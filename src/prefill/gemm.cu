// src/prefill/gemm.cu - see include/strata/prefill/gemm.hpp.
#include "strata/prefill/gemm.hpp"
#include "strata/kernels/dequant_bf16.hpp"

#include <cublas_v2.h>
#include <cuda_runtime.h>
#include <cuda_fp16.h>

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>

namespace strata::prefill {
namespace {

std::atomic<int> turing_bf16_enabled{-1};
bool is_turing() {
    int device = 0, major = 0, minor = 0;
    return cudaGetDevice(&device) == cudaSuccess &&
        cudaDeviceGetAttribute(&major, cudaDevAttrComputeCapabilityMajor, device) == cudaSuccess &&
        cudaDeviceGetAttribute(&minor, cudaDevAttrComputeCapabilityMinor, device) == cudaSuccess &&
        major == 7 && minor == 5;
}

void cuda_ck(cudaError_t e, const char* what) {
    if (e != cudaSuccess) {
        std::fprintf(stderr, "prefill gemm: %s: %s\n", what, cudaGetErrorString(e));
        std::exit(1);
    }
}

// A power-of-two scale per row puts its largest BF16 value in the top FP16
// exponent bin. BF16 has fewer significand bits, so most rows convert exactly.
// Validate EVERY value by converting back: wide-range rows, NaNs and infinities
// are never silently rounded, clipped or dropped by this optimization.
__global__ void bf16_scale_rows(const uint16_t* src, uint16_t* dst, int* shifts,
                                int cols, int* bad, int* bad_ids) {
    __shared__ unsigned maxima[8];
    const int lane = threadIdx.x & 31, warp = threadIdx.x >> 5;
    const int64_t base = (int64_t) blockIdx.x * cols;
    unsigned mx = 0;
    for (int i = threadIdx.x; i < cols; i += blockDim.x) mx = max(mx, (unsigned) (src[base+i] & 0x7fff));
    for (int d = 16; d; d >>= 1) mx = max(mx, __shfl_down_sync(0xffffffffu, mx, d));
    if (lane == 0) maxima[warp] = mx;
    __syncthreads();
    if (warp == 0) {
        mx = lane < 8 ? maxima[lane] : 0;
        for (int d = 16; d; d >>= 1) mx = max(mx, __shfl_down_sync(0xffffffffu, mx, d));
        if (lane == 0) maxima[0] = mx;
    }
    __syncthreads();
    mx = maxima[0];
    const int shift = mx ? min(126, max(-112, 142 - (int) (mx >> 7))) : 0;
    if (threadIdx.x == 0) shifts[blockIdx.x] = shift;
    const float scale = __uint_as_float((unsigned) (shift + 127) << 23);
    const float inverse = __uint_as_float((unsigned) (127 - shift) << 23);
    bool fail = false;
    for (int i = threadIdx.x; i < cols; i += blockDim.x) {
        const float v = __uint_as_float((unsigned) src[base+i] << 16);
        const __half h = __float2half_rn(__fmul_rn(v, scale));
        dst[base+i] = __half_as_ushort(h);
        const float back = __fmul_rn(__half2float(h), inverse);
        fail |= !isfinite(v) || back != v;
    }
    if (__syncthreads_or(fail) && threadIdx.x == 0) {
        shifts[blockIdx.x] = -1000;
        const int id = atomicAdd(bad, 1);
        if (bad_ids) bad_ids[id] = (int) blockIdx.x;
    }
}

__global__ void bf16_unscale(const float* src, float* dst, const int* xs, const int* ws,
                             int n, int rows, int src_ld, int ldy, float beta) {
    const int64_t i = (int64_t) blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= (int64_t) rows * n) return;
    const int row = (int) (i / n), col = (int) (i % n);
    if (xs[row] == -1000) return; // the original output is retained for the exact BF16 fallback (including beta)
    const float value = scalbnf(src[(int64_t) row * src_ld + col], -xs[row] - ws[col]);
    float* y = dst + (int64_t) row * ldy + col;
    *y = beta == 0.0f ? value : fmaf(beta, *y, value);
}

template<class T> __global__ void gather_bad_rows(const T* src, T* dst, const int* ids,
                                                 int cols, int rows, int ld) {
    const int64_t i = (int64_t) blockIdx.x * blockDim.x + threadIdx.x;
    if (i < (int64_t) rows * cols) dst[i] = src[(int64_t) ids[i / cols] * ld + i % cols];
}
__global__ void scatter_bad_rows(const float* src, float* dst, const int* ids, int cols, int rows, int ld) {
    const int64_t i = (int64_t) blockIdx.x * blockDim.x + threadIdx.x;
    if (i < (int64_t) rows * cols) dst[(int64_t) ids[i / cols] * ld + i % cols] = src[i];
}

void ck(cublasStatus_t s, const char* what) {
    if (s != CUBLAS_STATUS_SUCCESS) {
        std::fprintf(stderr, "prefill gemm: %s: cuBLAS status %d\n", what, (int) s);
        std::exit(1);
    }
}

}  // namespace

