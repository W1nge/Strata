# Strata 0.1.41 prefill evidence, 2026-10-09

The [report](../../../docs/performance/PART2-PREFILL-0141-2026-10-09.md) describes the hardware, adopted configuration, measurements, limitations, installation and rollback.

This archive contains seven cold-input runs (77 responses), one final session replay (17 responses), and one final coding replay (six responses). All nine model processes ended. The selected change is a 12 GiB resident budget enabling upstream 0.1.41's existing memory-based unbuffered I/O selection and batched reads; it is not a new upstream default or a new decode speedup.

The seven measured cold-input labels are `baseline-a`, `baseline-b`, `v141-default-a`, `v141-direct-a`, `v141-direct-b`, `v141-direct-share-a`, and `v141-direct-short128-a`. Their actual execution order is in the report. Other `*-base.json` files are prepared configurations, not evidence of additional runs. `previous-coding-result.json` and `previous-sessions-result.json` are earlier reference outputs and are not included in this run's 100 responses.

Recompute from this directory without loading a model:

```text
python summarize.py baseline-a baseline-b v141-default-a v141-direct-a v141-direct-b v141-direct-share-a v141-direct-short128-a
python verify_regressions.py
```

The first command prints the cold comparison. The second revalidates recorded session/coding outputs and rewrites the same `regression-summary.json`. Both readers accept raw or gzip files. Timing fields ending in `_s` are seconds; engine fields ending in `_ms` are milliseconds. Disk counters are system-wide and include other activity and sampling-boundary error.

`server-tests.log` records the initial host-dependent vision fixture failure; `server-tests-final.log` and `verification-receipt.json` record the completed verification. `daily-sync.log` records initial merge conflicts; `daily-sync-success.json` records the resolved source synchronization. `installation.json`, `installed-coding-config.json`, `rollback-coding-config.json` and `postflight.json` identify the installed and retained files.

`manifest.json` records raw and stored SHA256 values. Gzip timestamps are fixed, and `.gitattributes` disables text conversion so Git preserves evidence bytes. Executables, model weights and object files are excluded. Scripts that build, install or run models remain as historical reproduction material; the two summary commands above are the offline verification entry points.
