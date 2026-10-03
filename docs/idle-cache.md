# Idle conversation cache

Opt in with these engine arguments:

```text
--cache-idle-seconds 180
--cache-expire-seconds 3600
--cache-disk-dir C:/strata-models/cache/kv
```

The timer starts when the last generation finishes, including cancellation and
STOP draining. Health/status requests do not refresh it. A generation in progress
cannot be offloaded or expired. Any later generation resets the timer after it
finishes. This is an engine-wide policy for its current shared cache, not a
separate timer or permanent archive for each client conversation.

At 180 idle seconds the engine writes one snapshot of its session/MTP state arenas
and CPU checkpoint state, commits the file, then releases their physical VRAM and
CPU vectors. Model weights remain loaded. CUDA virtual addresses and small,
constant initialization tables remain available so captured graphs can be reused.
At 3600 idle seconds since the last generation finished, it deletes the snapshot
and invalidates the cache. It does not wait an additional hour after offloading.
Released arenas are allocated again on the next request.

Restoration preserves the original numerical storage format. Snapshot blocks are
checksummed; missing/truncated/corrupt files cause a fresh Prefill. Write failure
retains the in-memory cache and retries later. Allocation failure on wake returns
an error and keeps the disk snapshot available for a retry. File deletion failures
are logged and retried during expiration. Only this feature's files are cleaned.

`GET /v1/status` has a `cache` object with `state`, configured timers, disk bytes,
released arena/host bytes, and the last transition duration. `operation_ms` for a
restore is additional to the engine's prompt-processing timing; client latency
includes both. Released bytes refer to allocator resources, not a guarantee that
Windows working-set or system-cache counters drop immediately.

Snapshots are temporary and process-local. Normal engine shutdown removes its
snapshot. A crashed/stopped process cannot run expiry timers; on the next engine
startup, expired abandoned snapshots in the configured directory are cleaned.
There is no cross-restart cache import. Client chat history is unaffected.

Currently supported: a single GPU with CUDA VMM, fully resident KV (`--kv-resident
0`). FP16/INT8/Q4 storage is copied without conversion, but the local model-level
validation used FP16 at 32K. Layer splits, remote expert GPUs, and KV streaming
are rejected with this feature. `--cache-idle-seconds 0` disables it and retains
the normal cudaMalloc path. The expiry duration must exceed the offload duration.

At 32K on the validated setup, about 1016 MiB of state/workspace VRAM can be
released. Disk bytes also include CPU checkpoints; entire allocated arenas are
saved, so a short conversation does not produce a proportionally small file.
This is a memory-management policy, not an active Prefill throughput optimization.
