# Phase 3: lifecycle recommendations — Verification

Verified: 2026-07-31

## Goal-backward check

Phase promise: turn the analysis into ready-to-apply artifacts — delete
manifests, lifecycle policy JSON, tiering configs, batch move plans —
generated and validated, never applied by the tool.

Live end-to-end exercise (real CLI, real sqlite, real files; mixed bucket
of old-large / old-huge(>5 GB) / old-tiny-with-unicode-key / mid-age /
fresh objects, custom `--age-bands 90,365`):

- **Lifecycle configs**: stale prefixes got rules with the full 90→IA /
  365→Glacier ladder, explicit `ObjectSizeGreaterThan: 131072`,
  `--delete-after 730` Expiration; the fresh prefix correctly absent.
- **Delete manifests**: exactly the three stale keys captured (unicode/
  comma key intact in JSON), chunk shape `{"Objects": [...], "Quiet": true}`.
- **Batch-copy manifests**: stale ≤5 GB keys in CSV with URL-encoded
  commas/spaces/unicode; the 6 GiB object routed to the `.skipped.txt`
  sidecar, not the manifest.
- **Tiering configs**: two per-prefix configs with ARCHIVE_ACCESS 90d /
  DEEP_ARCHIVE_ACCESS 180d.
- **APPLY.md present in every artifact directory** — apply commands,
  blast-radius (PUT replaces whole config), delete-marker and
  already-in-INT caveats, create-job recipe with role trust principal.
- Exercise initially "failed" on a 10 GiB test object missing from the
  copy CSV — script error, not code: the object was correctly in the
  >5 GB sidecar. Fixed the exercise, all checks pass.

Locked decisions honored: two generation surfaces (prefix-level from
persisted run; key-level streamed at scan — report-only mode refuses
key-level flags with the reason), complete-config-per-bucket, hard
validation raising on IA<30d / chain gaps / bad Expiration / missing
size filter / INT-illegal targets, nothing ever applied.

## Gates

- Tests: 145 passed, 0 failed (22 new this phase).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flags on 23/24/25 normalize
  with this file; all other issues ok. Open issues in phase: none.
- TDD frontmatter: none declared.
- Ledger: three issues with commit ranges (fbe8c96..368bacd,
  368bacd..1c761fd, 1c761fd..910e23f).

## Result

PASS.

## Deviations

None — all six PLAN.md tasks landed as written.
