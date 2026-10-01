// test_iq1m.cpp - does ggml-cpu's x86 iq1_m vec_dot work on RAW GGUF rows (what Strata's
// native_expert.cpp feeds it), or does it need the backend's repack?  Canonical (traits table)
// and the _generic fallback are both called; a Python checker validates against requant_gsq's
// dequantizer.  Real block: layer-8 gate expert0 row0 of the IQ2_XS GGUF (iq1m_row.bin).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <vector>
#include "ggml.h"
#include "ggml-cpu.h"

extern "C" void ggml_vec_dot_iq1_m_q8_K_generic(int n, float * s, size_t bs, const void * vx, size_t bx,
                                                const void * vy, size_t by, int nrc);

static float act_at(unsigned seed, int i) {
    unsigned x = seed * 2654435761u + (unsigned) i * 2246822519u + 97u;
    x ^= x >> 13; x *= 3266489917u; x ^= x >> 16;
    return -2.5f + 5.0f * ((float) (x & 0xFFFFFF) / 16777216.0f);
}

int main(int argc, char** argv) {
    ggml_cpu_init();
    FILE* f = fopen(argc > 1 ? argv[1] : "iq1m_row.bin", "rb");
    if (!f) { fprintf(stderr, "no iq1m_row.bin\n"); return 1; }
    std::vector<unsigned char> row(560);
    if (fread(row.data(), 1, row.size(), f) != row.size()) { fprintf(stderr, "short read\n"); return 1; }
    fclose(f);

    const int n = 2560;
    const ggml_type_traits_cpu* qk = ggml_get_type_traits_cpu(GGML_TYPE_Q8_K);
    const ggml_type_traits_cpu* t = ggml_get_type_traits_cpu(GGML_TYPE_IQ1_M);
    printf("IQ1_M: vec_dot=%p vec_dot_type=%d\n", (void*) t->vec_dot, (int) t->vec_dot_type);

    std::vector<float> x(n);
    for (int i = 0; i < n; i++) x[i] = act_at(88, i);
    std::vector<unsigned char> act(ggml_row_size(GGML_TYPE_Q8_K, n) + 64);
    qk->from_float(x.data(), act.data(), n);

    float s1 = 0.f, s2 = 0.f;
    t->vec_dot(n, &s1, 0, row.data(), 0, act.data(), 0, 1);
    printf("canonical vec_dot : %.6e\n", (double) s1);
    ggml_vec_dot_iq1_m_q8_K_generic(n, &s2, 0, row.data(), 0, act.data(), 0, 1);
    printf("generic  vec_dot  : %.6e\n", (double) s2);
    printf("x float sum       : %.6e\n", (double) x[0]);
    return 0;
}
