# Mapped helper output and code-edit latency

Measurements from an i7-13850HX, 32 GB RAM, RTX 2080 Ti 22 GiB and Tesla P100 16 GiB on Windows WDDM, driver 537.13. See the [report](../../../docs/performance/PART2-MAPPED-OUTPUT-2026-10-08.md) for the workload, limitations and installation decision.

Thirteen serial starts produced 137 checked responses. A matched engine repeat changed four long-code workloads from 89.41 to 90.42 tokens/s (+1.13%), with identical output. The new engine plus short-read1024 reduced two full-module edit requests from 50.75 to 34.78 seconds; their output length also changed. The general suite had no measured speedup, so its installed config and executable were retained.

`receipt.json` records the hashes of the copied evidence; executables and model weights are excluded. `install-receipt.json` identifies the installed coding executable and the retained general config. `final-local-checks.json` records the driver, power limits and stopped benchmark processes. The original binary remains available for rollback.

Run `python summarize.py` here to recompute the saved metrics. Reproduction commands are in the report. Benchmark and installation scripts preserve the original local paths; use fresh output labels and update paths before running them elsewhere.
