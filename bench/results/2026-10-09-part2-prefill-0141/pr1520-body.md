On Windows, prefill copies expert weights from file mappings into the Stager's buffers, but the source pages can remain in the process working set after the copy. With a resident CPU expert pool, these duplicate pages can consume the remaining RAM during a long prompt.

Keep the source and expert identity on stable-pointer jobs and call the existing `ExpertSource::release` after the host copies complete, before publishing each job as ready. Stable pointers still use `memcpy`; transient blobs keep 0.1.41's `copy_blobs` batching. The mapping, resident RAM copies and CUDA-registered buffers remain intact. This uses the existing opt-in `STRATA_FILE_RELEASE=1`; it adds no setting or numerical change.

Validation:

- Rebased onto 0.1.41 (`fb58e0d`); three files, +22/-13. The Stager definition matches the model-tested integrated build byte for byte.
- Windows, CUDA 12.4.131, SM60/SM75, RTX 2080 Ti + Tesla P100, driver 537.13: engine build, `file_expert_source_test` and `gr_parity --selftest` pass.
- The integrated 0.1.41 build passed a bounded 100-response comparison/regression, including scalar mmap staging, batched unbuffered reads, shared-prefix replacement and code generation/editing. Matching responses and token counts were retained. This is integration validation, not a separate full-model run of this standalone PR branch.
- The original 0.1.40.4 experiment measured median available RAM during long prompts increasing from about 0.45 to 11.40 GiB. That measurement concerns source-page release. The newer batched-read speedup belongs to upstream 0.1.41 and is not claimed as this patch's result.

Full model validation was on this Windows helper-GPU configuration and native IQ3_XXS pack. Other backends, GGUF-in-place staging and concurrent layer-split batches were not exercised by those model runs.
