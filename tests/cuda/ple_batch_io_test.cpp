// Real-table PLE batches: alternate queue depths, compare every output byte.
// Row cache is disabled in both arms; this measures a component, not model speed.
#include "strata/kernels/ngram.hpp"
#include <chrono>
#include <cstdio>
#include <cstring>
#include <random>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    namespace k = strata::kernels;
    for (const int tokens : {8192, 32768}) {
        std::vector<uint32_t> rows((size_t) tokens * 16);
        std::vector<float> reference((size_t) tokens * 2560), out(reference.size());
        for (int cycle = 0; cycle < 4; ++cycle) {
            std::mt19937 rng(407 + tokens + cycle);
            for (int pass = 0; pass < 2; ++pass) {
                const int depth = (pass == (cycle % 2)) ? 64 : 256;
                k::PleIoOptions opts;
                opts.max_inflight = depth;
                opts.cache_rows = 0;
                k::PleTable table;
                std::string err;
                if (!table.open(argv[1], err, opts)) { std::fprintf(stderr, "%s\n", err.c_str()); return 1; }
                if (pass == 0) for (auto& r : rows) r = rng() % table.rows();
                auto start = std::chrono::steady_clock::now();
                if (!table.gather_batch(rows.data(), tokens, out.data(), err)) {
                    std::fprintf(stderr, "%s\n", err.c_str()); return 1;
                }
                double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
                if (pass == 0) reference = out;
                else if (std::memcmp(reference.data(), out.data(), out.size() * sizeof(float)) != 0) {
                    std::fprintf(stderr, "queue depths changed gathered rows\n"); return 1;
                }
                std::printf("tokens=%d cycle=%d depth=%d ms=%.3f exact=%d %s\n", tokens, cycle, depth, ms,
                            pass == 1, table.io_report().c_str());
                std::fflush(stdout);
            }
        }
    }
    std::puts("PASS: all queue-depth pairs are byte-identical");
}
