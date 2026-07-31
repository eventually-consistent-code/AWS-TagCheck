# Phase 4: multi-backend expansion — Research

Researched: 2026-07-31 (live SDK API references + pricing pages).

## Azure Blob (`azure-storage-blob`)

- `ContainerClient.list_blobs()` streams with automatic pagination
  (ItemPaged lazily follows continuation tokens); `results_per_page`
  sizes pages.
- `BlobProperties`: `name`, `size` (bytes), `last_modified`,
  `blob_tier` (Hot/Cool/Cold/Archive), `last_accessed_on` — the last
  field ONLY populated when last-access-time tracking is enabled on the
  account, and updates at ~daily resolution (first read per 24h window).
- Auth: `BlobServiceClient(account_url, credential=DefaultAzureCredential())`,
  `https://<account>.blob.core.windows.net`.

## GCS (`google-cloud-storage`)

- `Client.list_blobs(bucket, prefix=..., page_size=...)` — automatic
  pagination via the iterator.
- `Blob`: `name`, `size`, `updated`, `storage_class`
  (STANDARD/NEARLINE/COLDLINE/ARCHIVE).
- **No per-object last-access time exists** — confirmed against the API
  resource; Autoclass tracks access internally but exposes nothing.

## Pricing (list, US primary regions)

- Azure Blob East US LRS $/GB-mo: Hot 0.018 (50/500 TB breaks), Cool
  0.01, Cold 0.0045 (SOFT — corroborated by two 2026 secondary sources,
  Microsoft's page is JS-rendered; re-verify at refresh time), Archive
  0.00099. Minimum retention: Cool 30d / Cold 90d / Archive 180d,
  prorated early-deletion charges.
- GCS us-central1 $/GiB-mo (DERIVED — Google publishes hourly rates,
  ×730): Standard ≈0.022, Nearline ≈0.011, Coldline ≈0.0044, Archive
  ≈0.0014. Minimums: Nearline 30d / Coldline 90d / Archive 365d.
  Retrieval $/GiB: 0.01 / 0.02 / 0.05.

## S3 last-READ enrichment

- Server access logs: space-delimited; parse `Operation`
  (`REST.GET.OBJECT`), `Key` (URL-encoded, `-` when not object-scoped),
  `Time` (`[%d/%b/%Y:%H:%M:%S %z]`). max(Time) per key = last read.
  Delivery is BEST-EFFORT with hours-scale lag and possible gaps —
  derived last-read is a lower bound, never ground truth.
- **Storage Class Analysis: aggregate-only, confirmed** — daily CSV has
  age-bucket metrics, zero per-object rows, and only recommends
  STANDARD→STANDARD_IA. Dropped from the enrichment plan; issue #28
  updated with a dated reconciliation note.

## Design consequences

- New optional `last_accessed` on StorageObject: Azure and FS populate
  natively (FS atime); S3 enriches from parsed access logs; GCS never.
- Effective age = newest of (last_modified, last_accessed); every
  summary/report label must say which basis was used.
- Azure/GCS SDKs become OPTIONAL dependencies (lazy imports) — the base
  install stays boto3-only.
- Pricing snapshots for azure/gcs enter the existing schema; fs has no
  pricing (cost report must say so, not zero it).
