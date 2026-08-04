# Phase 1: data type signals — Verification

Verified: 2026-07-31

## Goal-backward check

Phase promise: the optimizer knows WHAT the data is, not just how old —
an extension-derived type dimension and type-aware recommendations,
closing v4's declared REQ-11 data-type gap.

Live end-to-end drive (real fs tree, real CLI, real sqlite): a
mixed-type prefix (logs + data + docs files, all aged 500 days) scanned
with `--backend fs --rollup-types --csv-out`:

- **CSV carries the data_type column, populated**: header now
  `...,owner,data_type,object_count,...`; values `data`, `docs`, `logs`
  present.
- **Recommendations are type-aware**: `--recommend-structure` on the
  saved run produced a rec with `top types: data, docs, logs`. (It was
  compact-first, not type-split — the demo files are tiny so small-object
  precedence correctly wins; the point proven is that type ATTRIBUTION
  surfaces on any rec kind, per the plan.)
- The full path is proven: classify_key → always-6-tuple rollup →
  data_type persisted → CSV column → recommendation top_types.

Locked decisions honored: coarse extension taxonomy from a constant map
(compound suffixes win, case-insensitive, no-ext → other — unit-tested);
opt-in `--rollup-types` threaded through CLI/services/jobs/web-target
form exactly like `--rollup-owners`; always-6-tuple cell key with every
unpacker updated in one commit (reconciled against the post-service-layer
code first); type-split LAST in precedence; the out-of-scope note now
conditional on whether types were recorded.

## Gates

- Tests: 222 passed, 0 failed (10 new this phase; the three v4 5-tuple
  key assertions moved to 6-tuple — key shape only, behavior untouched).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flags on 35/36 normalize with
  this file. Open issues in phase: none. TDD frontmatter: none.
- Ledger: both issues with commit ranges (6cc136d..aeb5663,
  aeb5663..de2da41).
- Schema guard extended for `data_type`; the web-UI stale-schema notice
  and the CLI's guard-before-scan both cover the new column (existing
  tests).

## Result

PASS.

## Deviations

- type-split's reachable window is narrow by the plan's own precedence
  (it is strictly last): fresh-dominant, single-class, thin-cold,
  type-mixed prefixes. Documented in the tests and the #36 close note —
  by design, not a defect. Type attribution (`top_types`) surfaces on
  every rec kind regardless, which is where the day-to-day value lands.
