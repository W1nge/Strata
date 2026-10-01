"""tools/requant_gsq.py - (this fork) hand-rolled dequantizers for the two GSQ-RCO expert-row formats
whose ggml-cpu x86 kernels are broken in the pinned llama.cpp build: Q2_0 (returns all zeros - proven
with a hand-crafted block) and IQ1_M (faults outside the CPU backend's repack).  Decode mirrors
ggml-quants.c's dequantize_row_q2_0 / dequantize_row_iq1_m byte for byte; re-quantization to
IQ2_S / IQ4_NL goes through gguf-py's own quantizers (which DO exist for those targets).

Layouts (ggml-common.h): block_q2_0 = d fp16 + qs[16] (2-bit codes), 18 B per 64 values.
block_iq1_m = qs[32] + qh[16] + scales[8], 56 B per 256 values; scale fp16 assembled from nibbles of
scales[0..3]; per 32-value sub-block ib (8 per block): dl = d * (2*((sc[ib/2] >> (6*(ib%2))) & 7) + 1)
and dl2 with +3; the deltas come from qh bits.
"""
from __future__ import annotations

import numpy as np

IQ1S_DELTA = 0.125
IQ1M_DELTA = 41275.0 / 16384.0


def dequant_q2_0_rows(raw: np.ndarray, rows: int, row_bytes: int, n_per_row: int) -> np.ndarray:
    """raw: (rows, row_bytes) uint8 - per row: 40 x (d fp16, 16 B of 2-bit codes); n_per_row values per row.
    (row_bytes = n_per_row // 64 * 18: Q2_0 = 18 B per 64 values.)"""
    assert row_bytes == n_per_row // 64 * 18, (row_bytes, n_per_row)
    n_blocks = n_per_row // 64
    out = np.empty((rows, n_per_row), dtype=np.float32)
    d = np.frombuffer(np.ascontiguousarray(raw).reshape(rows * n_blocks, 18)[:, 0:2].tobytes(),
                      dtype=np.float16).astype(np.float32).reshape(rows * n_blocks)
    qs = np.ascontiguousarray(raw).reshape(rows * n_blocks, 18)[:, 2:18]
    codes = np.empty((rows * n_blocks, 16, 4), dtype=np.int8)
    for k in range(4):
        codes[:, :, k] = ((qs >> (2 * k)) & 3).astype(np.int8) - 1
    vals = codes.reshape(rows * n_blocks, 64).astype(np.float32)
    vals *= np.repeat(d, 64).reshape(rows * n_blocks, 64)
    out[:] = vals.reshape(rows, n_per_row)
    return out


# iq1s_grid lives in ggml-quants.c as a 2048-entry table of 8 packed int8 values in a u64.  We rebuild
# it from the C header by evaluating the same expression ggml uses at compile time...  It is a plain
# constant table; we carry it as a generated module next to this file.
from _iq1s_grid import IQ1S_GRID  # noqa: E402


def dequant_iq1_m_rows(raw: np.ndarray, rows: int, row_bytes: int, values_per_row: int) -> np.ndarray:
    """raw: (rows, row_bytes) uint8; row_bytes = 56 x (values_per_row // 256) blocks of 256 values."""
    assert row_bytes == values_per_row // 256 * 56
    n_blocks = values_per_row // 256
    rows = rows * (row_bytes // (n_blocks * 56)) if row_bytes != n_blocks * 56 else rows
    # 调用方把整个 expert 平面压成 (rows, row_bytes) 时（rows=640, row_bytes=560）行恰好就是块行。
    n_blocks = row_bytes // 56
    out = np.empty((rows, n_blocks * 256), dtype=np.float32)
    for r in range(rows):
        row = raw[r]
        # C 的循环：sc 是整个 ROW 的 8 字节 scales（per 256 值），ib 0..7 per 256；跨块时 sc 重新指向。
        # 这里一行 = row_bytes/56 个 256 值块；把行按块切成 56B，每块独立解 8 个 ib。
        for blk_i in range(n_blocks):
            blk = row[blk_i * 56:(blk_i + 1) * 56]
            qs_all = blk[0:32]
            qh_all = blk[32:48]
            sc_all = np.frombuffer(blk[48:56].tobytes(), dtype=np.uint16)
            scale_u16 = ((int(sc_all[0]) >> 12) | ((int(sc_all[1]) >> 8) & 0x00F0) |
                         ((int(sc_all[2]) >> 4) & 0x0F00) | (int(sc_all[3]) & 0xF000))
            d = float(np.frombuffer(np.uint16(scale_u16).tobytes(), dtype=np.float16)[0])
            y = out[r, blk_i * 256:(blk_i + 1) * 256]
            ypos = 0
            for ib in range(8):
                dl1 = d * (2 * ((int(sc_all[ib // 2]) >> (6 * (ib % 2))) & 0x7) + 1)
                dl2 = d * (2 * ((int(sc_all[ib // 2]) >> (6 * (ib % 2) + 3)) & 0x7) + 1)
                qs = qs_all[ib * 4: ib * 4 + 4]
                qh = qh_all[ib * 2: ib * 2 + 2]
                idx = [int(qs[0]) | ((int(qh[0]) << 8) & 0x700),
                       int(qs[1]) | ((int(qh[0]) << 4) & 0x700),
                       int(qs[2]) | ((int(qh[1]) << 8) & 0x700),
                       int(qs[3]) | ((int(qh[1]) << 4) & 0x700)]
                deltas = [IQ1S_DELTA if not (qh[0] & 0x08) else -IQ1S_DELTA,
                          IQ1S_DELTA if not (qh[0] & 0x80) else -IQ1S_DELTA,
                          IQ1S_DELTA if not (qh[1] & 0x08) else -IQ1S_DELTA,
                          IQ1S_DELTA if not (qh[1] & 0x80) else -IQ1S_DELTA]
                for l in range(2):
                    grid = IQ1S_GRID[idx[l]]
                    for j in range(8):
                        y[ypos] = dl1 * (grid[j] + deltas[l])
                        ypos += 1
                for l in range(2, 4):
                    grid = IQ1S_GRID[idx[l]]
                    for j in range(8):
                        y[ypos] = dl2 * (grid[j] + deltas[l])
                        ypos += 1
    return out
