// Check native Q2_0 VNNI and runtime dispatch against AVX2 across token tiling,
// both projection widths, unaligned rows, extreme codes/activations and row slices.
#include "strata/kernels/cpu/expert_layout.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

using namespace strata::kernels::cpu;

int main() {
    constexpr int nr = 7, r0 = 1, r1 = 6;
    int checks = 0;
    const bool vnni = cpu_avx_vnni_ok();
    const char* enable = std::getenv("STRATA_Q2_AVX_VNNI");
    if ((enable == nullptr || enable[0] != '1') && vnni) {
        std::printf("FAIL: AVX-VNNI enabled without opt-in\n");
        return 1;
    }
    for (const char* key : {"STRATA_FORCE_AVX2", "STRATA_NO_AVX_VNNI"})
        if (const char* value = std::getenv(key); value && value[0] == '1' && vnni) {
            std::printf("FAIL: %s did not disable AVX-VNNI\n", key);
            return 1;
        }
    for (int nb : {1, 10, 40}) for (int pattern = 0; pattern < 5; ++pattern) {
        const size_t stride = nb * 18 + 3; // deliberately unaligned, with padding
        std::vector<uint8_t> w(nr * stride + 1);
        for (int r = 0; r < nr; ++r) for (int b = 0; b < nb; ++b) {
            auto* block = w.data() + 1 + r * stride + b * 18;
            const uint16_t scales[] = {0, 0x1800, 0x3400, 0x3c00, 0xbc00};
            const uint16_t scale = scales[(r + b) % 5];
            std::memcpy(block, &scale, 2);
            for (int k = 0; k < 16; ++k)
                block[k + 2] = pattern < 4 ? (uint8_t) (pattern * 85) : (uint8_t) (r * 17 + b * 31 + k * 43);
        }
        ActQ acts[8] = {};
        const ActQ* ap[8];
        std::vector<float> ref[8], got[8];
        float *rp[8], *gp[8];
        for (int t = 0; t < 8; ++t) {
            ap[t] = &acts[t];
            acts[t].nchunks = nb * 2;
            for (int c = 0; c < nb * 2; ++c) {
                acts[t].scale[c] = std::ldexp(1.f, (c + t) % 5 - 8);
                for (int k = 0; k < 32; ++k) {
                    const int v = pattern == 0 ? 0 : pattern == 4 ? (k * 37 + t * 19 + c * 3) % 255 - 127 :
                                  ((k + t + c) & 1 ? 127 : -127);
                    acts[t].q[c * 32 + k] = (int8_t) v;
                    acts[t].sum[c] += v;
                }
                acts[t].hx[c] = acts[t].scale[c] * acts[t].sum[c];
            }
            ref[t].resize(nr); got[t].resize(nr);
            rp[t] = ref[t].data(); gp[t] = got[t].data();
        }
        for (int nt = 1; nt <= 8; ++nt) {
            for (int t = 0; t < 8; ++t) {
                std::fill(ref[t].begin(), ref[t].end(), 123456.f);
                std::fill(got[t].begin(), got[t].end(), 123456.f);
            }
            q2_0_gguf_rows_multi_avx2(w.data() + 1, stride, nb, ap, nt, rp, r0, r1);
            q2_rows_any(w.data() + 1, stride, nb, ap, nt, gp, r0, r1);
            auto check = [&] {
                for (int t = 0; t < 8; ++t) for (int r = 0; r < nr; ++r) {
                    // The new VNNI path preserves the AVX2 floating-point order exactly.
                    if (!std::isfinite(got[t][r]) || got[t][r] != ref[t][r]) {
                        std::printf("FAIL nb=%d pattern=%d nt=%d t=%d r=%d ref=%g got=%g\n",
                                    nb, pattern, nt, t, r, ref[t][r], got[t][r]);
                        return false;
                    }
                    ++checks;
                }
                return true;
            };
            // Existing AVX-512 kernels may use another reduction order. The direct
            // VNNI comparison below remains exact on those machines as well.
            if (!cpu_avx512_ok() && !check()) return 1;
#if defined(STRATA_HAVE_AVX_VNNI)
            if (vnni) {
                for (auto& v : got) std::fill(v.begin(), v.end(), 123456.f);
                q2_0_gguf_rows_multi_avx_vnni(w.data() + 1, stride, nb, ap, nt, gp, r0, r1);
                if (!check()) return 1;
            }
#endif
        }
    }
    std::printf("q2_vnni_test: %d exact comparisons passed; AVX-VNNI %s\n", checks, vnni ? "enabled" : "disabled/unavailable");
    return 0;
}
