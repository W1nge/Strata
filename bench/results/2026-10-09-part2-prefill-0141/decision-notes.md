# 0.1.41 cold-prompt experiment decisions

- Frozen source: merged commit `26a119378f2fb28525dad29f00ada36dba9e249c`; engine SHA256 `9fcc7cd90f0e8dad13463846e464f5b54fbe262fc9eeff90e98797de403dbae2`.
- Preserve NVIDIA 537.13, RTX 2080 Ti 310 W / Tesla P100 250 W, and the primary/helper split. No driver changes or overlapping model/build runs.
- New engine defaults alone did not improve this fixture: 158.090 s of cold prefill versus 150.083 s for the installed engine. All 11 requests, responses and token counts matched.
- The full resident helper configuration has no `--resident-budget-gib`, so it never selected the unbuffered path. A 12 GiB upper budget keeps the complete 10.84 GiB CPU complement, triggers the existing memory-based I/O choice, and makes 0.1.41's batched reads and mapping closure applicable.
- With that budget, the first candidate took 89.6097 s of cold prefill. Physical C: reads were approximately 103.67 GiB versus 95.73 GiB in the baseline; this is faster I/O, not fewer bytes read. The source's `files N blobs` counter is not comparable across the scalar and batched copy paths.
- Explicit CPU share with a 3072-token limit took 87.0543 s, but the first 2067-token source regressed from 10.3189 to 12.5385 s. A few percent aggregate difference with mixed per-case results does not justify an extra numerical path/configuration change.
- Default CPU share is armed in helper mode because the engine's `multi_gpu` predicate denotes a layer split. `--short-read 1024` handles the small prompts through decode windows before that batched path; an ON startup message is not proof every short prompt used CPU sharing.
- With `--short-read 128`, 422-token prompts rose from 3.7606/3.7252 to 7.2023/6.9722 s. Retain 1024. The 884-token first prompt stayed approximately 8.2 s; the second was faster, but the small-input regression is substantial.
- `STRATA_STAGE_PIN=0` remains explicit: upstream fb58e0d disabled it after an asynchronous stage-buffer reuse failure. Do not re-enable it in this experiment.
- The no-P2P peer prefill mode still cannot share the current helper expert cache configuration. It was not measured here.
- Required remaining adoption gates at the time of this note: repeat installed baseline then the direct candidate; replay the frozen multi-session/prefix fixture; run the existing coding suite; preserve the user's audit edit and the old executable/configuration on installation.

## Completed adoption and publication

- Both later runs completed. The two baseline runs total 305.1394 s of cold prefill; the adopted pair total 179.1151 s, a 41.3006% reduction. Complete request time, including each warm-up request, fell by 40.7751%.
- All 77 cold-fixture responses passed and matched their corresponding prompts, answers and token counts. The 17-session replay and six coding tasks also passed, for 100 API responses across nine model loads. All six coding outputs were byte-identical to the earlier installed version; long-code decode was 91.6258 token/s, with no new decode speedup claim.
- Final server/tokenizer/idle tests passed 283 checks after fixing the host-dependent vision GPU-order fixture. C++ cache tests and both selected CTest cases passed. The full-model runs remain limited to the documented Windows SM60/SM75 helper configuration.
- The selected executable and resident-budget 12 GiB configuration were installed once; the complete 10.84 GiB CPU complement is retained. Installation and rollback identities are in installation.json. The user's audit edit is unchanged.
- Daily source integration completed at 62a04cc after resolving the earlier logged merge conflicts. PR #1520 was rebased and pushed at 83d4f1a; the one-line vision test correction was submitted as PR #1632 at 9e1b2ec. Both were OPEN/MERGEABLE when inspected, with no CI results reported.
- Model and test work has ended. Postflight and repository archiving only record the completed run; they do not reopen the performance sweep.
