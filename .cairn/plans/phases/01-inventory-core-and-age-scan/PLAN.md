---
issues: [19, 20]
---
# Phase 1: inventory core and age scan — Plan

Goal: thin vertical slice — scan an S3 bucket, band objects by age against
user thresholds, emit console + CSV summary — on a backend-agnostic
interface phase 4 can implement for Azure/GCS/SMB.

## Tasks

### Issue #19 — inventory model + scanner interface

1. `tagmanager/storage/base.py` — `StorageObject` dataclass (backend,
   container, key, size_bytes, storage_class, last_modified, owner|None,
   region|None); abstract `StorageProvider` with
   `list_objects(container, prefix) -> Iterator[StorageObject]` and
   `capabilities()`; mirror `providers/base.py` shape.
2. `tagmanager/storage/rollup.py` — age-band classifier (thresholds in
   days → band label) + streaming aggregator: consumes StorageObject
   iterator, produces rollups keyed (container, prefix@depth,
   storage_class, age_band) → count/bytes/oldest, plus bounded top-N
   largest + oldest samples. Pure logic, no cloud calls, unit-tested first.
3. `tagmanager/models/tables.py` — `StorageScanRun` + `StoragePrefixStat`
   tables following the ScanRun pattern (status, skips JSON; latest-run
   scoping per card decision-0ce2ad0a); persistence helper writes rollups.

### Issue #20 — S3 scanner + thresholds + summary

4. `tagmanager/storage/s3_provider.py` — `S3StorageProvider` over
   ListObjectsV2 paginator (Key/Size/StorageClass/LastModified per page),
   bucket + optional prefix scope, per-bucket failure isolation into run
   skips; mock-paginator tests per `test_aws_provider.py` pattern.
5. `tagmanager/config.py` — `age_band_days` setting (default `[90, 365]`,
   env `TAGMANAGER_AGE_BAND_DAYS`), prefix rollup depth (default 2).
6. `tagmanager/storage/cli.py` — entrypoint: `--bucket` (repeatable),
   `--prefix`, `--age-bands`, `--csv-out`; runs scan → rollup → persists →
   prints console table (bytes/count per band, oldest object) and writes
   CSV. End-to-end test with mocked provider.

## Notes

- Task order is the dependency order; 1–2 are pure-Python and land first.
- Report labels say "last modified" not "last accessed" until phase-4
  enrichment (REQ-10).
