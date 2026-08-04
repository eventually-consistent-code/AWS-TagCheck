# Phase 3: request rate awareness — Context

## Locked decisions

- **Op classification, not just reads.** The access-log and CloudTrail
  parsers gain a per-op READ/WRITE classification (write allowlists in
  RESEARCH.md). The parser record grows to carry the op type; the
  existing last-read index keeps taking READS only (fold_reads filters
  op == read), so phase-2 behavior is unchanged.
- **Rates are average-over-sample, labeled as such — never peak.** Logs
  give op counts over their window; the derived req/s is an AVERAGE over
  `max−min event time`, and every surface says so ("peaks likely
  exceed it"). A **minimum-window guard** (default 1 h) suppresses rates
  from too-short samples — counts recorded, no rate emitted below it.
- **Per-prefix, at the run's prefix_depth.** Rates aggregate per
  (container, prefix) using the same prefix truncation the rollups and
  structure engine use, so a fan-out rec lines up with the other
  per-prefix recs. Persisted as a JSON map on `StorageScanRun`
  (`request_rates`), matching the artifacts / structure_recs pattern —
  no per-cell columns (rates aren't per-cell). Schema guard extended.
- **Single parse pass.** `build_access_report` gains `prefix_depth` and
  builds the last-read index AND the rate map from ONE sweep per source
  file — no double gzip-decompress. Report grows a `rates` field.
- **Fan-out is a recommendation, HIGHEST precedence.** A live throughput
  ceiling (503 Slow Down now) outranks latent lifecycle savings, so
  `prefix-fanout` sits first: prefix-fanout > compact-first > date-split
  > straight-lifecycle > zone-split > type-split. It fires only when
  rates were recorded, the window passed the guard, and a prefix's
  estimated read OR write average exceeds `FANOUT_CEILING_FRACTION`
  (default 0.3) of the AWS ceiling (5,500 read/s, 3,500 write/s). The
  rationale names the estimated rate, the ceiling, and the
  average-vs-peak caveat.
- **The v4 out-of-scope note splits.** `REQUEST_RATE_NOTE` currently
  bundles "request-rate fan-out AND churn/expiry" — split it: the
  request-rate/fan-out half retires when rates are recorded; the
  churn/expiry half stays (that's phase 4). `out_of_scope_notes` grows a
  `rates_recorded` arg alongside `types_recorded`.
- **Scope boundary with phase 4.** This phase delivers the rate signal +
  the fan-out rec (the one thing the signal directly unlocks). Phase 4
  (#39) consumes rates to refine the OTHER kinds (read-verified zone
  splits, churn/expiry, confidence labels). No churn advice here.
