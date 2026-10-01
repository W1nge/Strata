// AVX-VNNI (VEX, 256-bit) Q2_0 dots for CPUs such as Intel Core 12th-14th gen.
// This file is entered only after cpu_avx_vnni_ok(); it does not require AVX-512.
#define STRATA_Q2_AVX_VNNI
#include "q2_rows_impl.hpp"

namespace strata::kernels::cpu {

void q2_0_gguf_rows_multi_avx_vnni(const uint8_t* w, size_t row_bytes, int nblocks, const ActQ* const* a, int nt,
                                   float* const* out, int r0, int r1) {
    q2_rows_multi(w, row_bytes, nblocks, a, nt, out, r0, r1);
}

}  // namespace strata::kernels::cpu