void Gemm::set_turing_bf16(bool enabled) { turing_bf16_enabled.store(enabled, std::memory_order_relaxed); }

Gemm::~Gemm() {
    if (std::getenv("STRATA_PREFILL_TIMING") && (fast_tiles_ || fallback_tiles_))
        std::fprintf(stderr, "strata prefill bf16: exact-scaled tiles %lld, BF16 fallback tiles %lld\n",
                     (long long) fast_tiles_, (long long) fallback_tiles_);
    if (handle_) cublasDestroy((cublasHandle_t) handle_);
    if (!external_) {
        if (scratch_) cudaFree(scratch_);
        if (workspace_) cudaFree(workspace_);
    }
}

bool Gemm::init_external(void* stream, uint16_t* scratch, int64_t scratch_elems, void* workspace, size_t ws_bytes,
                         std::string& err) {
    cublasHandle_t h = nullptr;
    if (cublasCreate(&h) != CUBLAS_STATUS_SUCCESS) { err = "prefill gemm: cublasCreate failed"; return false; }
    handle_ = h;
    stream_ = stream;
    turing_ = is_turing();
    external_ = true;
    cublasSetStream(h, (cudaStream_t) stream);
    workspace_ = workspace;
    cublasSetWorkspace(h, workspace_, ws_bytes);
    cublasSetMathMode(h, CUBLAS_DEFAULT_MATH);
    scratch_ = scratch;
    scratch_elems_ = scratch_elems;
    return true;
}

void Gemm::rebind(uint16_t* scratch, int64_t scratch_elems, void* workspace, size_t ws_bytes) {
    scratch_ = scratch;
    scratch_elems_ = scratch_elems;
    workspace_ = workspace;
    cublasSetWorkspace((cublasHandle_t) handle_, workspace_, ws_bytes);
}

bool Gemm::init(void* stream, int64_t scratch_elems, std::string& err) {
    cublasHandle_t h = nullptr;
    if (cublasCreate(&h) != CUBLAS_STATUS_SUCCESS) { err = "prefill gemm: cublasCreate failed"; return false; }
    handle_ = h;
    stream_ = stream;
    turing_ = is_turing();
    cublasSetStream(h, (cudaStream_t) stream);
    // A fixed workspace so the handle never allocates on the way (and graphs could capture it later).
    const size_t ws = 32u << 20;
    if (cudaMalloc(&workspace_, ws) != cudaSuccess) { err = "prefill gemm: workspace"; return false; }
    cublasSetWorkspace(h, workspace_, ws);
    cublasSetMathMode(h, CUBLAS_DEFAULT_MATH);
    if (scratch_elems > 0 && cudaMalloc((void**) &scratch_, (size_t) scratch_elems * 2) != cudaSuccess) {
        err = "prefill gemm: dequant scratch of " + std::to_string(scratch_elems * 2 >> 20) + " MiB";
        return false;
    }
    scratch_elems_ = scratch_elems;
    return true;
}

void Gemm::bf16(const uint16_t* X, const uint16_t* W, float* Y, int64_t T, int64_t N, int64_t K, int64_t ldy,
                float beta) {
    if (T <= 0 || N <= 0) return;
    if (ldy <= 0) ldy = N;
    const char* opt = std::getenv("STRATA_TURING_BF16_GEMM");
    const int mode = turing_bf16_enabled.load(std::memory_order_relaxed);
    if (turing_ && (mode >= 0 ? mode != 0 : opt && std::atoi(opt) != 0) &&
        bf16_turing(X, W, Y, T, N, K, ldy, beta)) return;
    const float alpha = 1.0f;
    // Column-major view: Y^T[N, T] = W[N, K] (stored K x N col-major, transposed) . X^T[K, T].
    ck(cublasGemmEx((cublasHandle_t) handle_, CUBLAS_OP_T, CUBLAS_OP_N, (int) N, (int) T, (int) K, &alpha, W,
                    CUDA_R_16BF, (int) K, X, CUDA_R_16BF, (int) K, &beta, Y, CUDA_R_32F, (int) ldy,
                    CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT),
       "cublasGemmEx");
}

