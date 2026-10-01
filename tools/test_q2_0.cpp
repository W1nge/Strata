// test_q2_0.c - decide whether ggml-cpu's Q2_0 vec_dot is broken under MSVC, or the caller is.
// Replicates Strata's exact call path: ggml_get_type_traits_cpu(type)->vec_dot with activations
// quantized by the traits' from_float.  Q4_0 runs as the known-good control (same fp16 tables).
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "ggml.h"
#include "ggml-cpu.h"

static void run_q2_0(void) {
    const int n = 64;
    // one block_q2_0 (18 B): f16 d = 2.0 (0x4000 LE) + 16 code bytes 0xAA (each 2-bit field = 2 -> value (2-1)*d)
    unsigned char w[18];
    w[0] = 0x00; w[1] = 0x40;
    memset(w + 2, 0xAA, 16);

    float x[64];
    for (int i = 0; i < n; i++) x[i] = 100.0f;

    const ggml_type_traits_cpu * q8t = ggml_get_type_traits_cpu(GGML_TYPE_Q8_0);
    unsigned char act[256];
    memset(act, 0, sizeof act);
    q8t->from_float(x, act, n);

    const ggml_type_traits_cpu * t = ggml_get_type_traits_cpu(GGML_TYPE_Q2_0);
    printf("Q2_0: vec_dot_type=%d vec_dot=%p from_float=%p\n", (int) t->vec_dot_type,
           (void *) t->vec_dot, (void *) t->from_float);
    float s = -1.0f;
    t->vec_dot(n, &s, 0, w, 0, act, 0, 1);
    printf("Q2_0 x Q8_0: got %.2f   expected 12800.00   -> %s\n", s,
           s == 12800.0f ? "PASS" : (s == 0.0f ? "ZERO-BUG" : "WRONG"));
}

static void run_q4_0(void) {
    const int n = 32;
    // one block_q4_0 (18 B): f16 d = 2.0 + 16 nibble bytes 0x99 (each nibble 9 -> value (9-8)*d = 2.0)
    unsigned char w[18];
    w[0] = 0x00; w[1] = 0x40;
    memset(w + 2, 0x99, 16);

    float x[32];
    for (int i = 0; i < n; i++) x[i] = 100.0f;

    const ggml_type_traits_cpu * q8t = ggml_get_type_traits_cpu(GGML_TYPE_Q8_0);
    unsigned char act[256];
    q8t->from_float(x, act, n);

    const ggml_type_traits_cpu * t = ggml_get_type_traits_cpu(GGML_TYPE_Q4_0);
    float s = -1.0f;
    t->vec_dot(n, &s, 0, w, 0, act, 0, 1);
    printf("Q4_0 x Q8_0: got %.2f   expected 6400.00    -> %s\n", s,
           s == 6400.0f ? "PASS" : "FAIL");
}

// n = 128: two Q2_0 blocks, second with varied codes and x, to catch packing/bit-order bugs
static void run_q2_0_varied(void) {
    const int n = 128;
    unsigned char w[36];
    w[0] = 0x00; w[1] = 0x40;                 // block 0: d = 2.0, all codes 2 -> values 2.0
    memset(w + 2, 0xAA, 16);
    w[18] = 0x00; w[19] = 0x3C;               // block 1: d = 1.0 (0x3C00 LE)
    for (int i = 0; i < 16; i++) w[20 + i] = (unsigned char) (i * 7 + 1);   // varied codes

    float x[128];
    for (int i = 0; i < n; i++) x[i] = 1.0f + (float) (i % 5);

    const ggml_type_traits_cpu * q8t = ggml_get_type_traits_cpu(GGML_TYPE_Q8_0);
    unsigned char act[1024];
    q8t->from_float(x, act, n);

    // expected: dequant each block with the spec formula ((code)-1)*d, dot with x
    double expect = 0.0;
    for (int blk = 0; blk < 2; blk++) {
        float d = blk == 0 ? 2.0f : 1.0f;
        for (int i = 0; i < 64; i++) {
            int byte = i / 4, sh = 2 * (i % 4);
            int code = (w[blk * 18 + 2 + byte] >> sh) & 3;
            expect += (double) (code - 1) * d * x[blk * 64 + i];
        }
    }

    const ggml_type_traits_cpu * t = ggml_get_type_traits_cpu(GGML_TYPE_Q2_0);
    float s = -1.0f;
    t->vec_dot(n, &s, 0, w, 0, act, 0, 1);
    printf("Q2_0 varied (n=128): got %.2f   expected %.2f   -> %s\n", s, expect,
           (s - expect) / expect < 0.01 && (expect - s) / expect < 0.01 ? "PASS" : "WRONG");
}

int main(void) {
    ggml_cpu_init();
    run_q4_0();
    run_q2_0();
    run_q2_0_varied();
    return 0;
}
