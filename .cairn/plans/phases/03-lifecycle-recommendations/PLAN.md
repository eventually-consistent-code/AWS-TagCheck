---
issues: [23, 24, 25]
---
# Phase 3: lifecycle recommendations — Plan

Goal: turn the phase-2 analysis into ready-to-apply artifacts — delete
manifests, lifecycle policy JSON, tiering configs, batch move plans —
generated, validated, never applied. Two surfaces per CONTEXT: prefix-level
artifacts from the persisted run; key-level manifests streamed during a scan.

## Tasks

### Issue #24 — age-out rule generator (lifecycle policy JSON)

1. `tagmanager/storage/lifecycle_gen.py` — generate one COMPLETE lifecycle
   config per bucket from the latest run's rollups + the band→target map
   (same `default_band_targets`/`--age-out-map` path as projections, INT
   matrix enforced): `Rules` with Filter (`And` of Prefix +
   `ObjectSizeGreaterThan: 131072` explicit), Transitions per band, IDs
   from prefix+band. Validator refuses invalid outputs: IA before 30d,
   IA→Glacier chain gap <30d, Expiration ≤ transition days, >1,000 rules,
   INT→IA. Header comment in every file: "PUT replaces the entire config".
2. CLI `--emit-lifecycle DIR` (report-only mode, works off latest run):
   writes `<bucket>.lifecycle.json` per bucket + APPLY.md with the
   aws-cli apply command and blast-radius note. Unit tests: schema shape,
   validator rejections, small-object filter always explicit.

### Issue #23 — deletion candidate manifests

3. Expiration-rule flavor: `--emit-lifecycle` gains `--delete-after DAYS`
   — adds Expiration rules for stale prefixes (validated > transition
   days) as the AWS-recommended async mass-delete path.
4. Immediate flavor, streamed at scan time: `ManifestEmitter` hooked into
   the scan loop — stale objects (age ≥ last threshold) stream into
   chunked `delete-objects` JSON files (≤1,000 keys, `Quiet: true`),
   `--emit-delete-manifests DIR` (scan mode only). APPLY.md documents
   per-chunk apply, versioned-bucket delete-marker caveat, and that
   manifests are point-in-time proposals. Tests: chunk boundary at 1,000,
   JSON payload shape, stale predicate uses scan thresholds.

### Issue #25 — tiering configs + batch move plans

5. `tagmanager/storage/tiering_gen.py` — Intelligent-Tiering config per
   bucket/prefix ({Id, Status, Filter, Tierings}) with 90/180d minimums
   validated; `--emit-tiering DIR` (report-only mode). APPLY.md notes the
   config only affects objects already in INTELLIGENT_TIERING class.
6. Batch-ops copy plans, streamed at scan time: stale objects into
   `S3BatchOperations_CSV_20180820` manifests (URL-encoded keys, no
   version IDs — scan doesn't enumerate versions; >5 GB objects skipped
   into a sidecar list, counted), plus a generated create-job command
   block (S3PutObjectCopy → target class from the band map) in APPLY.md.
   `--emit-batch-copy DIR` (scan mode only). Tests: URL-encoding of
   commas/spaces/unicode, 5 GB skip list, CSV shape.

## Notes

- Task order: 1–2 (#24) first — the generator/validator core the other
  artifacts reuse; then 3–4 (#23), then 5–6 (#25).
- All generators are pure functions over (rollups | object stream,
  thresholds, targets) returning artifact dicts/lines; file writing stays
  in the CLI layer. Validation failures raise, tested explicitly.
