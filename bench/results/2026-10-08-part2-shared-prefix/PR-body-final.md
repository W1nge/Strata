Pinning document A, switching to an edited document B, and returning to A can leave both parked snapshots permanently pinned. With two conversation-cache slots, later conversations can no longer be parked even when the byte budget has room. Their follow-ups repeatedly read the full prompt.

A valid explicit prefix request now releases older pins before cache lookup/take, across the live checkpoint chain, batch slots, and parked conversations. Token prefix, boundary, image identity, and steering mode must match to retain a pin. This changes retention metadata only: old snapshots remain reusable until normal eviction, and the selected prefix stays protected. It implements the documented rule that a new shared prefix replaces the previous one; no new flags or hardware defaults are added.

Validation:

- `conversation_cache_test`: 4211 checks pass, including stale-pin slot exhaustion, replacement, unchanged accounting, incoming-pin retention, and token/image/mode identity. Compiled and run on Windows/MSVC both in the integration checkout and on this branch based on `6674a00`.
- `conv_cache_test`: all 17 retention checks pass on this branch. MSVC/CUDA integration build succeeds.
- Full-model Windows tests used a local integrated 0.1.40.4 build, Qwen3.8-Flash-Next IQ3_XXS, 8192 context, INT8 KV, spec8, RTX 2080 Ti + P100, driver 537.13. With identical opt-in cache settings (3 checkpoints, 1536 MiB, 2 slots, 6144 MiB RAM floor), eight returning turns after document replacement went from 0/8 restored to 8/8 in both patched runs; their total HTTP time was 159.60 s before and 5.77 / 6.51 s after. All 17 corresponding response texts and token counts matched. The source-edit and tool-result-edit checks returned the updated values.
- Six existing code-generation/editing regression tasks passed and matched the previous integrated version's response text.

The model runs include other local integration patches (including the separately submitted Windows host-staging page release). The clean branch was checked with the CPU tests, not a separate full-model run. These measurements describe a repeated-prefix workload on one Windows setup; Linux/HIP, image requests, full layer-split execution and concurrent batch operation were not runtime-tested here. The local cache budget is not proposed as an upstream default.

Merge compatibility: a temporary clean merge with current main `fb58e0d` (0.1.41) also passes `conversation_cache_test` (4221 checks, including ten new upstream checks) and all 17 `conv_cache_test` checks on MSVC. This does not constitute a full-model validation of 0.1.41.