bool Gemm::bf16_turing(const uint16_t* X, const uint16_t* W, float* Y, int64_t T, int64_t N, int64_t K,
                       int64_t ldy, float beta) {
    // Limit the initial optimization to the model's two large HC projections.
    // Reuse existing scratch; no extra VRAM, allocation or expert-cache eviction.
    if (T < 128 || !((K == 10240 && N == 320) || (K == 320 && N == 10240)) || !scratch_) return false;
    const size_t cap = (size_t) scratch_elems_ * 2;
    const auto aligned = [](size_t n) { return (n + 255) & ~(size_t) 255; };
    const size_t wbytes = aligned((size_t) N * K * 2), wsbytes = aligned((size_t) N * sizeof(int));
    if (cap <= wbytes + wsbytes + 1024) return false;
    const size_t per_row = (size_t) K * 2 + (beta == 0.0f ? 0 : (size_t) N * 4) + 2*sizeof(int);
    const int64_t limit = std::min<int64_t>(16384, (int64_t) ((cap - wbytes - wsbytes - 1024) / per_row));
    int rows = 1;
    while ((int64_t) rows * 2 <= limit) rows *= 2;
    if (rows < 128) return false;
    uint8_t* p = (uint8_t*) scratch_;
    uint16_t* wh = (uint16_t*) p; p += wbytes;
    int* ws = (int*) p; p += wsbytes;
    uint8_t* arena = p;
    uint8_t* meta = (uint8_t*) scratch_ + cap - 256 - 2*aligned((size_t) rows*sizeof(int));
    int* xs = (int*) meta;
    int* ids = (int*) (meta + aligned((size_t) rows*sizeof(int)));
    int* bad = (int*) ((uint8_t*) scratch_ + cap - 256);
    uint16_t* xh = (uint16_t*) arena;
    float* tmp = (float*) (arena + aligned((size_t) rows*K*2));
    const size_t arena_bytes = (size_t) (meta - arena);
    if (aligned((size_t) rows*K*2) + (beta == 0.0f ? 0 : aligned((size_t) rows*N*4)) > arena_bytes) return false;
    const auto stream = (cudaStream_t) stream_;
    auto read_bad = [&]() {
        int host_bad = 0;
        cuda_ck(cudaMemcpyAsync(&host_bad, bad, sizeof(int), cudaMemcpyDeviceToHost, stream), "BF16 range read");
        cuda_ck(cudaStreamSynchronize(stream), "BF16 range check");
        return host_bad;
    };
    cuda_ck(cudaMemsetAsync(bad, 0, sizeof(int), stream), "BF16 range clear");
    bf16_scale_rows<<<(unsigned) N, 256, 0, stream>>>(W, wh, ws, (int) K, bad, nullptr);
    cuda_ck(cudaGetLastError(), "BF16 weight conversion");
    if (read_bad()) { ++fallback_tiles_; return false; }
    cublasMath_t previous_math;
    ck(cublasGetMathMode((cublasHandle_t) handle_, &previous_math), "read GEMM math mode");
    ck(cublasSetMathMode((cublasHandle_t) handle_, (cublasMath_t)
        ((unsigned) previous_math | (unsigned) CUBLAS_MATH_DISALLOW_REDUCED_PRECISION_REDUCTION)),
        "FP32 reduction for scaled GEMM");
    const float one = 1.0f, zero = 0.0f;
    for (int64_t t = 0; t < T; t += rows) {
        const int nb = (int) std::min<int64_t>(rows, T - t);
        cuda_ck(cudaMemsetAsync(bad, 0, sizeof(int), stream), "BF16 range clear");
        bf16_scale_rows<<<(unsigned) nb, 256, 0, stream>>>(X + t*K, xh, xs, (int) K, bad, ids);
        cuda_ck(cudaGetLastError(), "BF16 activation conversion");
        const int nbad = read_bad();
        if (nbad == nb) {
            ++fallback_tiles_;
            ck(cublasGemmEx((cublasHandle_t) handle_, CUBLAS_OP_T, CUBLAS_OP_N, (int) N, nb, (int) K,
                            &one, W, CUDA_R_16BF, (int) K, X + t*K, CUDA_R_16BF, (int) K,
                            &beta, Y + t*ldy, CUDA_R_32F, (int) ldy, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT),
               "BF16 tile fallback");
            continue;
        }
        ++fast_tiles_;
        float* output = beta == 0.0f ? Y + t*ldy : tmp;
        const int output_ld = beta == 0.0f ? (int) ldy : (int) N;
        ck(cublasGemmEx((cublasHandle_t) handle_, CUBLAS_OP_T, CUBLAS_OP_N, (int) N, nb, (int) K,
                        &one, wh, CUDA_R_16F, (int) K, xh, CUDA_R_16F, (int) K,
                        &zero, output, CUDA_R_32F, output_ld, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT),
           "exact-scaled FP16 GEMM");
        bf16_unscale<<<(unsigned) (((int64_t) nb * N + 255) / 256), 256, 0, stream>>>(
            output, Y + t*ldy, xs, ws, (int) N, nb, output_ld, (int) ldy, beta);
        cuda_ck(cudaGetLastError(), "BF16 output rescale");
        // Only rows that failed the lossless conversion need BF16. Compact them
        // after the fast GEMM; the same scratch is now free for fallback X and Y.
        const int fallback_rows = (int) ((arena_bytes-512) / ((size_t) K*2 + (size_t) N*4));
        for (int b = 0; b < nbad; b += fallback_rows) {
            const int count = std::min(fallback_rows, nbad-b);
            float* fy = (float*) (arena + aligned((size_t) count*K*2));
            gather_bad_rows<<<(unsigned) (((int64_t) count*K+255)/256), 256, 0, stream>>>(
                X+t*K, xh, ids+b, (int) K, count, (int) K);
            if (beta != 0.0f)
                gather_bad_rows<<<(unsigned) (((int64_t) count*N+255)/256), 256, 0, stream>>>(
                    Y+t*ldy, fy, ids+b, (int) N, count, (int) ldy);
            cuda_ck(cudaGetLastError(), "BF16 fallback gather");
            ck(cublasGemmEx((cublasHandle_t) handle_, CUBLAS_OP_T, CUBLAS_OP_N, (int) N, count, (int) K,
                            &one, W, CUDA_R_16BF, (int) K, xh, CUDA_R_16BF, (int) K,
                            &beta, fy, CUDA_R_32F, (int) N, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT),
               "BF16 row fallback");
            scatter_bad_rows<<<(unsigned) (((int64_t) count*N+255)/256), 256, 0, stream>>>(
                fy, Y+t*ldy, ids+b, (int) N, count, (int) ldy);
            cuda_ck(cudaGetLastError(), "BF16 fallback scatter");
            ++fallback_tiles_;
        }
    }
    ck(cublasSetMathMode((cublasHandle_t) handle_, previous_math), "restore GEMM math mode");
    return true;
}

