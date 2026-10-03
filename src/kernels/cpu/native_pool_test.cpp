// Exercise real native dispatch, mixed token counts, row splitting and profile sources.
// Profiling must not change one bit of the serial kernel's output.
#include "strata/kernels/cpu/pool.hpp"
#include "strata/kernels/cpu/expert_layout.hpp"
#include "strata/kernels/cpu/iq_avx2.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace strata::kernels::cpu;

int main() {
    ExpertPool pool(3, false);
    if (pool.set_native_tuning(0, 0) || pool.set_native_tuning(17, 0) ||
        pool.set_native_tuning(3, -1) || pool.set_native_tuning(3, 4) ||
        pool.set_native_tuning(3, 0, -1) || pool.set_native_tuning(3, 0, 8) || pool.set_native_tuning(3, 0, 0, -1) || pool.set_native_tuning(3, 0, 0, 3)) return 1;
    int checks = 0;
    for (int pattern : {0, 1}) for (int gu_type : {16, 17, 21}) for (int down_type : {20, 42}) for (int nt1 : {0, 7}) {
        NativeFmt f;
        std::string err;
        if (!native_fmt(gu_type, down_type, H, FF, f, err)) return 1;
        std::vector<uint8_t> blob(f.bytes);
        for (size_t i = 0; i < blob.size(); ++i) blob[i] = (uint8_t) (i * 37 + 19);
        // Each selected gate/up format starts its 256-value block with an f16 scale.
        // IQ4_NL/Q2_0 down: 18-byte blocks, also with an f16 block scale.
        const uint16_t scale = 0x2400; // 1/64, comfortably finite through both projections
        for (size_t i = 0; i < f.down_off; i += f.gu_row / (H / 256)) std::memcpy(blob.data() + i, &scale, 2);
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
        const int nts[3] = {pattern ? 2 : 1, pattern ? 4 : 3, pattern ? 5 : 6};
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
            if (nt1 && nts[e] == 1)
                iq256_gu_rows(gu_type, blob.data(), f.gu_row, f.up_off, H, ap, 1, fp, 0, FF);
            else native_gu_rows(f, blob.data(), ap, nts[e], fp, 0, FF);
            for (int t = 0; t < nts[e]; ++t)
                if (down_type == 42) act_quant_any(ff[t], FF, a2[t]);
                else native_quant_h(f, ff[t], hq[t]);
            if (down_type == 42)
                q2_rows_any(blob.data() + f.down_off, f.d_row, FF / 64, a2p, nts[e], op, 0, H);
            else native_down_rows(f, blob.data(), hp, nts[e], op, 0, H);
        }
        const std::vector<ExpertJobMulti> original(jobs, jobs + 3);
        for (int tasks : {1, 3, 6, 12, 16}) for (int order = 0; order < 4; ++order) for (int shape = 0; shape < 3; ++shape) {
            const int repeat = tasks * 4 + order;
            if (!pool.set_native_tuning(tasks, order, nt1, shape)) return 1;
            std::copy(original.begin(), original.end(), jobs);
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
