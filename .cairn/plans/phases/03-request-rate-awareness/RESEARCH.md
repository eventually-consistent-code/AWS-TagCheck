# Phase 3: request-rate awareness — Research

Researched: 2026-07-31 (design analysis; AWS ceilings carried from the
milestone-4 phase-5 storage-layout research, still current).

## AWS per-prefix request ceilings (from milestone-4 phase-5 research)

- S3 sustains **≥3,500 PUT/COPY/POST/DELETE and ≥5,500 GET/HEAD
  requests/sec per partitioned prefix**; no limit on prefix count, so
  parallelizing across N prefixes scales aggregate throughput ~N×.
- Scaling is gradual — S3 repartitions under sustained load and returns
  transient `503 Slow Down` while it does. So the fix for a hot prefix
  is spreading the keys across more prefixes (fan-out).
- Below the ceiling, prefix layout is a cost/lifecycle concern, not a
  performance one — which is exactly why v4 deferred fan-out advice
  until request telemetry existed.

## The estimation honesty problem (the load-bearing decision)

- Access logs / CloudTrail give **op COUNTS over the sample window**, so
  the derived figure is **average req/s over that window**, NOT the peak
  per-second the AWS ceiling is measured against. Peaks on bursty
  workloads far exceed the average.
- Consequence: an average that is even a modest FRACTION of the ceiling
  implies peaks that likely breach it. So the fan-out trigger fires on a
  fraction of the ceiling (default 0.3), and every output states the
  figure is "estimated average over the <window> sample; peaks likely
  exceed it".
- **Minimum sample window guard**: a tiny window (a few minutes of logs)
  divides a handful of ops into a garbage rate. Require a minimum
  observed window (default 1 hour, from max−min event time) before any
  rate is trusted; below it, record the counts but emit no rate/fan-out.

## Reuse & fit

- The access-log and CloudTrail parsers already extract per-op events
  with (bucket, key, time). Phase 3 extends them to classify each op as
  READ or WRITE (a small allowlist per source) so rates cover both
  axes; the existing last-read index keeps taking READS only.
- Rates aggregate per (container, prefix) at the run's prefix_depth — the
  same prefix view the structure engine uses — so a fan-out rec lines up
  with the other per-prefix recs.
- Persist as a JSON map on StorageScanRun (the artifacts / structure_recs
  pattern); no per-cell columns (rates are per-prefix, not per-cell).

## Write-op allowlists (to add)

- Access logs: writes = `REST.PUT.OBJECT`, `REST.POST.OBJECT`,
  `REST.COPY.OBJECT`, `REST.DELETE.OBJECT` (reads stay `REST.GET.OBJECT`).
- CloudTrail: writes = `PutObject`, `CopyObject`, `DeleteObject`,
  `CompleteMultipartUpload` (reads stay GetObject/SelectObjectContent).
