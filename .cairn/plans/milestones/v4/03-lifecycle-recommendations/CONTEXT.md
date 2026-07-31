# Phase 3: lifecycle recommendations — Context

## Locked decisions

<!-- decisions made for this phase; on conflict these WIN over tracker issue text -->

- Carried from phase-2 verification: since Sept 2024 AWS's DEFAULT lifecycle
  behavior excludes objects <128 KiB from all transitions. Generated
  lifecycle rules must set `ObjectSizeGreaterThan` explicitly so the rule
  matches what the projections priced (and never silently archives tiny
  objects the floor math excluded).
- Carried from phase-2 verification: Intelligent-Tiering sources may only
  transition to One Zone-IA / Glacier IR / Glacier Flexible / Deep Archive —
  never Standard-IA. Rule generation must enforce the same matrix the
  projector uses (INT_ALLOWED_TARGETS in projections.py).
- **Two generation surfaces** (research-driven): prefix-level artifacts
  (lifecycle configs, tiering configs, expiration rules) generate from the
  persisted run in report-only mode; key-level artifacts (delete-objects
  chunks, batch-ops copy manifests) stream during a scan — rollups keep no
  keys, and that stays true (aggregate-first is a phase-1 locked decision).
- **Generated lifecycle configs are COMPLETE per bucket** — PUT replaces
  the whole config, so emitting a delta would silently destroy existing
  rules. Every generated config file carries a header comment saying so.
- **Mass delete = lifecycle Expiration (recommended, async) or chunked
  delete-objects JSON (immediate, ≤1,000 keys/request)** — Batch
  Operations cannot delete objects, only their tags; never generate a
  batch-ops "delete" job.
- **Generator validates before writing**: 30d IA minimum, ≥30d IA→Glacier
  chaining gap, Expiration > transitions, explicit ObjectSizeGreaterThan,
  INT transition matrix. Invalid combinations are a generation error, not
  a warning in a broken file.
- Artifacts land in a user-named output directory with an APPLY.md
  explaining each file's aws-cli apply command and its blast radius;
  nothing is ever applied by the tool (milestone posture).
