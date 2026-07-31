# Phase 1: inventory core and age scan — Research

Researched: 2026-07-31 (repo reuse-surface sweep)

## Reuse surfaces

- **Provider pattern to mirror** — `tagmanager/providers/base.py:31-50`:
  abstract `Provider` with `list_resources(scope)` yielding a
  `NormalizedResource` dataclass (base.py:5-8) + `capabilities()`. Storage
  scanners should mirror this shape exactly: dataclass record + iterator +
  capabilities.
- **Models/DB** — `tagmanager/models/base.py:11-28` (DeclarativeBase,
  `get_engine`, `session_factory`); `tables.py` has `Resource`, `ScanRun`
  (status running/complete/partial, skips JSON), `Violation`. Scan-run
  scoping via `last_seen_run_id` / `scan_run_id` FK — milestone-3 card
  decision-0ce2ad0a (latest-run scoping) applies to any storage queries too.
- **Scanner service** — `tagmanager/scanner.py`: `_upsert` keyed on unique
  constraint, `run_scan` isolates per-scope failures into `ScanRun.skips`,
  `reap_stale_runs` at boot. Same failure-isolation shape wanted for bucket
  scans.
- **Config** — `tagmanager/config.py:9-21`: pydantic `Settings`,
  `env_prefix="TAGMANAGER_"`, `get_settings()`. Age thresholds belong here.
- **Existing S3 code** — `aws.py:298-347`: `parse_s3_uri`, `read_s3_text`,
  `upload_file_to_s3`. No bucket enumeration or object listing exists yet —
  scanner is new code.
- **Tests** — `unittest.mock` boto3 stubs (no moto); `test_aws_provider.py`
  shows the paginator-mock pattern to copy.

## Design findings

- **Per-object DB rows don't scale.** Mass-storage buckets run to millions+
  objects; SQLite (default `sqlite:///tagmanager.db`) would drown. Persist
  AGGREGATES: rollups keyed (backend, container, prefix, storage_class,
  age_band) → object_count, total_bytes, oldest_last_modified — plus a
  bounded top-N sample of largest/oldest objects for the report.
- **ListObjectsV2 is sufficient for phase 1.** Each page already carries
  Key, Size, StorageClass, LastModified — no per-object HEAD calls needed.
  Stream pages into rollups; never hold the full listing in memory.
  S3 Inventory-report ingestion (for billion-object buckets) and last-READ
  enrichment are phase-4 scope (REQ-10).
- **Age bands** are pure threshold math on LastModified — unit-testable
  without AWS; thresholds user-configurable via Settings + CLI override.
