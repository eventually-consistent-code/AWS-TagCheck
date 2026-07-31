# Phase 4: multi-backend expansion — Verification

Verified: 2026-07-31

## Goal-backward check

Phase promise: the same scan → age bands → cost → artifacts pipeline over
Azure Blob, GCS, and SMB/local filesystems, plus true last-READ awareness
where each platform can give it.

- **Live fs exercise** (real files, real CLI, real sqlite): a tree with a
  500-day-old file and a fresh file scanned via `--backend fs` — correct
  `>365d` / `<90d` banding, atime picked up natively, summary labeled
  "age = access-aware". One cosmetic defect found: `s3://` hardcoded on
  oldest-object lines for every backend — traced (trace-cb16d279, issue
  33), fixed in 0c06c57 with per-backend schemes, re-run clean.
- **Azure/GCS providers** (mock-SDK tests — cloud creds unavailable):
  BlobProperties/Blob field mapping exact, tiers verbatim
  (HOT/COOL/COLD/ARCHIVE, STANDARD/NEARLINE/COLDLINE/ARCHIVE),
  `last_accessed_on` carried on Azure, GCS never sets last_accessed;
  missing-SDK constructor raises install-hint errors (tested).
- **Backend routing + isolation**: `--backend` selects provider, run
  lookup, and pricing snapshot; an s3 report-only run refuses when only
  azure runs exist (tested). Azure requires `--account-url` (tested).
- **Access enrichment**: real-format server-access-log records parsed
  (GET-only, URL-decoded keys, two-token timestamps); a stale-by-mtime
  object read 2 days ago flips to `<90d` through the full CLI path
  (tested). Read-hot-never-edited unit case in the fresh band. All
  outputs label age basis; access-aware caveat on report-only paths via
  the persisted run flag.
- **Pricing snapshots**: azure (eastus) and gcs (us-central1) load and
  answer rate/duration questions; provenance flags recorded in-file
  (Azure Cold soft-confirmed; GCS monthly derived from hourly).
- Locked decisions honored: lazy optional SDKs (base install boto3-only),
  fs has no pricing (message, not zeros), platform tier names verbatim.

## Gates

- Tests: 167 passed, 0 failed (22 new this phase).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flags on 26/27/28 normalize
  with this file; all other issues ok. Open issues in phase: none.
- TDD frontmatter: none declared.
- Ledger: three issues with commit ranges (8ca0296..5fc6925,
  5fc6925..61faf41, 61faf41..5813bde) + fix 0c06c57.

## Result

PASS — after one traced cosmetic fix.

## Deviations

- Azure/GCS scanners verified against mocked SDKs only — no cloud
  credentials in this environment; field mappings pinned to the API
  reference via RESEARCH.md. First real-account run should sanity-check
  tier strings.
- rc-propagation bug in post-scan outputs was found and fixed during #27
  (not a plan task); covered by the fs no-pricing test.
