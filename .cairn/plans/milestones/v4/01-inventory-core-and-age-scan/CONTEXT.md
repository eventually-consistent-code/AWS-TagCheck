# Phase 1: inventory core and age scan — Context

## Locked decisions

- **Aggregate-first persistence.** No per-object rows in the DB. Rollups
  keyed (backend, container, prefix, storage_class, age_band) with
  object_count / total_bytes / oldest_last_modified, plus a bounded top-N
  sample (largest + oldest objects) for reporting. SQLite default must
  survive multi-million-object buckets.
- **Mirror the provider pattern.** New `tagmanager/storage/` package:
  `StorageObject` dataclass + abstract `StorageProvider` (iterator +
  `capabilities()`), shaped like `providers/base.py`. Phase-4 backends
  (Azure/GCS/SMB) implement the same interface — the interface is the
  phase-1 deliverable that phase 4 depends on.
- **Streaming scan.** ListObjectsV2 pages stream directly into rollups;
  the full object listing is never materialized in memory. Metadata-only
  in this phase — no per-object HEAD, no S3 Inventory ingestion (phase 4).
- **Age bands from Settings.** Pydantic `Settings` (env prefix
  `TAGMANAGER_`), default bands 90/365 days (warm < 90d ≤ stale < 365d ≤
  cold), CLI-overridable. Band math on LastModified; last-READ enrichment
  is explicitly phase-4 (REQ-10) — reports must label age as
  "last modified", not "last accessed", until then.
- **Walking skeleton ends at console + CSV.** scan → rollup → summary
  output end-to-end this phase; DB persistence uses the existing
  ScanRun/latest-run scoping pattern (card decision-0ce2ad0a); HTML/report
  integration is phase 5 (REQ-12).
