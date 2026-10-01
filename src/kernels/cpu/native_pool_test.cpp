// Exercise real native dispatch, mixed token counts, row splitting and profile sources.
// Profiling must not change one bit of the serial kernel's output.
#include "strata/kernels/cpu/pool.hpp"
#include "strata/kernels/cpu/expert_layout.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace strata::kernels::cpu;

int main() {
    ExpertPool pool(3, false);
    int checks = 0;
    for (int down_type : {20, 42}) {
        NativeFmt f;
        std::string err;
        if (!native_fmt(16, down_type, H, FF, f, err)) return 1;
        std::vector<uint8_t> blob(f.bytes);
        for (size_t i = 0; i < blob.size(); ++i) blob[i] = (uint8_t) (i * 37 + 19);
        // IQ2_XXS: 66-byte blocks. IQ4_NL/Q2_0: 18-byte blocks. All use an f16 block scale.
        const uint16_t scale = 0x2400; // 1/64, comfortably finite through both projections
        for (size_t i = 0; i < f.down_off; i += 66) std::memcpy(blob.data() + i, &scale, 2);
        for (size_t i = f.down_off; i < f.bytes; i += 18) std::memcpy(blob.data() + i, &scale, 2);
        alignas(64) uint8_t acts[MAXT][kNativeActBytes];
        const void* ap[MAXT];
        float x[H];
        for (int t = 0; t < MAXT; ++t) {
            for (int i = 0; i < H; ++i) x[i] = std::sin(float(i * 7 + t) * 0.03f) * 0.1f;
            native_quant_act(f, x, acts[t]);
            ap[t] = acts[t];
        }
        std::vector<float> reference(3 * MAXT * H), actual(reference.size());
        ExpertJobMulti jobs[3];
        const int nts[3] = {1, 3, 6};
        for (int e = 0; e < 3; ++e) {
            jobs[e].blob = blob.data(); jobs[e].nt = nts[e]; jobs[e].profile_source = e;
            float ff[MAXT][FF];
            float* fp[MAXT];
            float* op[MAXT];
            alignas(64) uint8_t hq[MAXT][kNativeHBytes];
            ActQ a2[MAXT];
            const void* hp[MAXT];
            const ActQ* a2p[MAXT];
            for (int t = 0; t < nts[e]; ++t) {
                jobs[e].nact[t] = ap[t];
                jobs[e].out[t] = actual.data() + (e * MAXT + t) * H;
                fp[t] = ff[t]; op[t] = reference.data() + (e * MAXT + t) * H;
                hp[t] = hq[t]; a2p[t] = &a2[t];
            }
            native_gu_rows(f, blob.data(), ap, nts[e], fp, 0, FF);
            for (int t = 0; t < nts[e]; ++t)
                if (down_type == 42) act_quant_any(ff[t], FF, a2[t]);
                else native_quant_h(f, ff[t], hq[t]);
            if (down_type == 42)
                q2_rows_any(blob.data() + f.down_off, f.d_row, FF / 64, a2p, nts[e], op, 0, H);
            else native_down_rows(f, blob.data(), hp, nts[e], op, 0, H);
        }
        for (int repeat = 0; repeat < 5; ++repeat) {
            std::fill(actual.begin(), actual.end(), 123456.f);
            pool.run_split_multi_native(f, jobs, 3, down_type);
            for (int e = 0; e < 3; ++e) for (int t = 0; t < MAXT; ++t) for (int r = 0; r < H; ++r) {
                const size_t i = (e * MAXT + t) * H + r;
                const float expected = t < nts[e] ? reference[i] : 123456.f;
                if (!std::isfinite(actual[i]) || actual[i] != expected) {
                    std::printf("FAIL type %d repeat %d e %d t %d r %d expected %g got %g\n",
                                down_type, repeat, e, t, r, expected, actual[i]);
                    return 1;
                }
                ++checks;
            }
        }
    }
    pool.profile_report(stdout);
    std::puts("PROFILE RESET");
    pool.profile_report(stdout);
    std::printf("PASS native pool: %d exact/sentinel comparisons\n", checks);
    return 0;
}
