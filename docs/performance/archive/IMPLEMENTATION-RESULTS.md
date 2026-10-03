> 历史原始报告（归档于 2026-10-03）。本文的“当前/已启用/未推送”只表示当时状态；最终采用项、纠错和发布状态以 [总总结](../OPTIMIZATION-SUMMARY.md) 为准。本归档仅添加此说明并替换个人工作区路径，未改写测量结论。附件名可能指本机证据包；已公开的小型数据见 [索引](../../../bench/results/2026-10-03-local-optimization/README.md)。

> 历史阶段记录：其中的 PCIe x4 数据不代表当前 x16 配置；最新结论见 CONTINUOUS-OPTIMIZATION-X16.md。

# Strata CPU optimization: applied changes and measurements

> Historical first-stage report. Later memory fixes, deployed settings and final speed measurements are recorded in DECODE-40-RESULTS.md.

Date: 2026-10-02. Model: the existing IQ3_XXS native pack. Repository: `<REPO>`, branch `codex/avx-vnni-q2`.

**The everyday configuration now uses a 10 GiB pinned-expert budget instead of 13 GiB. The new AVX-VNNI implementation is built and tested, but remains opt-in: its isolated kernel improvement did not translate into a reliable full-model improvement in these trials.**

Use the existing `C:/strata-models/run-iq3xxs-native.bat` launcher. Its JSON configuration has already been updated. A resident server is also running at `http://127.0.0.1:8080`; do not start a second copy while it is running. The running service uses an equivalent saved configuration in the Codex work directory with diagnostic logging enabled.

**What changed in the engine**

- Added a separate 256-bit AVX-VNNI Q2_0 implementation and connected it to the actual native expert dispatch path, `q2_rows_any`.
- Shared weight unpacking, scaling, floating-point accumulation and token tiling with the existing AVX2 implementation. The AVX2 translation unit and feature detector contain no VNNI instructions; the new translation unit contains VEX-encoded `vpdpbusd`.
- Added compiler capability checks and runtime CPUID/OS YMM-state checks. Existing AVX-512 dispatch retains priority.
- Added the experimental switch `STRATA_Q2_AVX_VNNI=1`. It is off by default. `STRATA_NO_AVX_VNNI=1` and `STRATA_FORCE_AVX2=1` override it.
- Added startup reporting of the selected native Q2_0 backend, four regression tests, and corrected the inaccurate call-chain/performance conclusions in `FORK_NOTES.md`.

**Why VNNI is not the default yet**

The earlier real-weight, single-core microbenchmark found 1.127× throughput on a P core and 1.253× on an E core at four tokens per expert. All 92,160 compared outputs matched the original kernel exactly. That justified implementing the path, but did not justify promising a model-level speedup.

The full engine also spends time paging cold experts, moving data, synchronizing, drafting and verifying tokens. Those costs varied substantially here. The VNNI trial at 10 GiB was slower overall than the AVX2 trial at the same budget; these measurements cannot isolate a causal regression in the kernel, but they also do not establish an end-to-end improvement. The measured AVX2 configuration therefore remains the everyday default.

**Full-model trials**

Each trial used the same six prompts from `bench-m2.py`, temperature 0, reasoning off, maximum 128 generated tokens, repeated three times: 18 requests per trial, 72 in total. This differs from the original script's 256-token cap, so the absolute numbers are not directly interchangeable with older published benchmarks.

| Trial | Mean per-request wall tok/s | Total output tokens / total wall time | Mean engine decode tok/s |
|---|---:|---:|---:|
| Initial resident engine, AVX2, 13 GiB | 10.22 | 7.77 | 14.19 |
| AVX2, 10 GiB — selected | **20.80** | **19.63** | **28.54** |
| AVX-VNNI, 10 GiB | 16.74 | 15.35 | 23.89 |
| AVX-VNNI, 8 GiB | 20.48 | 14.57 | 28.11 |

The aggregate wall rate is useful here because short responses and occasional long stalls can distort a mean of individual rates. At 8 GiB, the first six-prompt pass averaged only 9.61 tok/s, compared with 13.90 tok/s for AVX2 at 10 GiB. The smaller pinned tier was not a clear latency improvement.

These are observations, **not proof of a repeatable 2× speedup**. The initial server was already resident, later trials restarted the process, Windows file-cache state changed, adaptive expert residency and speculation changed during requests, and some generated responses differed. For AVX2 at 10 GiB, pass averages were 13.90, 20.15 and 28.34 tok/s; this warmup effect is itself much larger than the expected whole-engine gain from a small Q2 dot-product optimization.

**Memory pressure remains a real limitation**

During the initial run, available RAM fell to roughly 100 MiB with paging and disk activity. Low available-memory readings and large page-in bursts also occurred with the smaller budgets. Reducing the pinned allocation does not make every new-topic or cold-start request fast. In the final validation, even the two-token Paris answer stalled after loading; the simple Python request decoded at about 12 tok/s. These slower cases are retained in the evidence rather than hidden behind the best benchmark rate.

The printed pool GB/s metric is compressed expert bytes divided by whole row-phase time, not measured DRAM bandwidth. It does not exclude cold-page faults, codebook/cache latency or synchronization. A blanket conclusion that AVX2 arithmetic is the sole remaining bottleneck is unsupported.

If a hardware upgrade is considered later, investigate additional RAM before buying a CPU solely for the AVX-512 label. A 64 GiB configuration is a sensible capacity target to evaluate for this model, subject to motherboard support; no exact speedup has been established. AVX-512 also has multiple subfeatures, and the fast Strata path requires more than basic AVX512F.

**Verification and recovery**

- The four CTest cases passed: explicit VNNI enable, forced AVX2 fallback, explicit VNNI disable, and default-off behavior. They cover token counts 1–8, both projection widths, unaligned row strides, row slices, zero/negative scales, extreme and varied activations, and untouched output regions.
- The final server returned the correct capital of France and generated a Fibonacci function that passed five independently checked cases: 0, 1, 2, 10 and 30.
- All six long-context recall checks passed: depths 10%, 50% and 90%, at approximately 4,793 and 15,954 actual prompt tokens. These are correctness checks, not an exhaustive model-quality benchmark.

`strata-before-changes.zip` contains the original executable, original JSON configuration and original launcher. Model weights were not changed. For rollback, stop the resident service, restore the executable as `build/strata.exe` in the repository, restore the JSON as `C:/strata-models/strata-iq3xxs-native.json`, and start the usual launcher. Do not replace the executable while it is running.

The evidence archive accompanying this report contains request results, timing logs, the benchmark script, code/recall checks and build/test output. The source patch contains the engine changes separately from this machine's configuration adjustment.

Completed source commit: `2a52779aa743a660f4c3420f09a1366014a36002` on `codex/avx-vnni-q2`. The repository working tree is clean. Changes are local; no pull request or remote publication was made.

The resident server's startup log confirms `native Q2_0 rows: AVX2` and a 10.00 GiB pinned tier. The tested VNNI path is ready for further controlled profiling, without requiring another implementation effort.
