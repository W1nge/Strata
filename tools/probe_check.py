# probe_check.py - verify rowprobe's ggml-cpu vec_dot values against independent dequantization.
# expected = dot(w_dequant, x_float); the kernel computes dot(w_dequant, act_q) where act_q is the
# q8/q8_K activation with per-element error <= amax/254, so |got-expect| must stay under
# (amax/254)*sum|w|.  A misread block (wrong grid, wrong scale offset, wrong stride) is orders of
# magnitude outside that bound.  Q2_0 rows use requant_gsq's hand-written dequantizer.
import sys
import numpy as np

sys.path.insert(0, r"C:\Users\Winge\.zcode\workspace\default\llama.cpp-oracle\gguf-py")
sys.path.insert(0, r"C:\Users\Winge\.zcode\workspace\default\Strata\tools")
from gguf import quants, GGMLQuantizationType as Q
from gguf.constants import GGML_QUANT_SIZES
from requant_gsq import dequant_q2_0_rows

PACK = r"C:\strata-models\pack-iq3xxs-native"
N_EMBD, N_FF = 2560, 640

def act_at(seed, i):
    x = (seed * 2654435761 + i * 2246822519 + 97) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 3266489917) & 0xFFFFFFFF
    x ^= x >> 16
    return -2.5 + 5.0 * ((x & 0xFFFFFF) / 16777216.0)

def w_dequant(raw, tname, n):
    if tname == "Q2_0":
        return dequant_q2_0_rows(np.frombuffer(raw, dtype=np.uint8).reshape(1, len(raw)),
                                 1, len(raw), n).ravel()
    return quants.dequantize(np.frombuffer(raw, dtype=np.uint8), Q[tname])

meta = {}
for line in open(PACK + r"\native_experts.txt"):
    if line.startswith("#"):
        continue
    f = line.split()
    meta[int(f[0])] = (int(f[1]), int(f[2]), int(f[3]), int(f[4]))

TNAME = {int(q): q.name for q in Q}
BSIZE = dict(GGML_QUANT_SIZES)

def row_bytes(t, n):
    blck, ts = BSIZE[t]
    return n // blck * ts

blob = open(PACK + r"\experts.bin", "rb")
checked = fails = 0
worst = 0.0
for line in open(r"C:\strata-kernel-test\probe_results.txt"):
    f = line.split()
    if len(f) < 5 or f[4] == "SKIP" or f[4] == "NOACT":
        continue
    layer, kind, t_id, row, got = int(f[0]), int(f[1]), int(f[2]), int(f[3]), float(f[4])
    gu_t, d_t, off, blob_bytes = meta[layer]
    if kind in (0, 1):
        base = 0 if kind == 0 else row_bytes(gu_t, N_EMBD) * N_FF
        n, rb, tid = N_EMBD, row_bytes(gu_t, N_EMBD), gu_t
    else:
        base = 2 * row_bytes(gu_t, N_EMBD) * N_FF
        n, rb, tid = N_FF, row_bytes(d_t, N_FF), d_t
    blob.seek(off + base + row * rb)
    raw = blob.read(rb)
    seed = layer * 131 + kind * 17 + (1 if row != 0 else 0) * 5 + 1
    x = np.array([act_at(seed, i) for i in range(n)], dtype=np.float32)
    w = w_dequant(raw, TNAME[tid], n)
    expect = float(np.dot(w.astype(np.float64), x.astype(np.float64)))
    bound = 2.5 / 127.0 / 2.0 * float(np.abs(w).sum()) + 1e-3
    ratio = abs(got - expect) / bound
    checked += 1
    worst = max(worst, ratio)
    if ratio > 1.0:
        fails += 1
        print(f"FAIL layer {layer} kind {kind} {TNAME[tid]} row {row}: got {got:.6g} expect {expect:.6g} "
              f"bound {bound:.3g} ratio {ratio:.3g}")
print(f"{checked} probes checked, {fails} failed, worst error/bound = {worst:.3f}")
