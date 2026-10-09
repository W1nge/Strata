# Prefill: helper VRAM cache as the prompt path source (same-day A/B, 2026-10-09)

One serial 11-request fixture per arm, a fresh engine process each, driver 537.13, 2080 Ti 310 W + P100 250 W.
Candidate = the same exe plus STRATA_PREFILL_HELPER_SOURCE=1: a blob a helper VRAM cache holds is copied from
that cache instead of being read from the files again.  Both arms answered every request with the expected value
and cache_n == 0 on every cold case.  Raw logs, the configs and every result JSON are archived here (`manifest.json` carries the sha256 of each one,
and `summary.json` names the runner directory they were copied from).

| request | prompt tokens | baseline prefill ms | candidate prefill ms | delta | baseline tok/s | candidate tok/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| warm | 24 | 439 | 384 | -56 | 55 | 63 |
| records-small-r1 | 422 | 3893 | 3779 | -114 | 108 | 112 |
| records-medium-r1 | 884 | 8414 | 8225 | -189 | 105 | 108 |
| source-2k-r1 | 2067 | 12572 | 6301 | -6271 | 164 | 328 |
| source-3k5-r1 | 3500 | 13291 | 6878 | -6413 | 263 | 509 |
| records-5k-r1 | 5127 | 10871 | 7298 | -3573 | 472 | 702 |
| records-5k-r2 | 5127 | 10672 | 8434 | -2239 | 480 | 608 |
| source-3k5-r2 | 3500 | 9871 | 6283 | -3588 | 355 | 557 |
| source-2k-r2 | 2067 | 9235 | 5880 | -3355 | 224 | 352 |
| records-medium-r2 | 884 | 8490 | 8343 | -147 | 104 | 106 |
| records-small-r2 | 422 | 3784 | 3861 | +77 | 112 | 109 |

All 11 requests: 91.5 s -> 65.7 s of prefill (-28.3%).

Disk: the run read the same 5422 blobs in both arms, 142131.6 MB with the files as the source and 50077.8 MB with the
helper cache as one - 92.1 GB (64.8%) of the reads did not touch the SSD.

Requests at or below 1024 prompt tokens take the short-chunk path (the CPU pool and the helper GPU compute the
experts; no blob is streamed), so they are unchanged by this option; from 2067 tokens on every request streams the
full non-resident expert set and the helper answers all of it (8782 blobs, 14631.5 MiB per request).

## Where the time went after the change

`STRATA_PREFILL_TIMING=1` on the candidate (`diag-timing-engine.log`) shows the copies and the GPU work now running
against each other instead of in series - `wait copy` is down to 4-7% of the chunk while the GPU timeline is the wall:

| chunk tokens | wall ms | GPU timeline ms | host staging ms | largest GPU stages (ms) |
| ---: | ---: | ---: | ---: | --- |
| 2060 | 5314 | 5300 | 4699 | dequant 1959, gemm gate/up 557, combine 485, hc read 476, gather 442, wait copy 393 |
| 5120 | 6209 | 6178 | 9160 | dequant 1311, hc read 958, gemm gate/up 777, gather 584, qsa attn 409, wait copy 298 |

The 5120-token chunk's staging (9160 ms) already overlaps the next chunk. Note the shape of these numbers: every chunk
above 1024 tokens dequantizes and stages the same 8782 blobs (14631.5 MiB) no matter how many of them the prompt
routes to, which is why the chunk cost starts near 6.2 s and grows only slowly with the token count.

## What this says about the next step

- Chunks at or below 1024 tokens never reach `copy_blobs` (the CPU pool and the helper compute those experts), so the
  option cannot change them - at 884 tokens the same fixture measures 8272 ms with the share and 8303 ms without.
- From 2067 tokens on, the streamed set is exactly the 8782 blobs the helper holds, so the helper answers all of it and
  the remaining cost is the device-to-host transfer (3.25-3.28 GB/s on this card's PCIe 3.0 x4 link) and GPU dequant.
- Keeping the same experts in host RAM instead is not available here: the helper set (14.29 GiB) plus the resident RAM
  complement (10.84 GiB) does not fit the machine's 31.6 GB.
- Eight concurrent device-to-host streams were measured and changed nothing; the x4 link is already saturated.

