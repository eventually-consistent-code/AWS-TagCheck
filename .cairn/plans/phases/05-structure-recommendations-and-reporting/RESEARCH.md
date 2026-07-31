# Phase 5: structure recommendations and reporting — Research

Researched: 2026-07-31 (deep fan-out: repo report-surface map + storage
layout best-practices sweep, AWS docs + published engineering sources).

## Report surfaces (repo map)

- Classic HTML report: `aws_tag_manager.py:202` render_html_report —
  stdlib string building, inline table styling, write at :297, S3 upload
  at :357. EC2-violations shaped; storage sections don't belong inside it.
- Web UI: `tagmanager/app/ui.py:14` ui_router factory (Jinja2 + htmx),
  templates at `tagmanager/app/templates/` (base.html carries the only
  shared CSS, inline), routes for dashboard/resources/violations, tests
  in `tests/test_ui.py` using the latest-run scoping pattern.
- Storage CLI already has six print_*/write_* section writers — the HTML
  report can compose the same underlying data objects.

## Layout best practices (grounded, cited in agent output)

- **Prefix layout is a lifecycle/cost concern, not performance**, until a
  workload nears 3,500 write / 5,500 read req/s per prefix — no request
  telemetry in our scans, so performance fan-out advice is OUT of scope.
- **Lifecycle rules are prefix-scoped** → any subset needing different
  treatment must live under its own prefix. Mixed-age data under one
  prefix is THE anti-pattern the engine should catch.
- Community zoning norm: hot ≤30d, warm 30–90d, cold 90d+; zone prefixes
  (raw/stage/archive-style) each carrying exactly one rule; date
  partitioning (year/month, Hive-style fine) for append-only data,
  ≥1 GB per partition target.
- **Small objects: 128 KB is the hard industry line** (default transition
  exclusion, billable floors, 40 KB Glacier overhead). AWS's own worked
  example: 10M × 1 KB objects = $0.23/mo in Standard but $16/mo if
  transitioned as-is; compacted first, $0.13/mo. Compact/tar BEFORE
  tiering, aggregated to the partition's time granularity.

## Signals → recommendations (engine mapping)

With per-prefix rollups (bytes/count by band+class, small-object counts):

1. Cold-heavy prefix (>70% bytes past the first threshold) WITH fresh
   writes present → **date-split** (`prefix/year/month/`) so transitions
   can scope to aged partitions.
2. Entirely stale prefix, no fresh band → **straight lifecycle rule**
   (point at --emit-lifecycle, no reorg needed).
3. Stale prefix dominated by small objects (>50% of count under 128 KiB)
   → **compact/tar first**, never a transition rule.
4. Same-level mix of storage classes or strongly bimodal ages →
   **hot/cold zone split**, because prefix-scoped rules can't treat the
   mix cleanly.
5. Churn-based advice (expire-in-place for short-lived data) needs write
   telemetry a single scan lacks — out of scope, noted honestly.

## Gaps carried into design

- Rollups don't persist owner — "who interacts with it" grouping needs an
  opt-in owner dimension on cells (cardinality risk if default-on).
- Key-level move manifests need scan-time keys (same constraint as phase
  3): two-pass flow — scan → recommend → rescan with a move-plan emitter
  keyed off the recommendations.
