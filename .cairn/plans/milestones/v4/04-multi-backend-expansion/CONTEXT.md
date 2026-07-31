# Phase 4: multi-backend expansion — Context

## Locked decisions

- **Azure/GCS SDKs are optional dependencies** — lazy imports inside the
  providers, clear error naming the missing package. Base install stays
  boto3-only; `requirements.txt` gains commented optional lines.
- **`last_accessed` is a new optional StorageObject field.** Azure fills
  it from `last_accessed_on` (requires account-level tracking; ~daily
  resolution), FS from atime, S3 via access-log enrichment, GCS never
  (the platform exposes nothing). Effective age = newest of
  (last_modified, last_accessed).
- **Age basis is always labeled.** Every summary, report, and artifact
  says whether ages are last-modified-only or access-aware; access-aware
  ages are lower bounds (log delivery is best-effort, hours of lag).
- **Storage Class Analysis is OUT of the enrichment plan** — its export
  is aggregate-only (confirmed), no per-object rows. Issue #28 carries
  the dated reconciliation note. S3 enrichment = server access logs
  (`REST.GET.OBJECT`), parsed into a key→last-read index at scan time.
- **Pricing snapshots for azure/gcs** join the existing schema
  (provider/region/classes/min durations/retrieval). GCS monthly rates
  are derived from Google's hourly numbers (flagged in the snapshot);
  Azure's Cold rate is soft-confirmed — both carry `as_of_date` and
  re-verify at refresh time. **fs has no pricing** — cost report on an
  fs run explains that instead of pricing at zero.
- **Backend selection via `--backend s3|azure|gcs|fs`** on the CLI; scan
  args stay uniform (`--bucket` doubles as container/bucket/root-path).
  Azure needs `--account-url`; fs needs no cloud flags.
- Tier/class names map into the shared enum space verbatim per platform
  (HOT/COOL/COLD/ARCHIVE for Azure; STANDARD/NEARLINE/COLDLINE/ARCHIVE
  for GCS) — no cross-cloud renaming; pricing snapshots key on each
  platform's own names.
