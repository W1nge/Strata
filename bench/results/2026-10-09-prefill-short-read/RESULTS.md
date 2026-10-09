# Prefill: where the batched path beats the verify windows, and a small-chunk abort (2026-10-09)

One fixture per run, a serial request path, a fresh engine process each time: driver 537.13, RTX 2080 Ti at 310 W +
Tesla P100 at 250 W, native IQ3_XXS pack, 8192 context, INT8 KV, spec 8.  `candidate` is 0.1.41 plus
`STRATA_PREFILL_HELPER_SOURCE=1` (the "take expert blobs from a helper's VRAM cache" patch); `baseline` is stock
0.1.41 (`9fcc7cd9`).  Every run answered its fixture with the expected value and `cache_n == 0` on the cold cases.
The configs, per-request memory samples, engine and server logs are all archived here, and `manifest.json` carries
the sha256 of each file.

## 1. The two ways a prompt is read

`--short-read` decides, per prompt segment (the parts between the checkpoint and turn cuts), whether up to that many
tokens go through the verify windows or through the batched prefill.  The crossover fixture walks one prompt size per
request, so both arms read the same prompts in one session each:

| prompt tokens | verify windows | batched prefill, helper source |
| ---: | ---: | ---: |
| 202 | 1716 ms / 8.49 ms a token | not measured |
| 316 | 2699 ms / 8.54 | not measured |
| 429 | 3820 ms / 8.90 | 3679 ms / 8.58 |
| 546 | 4913 ms / 9.00 | 4043 ms / 7.40 |
| 683 | 6303 ms / 9.23 | not measured |
| 801 | 8344 ms / 10.42 | 4812 ms / 6.01 |
| 918 | 8906 ms / 9.70 | 8463 ms / 9.22 |
| 1126 | 11166 ms / 9.92 | 6169 ms / 5.48 |

Windows: `cross-win-a` (`--short-read 8192`, everything on the windows).  Batched: `cross6-a` (`--short-read 256`)
and `cross3-mix-a` (`--short-read 768`) for the sizes above their own threshold.  The windows cost 8.5 - 10.4 ms a
token across the whole range; the batched path falls from 8.6 ms a token at 429 tokens to 5.5 at 1126, because it pays
a fixed lend-and-refill cost per segment.  The two are a wash around 430 tokens and the batched path wins from about
550 tokens on (the 918-token point is 25% out of line with its neighbours in both arms and reads as a cold-cache
outlier; it is kept here as measured).

## 2. `--short-read 768` on the 11-request fixture

| arm | exe | `--short-read` | 11 requests, prompt time |
| --- | --- | ---: | ---: |
| baseline | stock 0.1.41 | 1024 | 91.5 s |
| candidate | helper source | 1024 | 65.7 s |
| candidate | helper source | 768 | 59.0 s (`s768-full`) |

The two 884-token requests, which move from the windows to the batched path when the threshold drops, went from
8414 / 8490 ms to 4909 / 4737 ms.  The 422-token requests did not move (3781 / 3745 ms against 3893 / 3784 ms in the
baseline archive) because they stay on the windows - they are below the crossover.

The `bl-768-mf` control separates the two effects: the stock exe at `--short-read 768` reads the same 884-token
prompt batched, with the files as its only source, in 7123 ms (8.06 ms a token).  So of the ~3.5 s that request
gains, about 1.2 s comes from crossing to the batched path and about 2.2 s from the helper's cache as the source
(4866 ms, 5.50 ms a token, in the candidate run of the same fixture).

`lend-mf-768` is the candidate with the medium-first fixture, `big-first-768` the same with a 884-token prompt as the
very first request of the session (both pass, so the threshold does not depend on a warm-up request).

## 3. A small-chunk abort in the batched path (upstream, issue #1650)

With `--short-read 0` every segment is batched, including the role header the server appends at the end of a chat
prompt (about 6 tokens).  Chunks that small abort the engine:

```
prefill gemm: cublasGemmEx f16: cuBLAS status 14
```

`STRATA_TRACE=1` prints each chunk as it starts, which is how the boundary below was measured on the candidate and
reproduced on the stock exe (`cross-batch-base`):

| prompt chunk | run | outcome |
| ---: | --- | --- |
| 6 | `allbatch-192first`, `allbatch-320first`, `allbatch-884first`, `allbatch-trace-192first`, `t29-sr0` | aborts |
| 21 | `tinyseg-sr0` | aborts |
| 24 | `cross-batch-a` (the 24-token warm as the first request) | aborts |
| 33 | `t29-sr0` | reads in 2298 ms |
| 37 / 73 / 109 | `smallseg2-sr32` | read in 2148 / 2471 / 2730 ms |
| 195 | `sr64-warm192`, `allbatch-trace-192first` | reads in 3439 ms |
| 429 and up | `cross6-a`, `cross3-mix-a`, `s768-full` | read normally |

The boundary sits between 24 and 33 tokens of chunk.  It is not the first request that fails - in
`allbatch-trace-192first` a 195-token chunk reads and the 6-token chunk after it aborts - and it is not the CPU
share: `allbatch-noshare-192first` turns `STRATA_PREFILL_CPU_SHARE` off and aborts the same way.  The upstream
default of 64 keeps the 6-token header on the windows, which is why `sr64-warm192` reads 195 tokens batched and
returns normally.

## 4. What each run is

| label | exe | config knobs | fixture |
| --- | --- | --- | --- |
| `s768-full` | candidate | short-read 768 | `prefill-fixture.json` (11 requests) |
| `bl-768-mf` | baseline | short-read 768 | `lend-medium-first-fixture.json` |
| `lend-mf-768` | candidate | short-read 768 | `lend-medium-first-fixture.json` |
| `big-first-768` | candidate | short-read 768 | `big-first-fixture.json` (884 first) |
| `cross-win-a` | candidate | short-read 8192 | `crossover-fixture.json` |
| `cross6-a` | candidate | short-read 256 | `crossover6-fixture.json` |
| `cross3-mix-a` | candidate | short-read 768 | `crossover3-fixture.json` |
| `sr64-warm192` | candidate | short-read 64 (upstream default) | `warm-then-192-fixture.json` |
| `smallseg2-sr32` | candidate | short-read 32, STRATA_TRACE | `small-seg2-fixture.json` |
| `tinyseg-sr0` | candidate | short-read 0, STRATA_TRACE | `tiny-seg-fixture.json` |
| `t29-sr0` | candidate | short-read 0, STRATA_TRACE | `t29-fixture.json` |
| `allbatch-192first` / `-320first` / `-884first` | candidate | short-read 0 | `s192-first-fixture.json`, `s320-first-fixture.json`, `big-first-fixture.json` |
| `allbatch-trace-192first` | candidate | short-read 0, STRATA_TRACE + timing | `s192-first-fixture.json` |
| `allbatch-noshare-192first` | candidate | short-read 0, CPU share off | `s192-first-fixture.json` |
| `cross-batch-a` / `cross-batch-base` | candidate / baseline | short-read 0 | `crossover-fixture.json` |

Runner directory on the measurement host: `E:/strata-setup/part2-prefill-helper-source-20261009`.

