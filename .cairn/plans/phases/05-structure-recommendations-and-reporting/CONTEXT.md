# Phase 5: structure recommendations and reporting — Context

## Locked decisions

- **Four recommendation kinds, threshold-constants, no ML**: date-split
  (>70% cold bytes AND fresh writes present), straight-lifecycle
  (entirely stale prefix — defer to --emit-lifecycle), compact-first
  (>50% of a stale prefix's objects under 128 KiB — never recommend
  transitions there), zone-split (same-level storage-class mix or
  strongly bimodal ages). Thresholds are named module constants.
- **No performance fan-out advice** — scans carry no request-rate
  telemetry, and below S3's per-prefix request ceilings layout is a
  cost/lifecycle concern. Churn/expiry-in-place advice likewise out
  (needs write telemetry). Both stated in output, not silently absent.
- **Owner dimension is opt-in** (`--rollup-owners`): cells gain an owner
  key component + additive column (schema guard extended). Off by
  default — owner cardinality can explode cells. Recommendations group
  by owner only when the run recorded it.
- **Move plans are two-pass and key-level**: scan → recommendations
  persist with the run → rescan with the move-plan emitter streaming
  old-key→new-key CSVs (date-split injects year/month from
  last-modified; zone-split prefixes a cold/ zone). Copy+delete
  semantics and point-in-time caveats in APPLY.md; the tool never moves
  anything.
- **Report surfaces: two, both thin.** Standalone storage HTML report
  (stdlib rendering, html.escape everywhere, same visual family as the
  classic report) composed from the SAME data objects the CLI printers
  use; and a web-UI /storage page via the ui_router pattern showing the
  latest run. The classic EC2 violations report is untouched.
- **Every surface carries the age-basis label and estimate disclaimer**
  (carried from phases 2/4); the artifacts index section lists which
  emit directories a run produced, from CLI-recorded metadata, not
  filesystem guessing.
- **Checker-locked amendments (2026-07-31)**: cell key is ALWAYS
  5 elements (owner "" when the flag is off — conditional shapes break
  unpackers); recommendations key per prefix with owner as attribution
  only (never N recs for one prefix); every additive column
  (owner, artifacts, structure_recs) is covered by schema_current;
  persisted recs cap at top-N by $ at stake; move-plan recs load at
  emitter construction from the latest COMPLETE run; rewrites skip
  already-conforming keys; data-type grouping declared out of scope in
  output (no content-type signal); "fresh writes" rationale reads
  "fresh activity" on access-aware runs.
