// rowprobe.cpp - real-block verification: read actual expert rows from a native pack's experts.bin and dot them
// through ggml-cpu's vec_dot exactly as src/kernels/cpu/native_expert.cpp does (traits table, from_float
// activations).  One line per probe: layer kind(gate=0,up=1,down=2) type row value.
// A Python checker recomputes the same products from dequantized rows (gguf-py / requant_gsq) and compares.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <array>
#include <string>
#include <vector>
#include "ggml.h"
#include "ggml-cpu.h"

static long long fsize(FILE* f) {
    _fseeki64(f, 0, SEEK_END);
    long long n = _ftelli64(f);
    _fseeki64(f, 0, SEEK_SET);
    return n;
}

// deterministic activation generator, replicated bit-exact in the Python checker
static float act_at(unsigned seed, int i) {
    unsigned x = seed * 2654435761u + (unsigned) i * 2246822519u + 97u;
    x ^= x >> 13; x *= 3266489917u; x ^= x >> 16;
    return -2.5f + 5.0f * ((float) (x & 0xFFFFFF) / 16777216.0f);
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: rowprobe <pack-dir>\n"); return 1; }
    std::string dir = argv[1];
    ggml_cpu_init();

    FILE* ft = fopen((dir + "\\native_experts.txt").c_str(), "rb");
    if (!ft) { fprintf(stderr, "no native_experts.txt\n"); return 1; }
    std::vector<std::array<long long, 8>> rows;   // layer gu d off blob gate_off up_off down_off
    char line[512];
    while (fgets(line, sizeof line, ft)) {
        if (line[0] == '#') continue;
        std::array<long long, 8> r{};
        if (sscanf(line, "%lld %lld %lld %lld %lld %lld %lld %lld", &r[0], &r[1], &r[2], &r[3], &r[4],
                   &r[5], &r[6], &r[7]) == 8)
            rows.push_back(r);
    }
    fclose(ft);
    fprintf(stderr, "%zu layers\n", rows.size());

    FILE* fb = fopen((dir + "\\experts.bin").c_str(), "rb");
    if (!fb) { fprintf(stderr, "no experts.bin\n"); return 1; }
    const long long total = fsize(fb);
    std::vector<unsigned char> buf(1 << 20);

    const int64_t n_embd = 2560, n_ff = 640;
    for (const auto& r : rows) {
        const int layer = (int) r[0];
        const ggml_type gu = (ggml_type) r[1], d = (ggml_type) r[2];
        const long long off = r[3], blob = r[4];
        const size_t gu_row = ggml_row_size(gu, n_embd), d_row = ggml_row_size(d, n_ff);
        if (2 * (long long) gu_row * n_ff + (long long) d_row * n_embd != blob) {
            fprintf(stderr, "layer %d: layout mismatch %lld vs %lld\n", layer,
                    2 * (long long) gu_row * n_ff + (long long) d_row * n_embd, blob);
            continue;
        }
        struct Plane { int kind; ggml_type t; long long base; int64_t n; size_t row_bytes; long long rows; };
        const Plane planes[3] = {
            {0, gu, 0, n_embd, gu_row, n_ff},
            {1, gu, (long long) gu_row * n_ff, n_embd, gu_row, n_ff},
            {2, d, 2 * (long long) gu_row * n_ff, n_ff, d_row, n_embd},
        };
        const ggml_type_traits_cpu* q8t = ggml_get_type_traits_cpu(GGML_TYPE_Q8_0);
        for (const Plane& p : planes) {
            const ggml_type_traits_cpu* tt = ggml_get_type_traits_cpu(p.t);
            if (!tt || !tt->vec_dot) { printf("%d %d %d -1 SKIP\n", layer, p.kind, (int) p.t); continue; }
            const long long probe_rows[2] = {0, p.rows - 1};
            for (int pr = 0; pr < 2; pr++) {
                const long long row = probe_rows[pr];
                const long long row_off = off + p.base + row * (long long) p.row_bytes;
                if (row_off < 0 || row_off + (long long) p.row_bytes > total) { fprintf(stderr, "oob\n"); continue; }
                _fseeki64(fb, row_off, SEEK_SET);
                if (fread(buf.data(), 1, p.row_bytes, fb) != p.row_bytes) { fprintf(stderr, "read\n"); continue; }
                const unsigned seed = (unsigned) (layer * 131 + p.kind * 17 + pr * 5 + 1);
                static std::vector<float> xa; static std::vector<unsigned char> qa;
                const ggml_type act_type = tt->vec_dot_type;          // the engine picks the quantizer this way
                const ggml_type_traits_cpu* at = ggml_get_type_traits_cpu(act_type);
                if (!at || !at->from_float) { printf("%d %d %d -1 NOACT\n", layer, p.kind, (int) p.t); continue; }
                const size_t act_bytes = ggml_row_size(act_type, p.n);
                xa.resize(p.n); qa.resize(act_bytes + 64);
                for (int64_t i = 0; i < p.n; i++) xa[i] = act_at(seed, (int) i);
                at->from_float(xa.data(), qa.data(), p.n);
                float s = 0.f;
                tt->vec_dot((int) p.n, &s, 0, buf.data(), 0, qa.data(), 0, 1);
                printf("%d %d %d %lld %.9g\n", layer, p.kind, (int) p.t, row, (double) s);
            }
        }
    }
    fclose(fb);
    return 0;
}