void Gemm::f16(const uint16_t* X, const uint16_t* W, float* Y, int64_t T, int64_t N, int64_t K, int64_t ldy,
               float beta) {
    if (T <= 0 || N <= 0) return;
    if (ldy <= 0) ldy = N;
    const float alpha = 1.0f;
    ck(cublasGemmEx((cublasHandle_t) handle_, CUBLAS_OP_T, CUBLAS_OP_N, (int) N, (int) T, (int) K, &alpha, W,
                    CUDA_R_16F, (int) K, X, CUDA_R_16F, (int) K, &beta, Y, CUDA_R_32F, (int) ldy,
                    CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT),
       "cublasGemmEx f16");
}

void Gemm::native(const uint16_t* X, int ggml_type, const void* W_blocks, float* Y, int64_t T, int64_t N, int64_t K,
                  int64_t ldy, float beta) {
    if (N * K > scratch_elems_) {
        // Too large for the scratch at once: in row slices.
        const int64_t rows = scratch_elems_ / K;
        if (rows <= 0) { std::fprintf(stderr, "prefill gemm: scratch too small for K=%lld\n", (long long) K); std::exit(1); }
        if (ldy <= 0) ldy = N;
        for (int64_t r0 = 0; r0 < N; r0 += rows) {
            const int64_t n = (N - r0 < rows) ? N - r0 : rows;
            strata::kernels::dequant_f16(ggml_type, W_blocks, r0, n, K, scratch_, stream_);
            f16(X, scratch_, Y + r0, T, n, K, ldy, beta);
        }
        return;
    }
    strata::kernels::dequant_f16(ggml_type, W_blocks, 0, N, K, scratch_, stream_);
    f16(X, scratch_, Y, T, N, K, ldy, beta);
}

}  // namespace strata::prefill
