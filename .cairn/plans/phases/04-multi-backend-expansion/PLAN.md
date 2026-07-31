---
issues: [26, 27, 28]
---
# Phase 4: multi-backend expansion — Plan

Goal: the same scan → age bands → cost → artifacts pipeline over Azure
Blob, GCS, and SMB/local filesystems, plus true last-READ awareness where
each platform can give it.

## Tasks

### Issue #26 — Azure Blob + GCS scanners + pricing

1. `tagmanager/storage/azure_provider.py` — `AzureBlobStorageProvider`
   (account_url + DefaultAzureCredential, lazy `azure-storage-blob`
   import): `list_blobs()` stream → StorageObject with `blob_tier` as
   storage_class (HOT/COOL/COLD/ARCHIVE) and `last_accessed_on` →
   `last_accessed` when present. Mock-SDK tests incl. the
   missing-package error message.
2. `tagmanager/storage/gcs_provider.py` — `GcsStorageProvider` (lazy
   `google-cloud-storage` import): `list_blobs()` stream → StorageObject
   (`updated` as last_modified, `storage_class` verbatim). Mock tests.
3. Pricing + CLI routing: `data/azure_pricing.json` + `data/gcs_pricing.json`
   in the existing schema (min durations 30/90/180 and 30/90/365,
   retrieval fees; GCS rates flagged derived-from-hourly, Azure Cold
   flagged soft); `--backend s3|azure|gcs|fs` selects provider AND
   pricing snapshot across scan/report/emit paths (`--account-url` for
   Azure). `requirements.txt` optional-deps comment block.

### Issue #27 — SMB/local filesystem scanner

4. `tagmanager/storage/fs_provider.py` — `FilesystemStorageProvider`:
   `os.scandir` recursive walk of a root path (the "container"),
   st_size/st_mtime → StorageObject, st_atime → `last_accessed`, owner
   via `pwd` best-effort, per-subtree error isolation (PermissionError
   → skip record, walk continues). storage_class "FILESYSTEM"; cost
   report on an fs run prints "no pricing for filesystem backends"
   instead of zeros. Tests over a tmp_path tree.

### Issue #28 — access enrichment (last-READ)

5. `last_accessed` through the core: optional StorageObject field;
   `RollupBuilder` age basis = newest of (modified, accessed); builder
   records whether ANY accessed timestamps were seen and
   summary/cost/projection output labels flip between "age = last
   modified" and "age = access-aware (lower bound)". Tests: read-hot
   never-edited object lands in the fresh band.
6. S3 access-log enrichment: parser for server-access-log lines —
   `REST.GET.OBJECT` ops, URL-decoded `Key`, `Time`
   (`[%d/%b/%Y:%H:%M:%S %z]`) — folded into a per-(bucket,key)
   last-read index; `--access-logs GLOB` loads local log files and the
   scan enriches streamed S3 objects from the index. Caveats printed:
   best-effort delivery, hours-scale lag. Tests with real-format sample
   lines incl. `-` keys and non-GET ops.

## Notes

- Task order: 1–3 (#26), 4 (#27), 5–6 (#28) — the field change in 5
  touches every provider, so it lands after all providers exist.
- Providers never write; read-only walk everywhere (matches provider-
  layer card reference-5969321a).
