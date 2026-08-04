# Phase 5: dry run diff engine — Research

Source: boto3 1.43.63 official API reference (fetched live). Context7's
boto3 corpus was thin on response shapes; the facts below are from the
boto3 docs pages.

## Live-config GET APIs (read-only)

- **Lifecycle**: `s3.get_bucket_lifecycle_configuration(Bucket=...)`.
  Response `{"Rules": [...], "TransitionDefaultMinimumObjectSize": ...}`
  plus `ResponseMetadata`. Use THIS, not the deprecated
  `get_bucket_lifecycle` (singular `Transition`, rule-level `Prefix`, no
  `Filter` block).
  - **No config** → `ClientError` code `NoSuchLifecycleConfiguration`
    (HTTP 404) → treat as empty `{"Rules": []}`.
- **Intelligent-Tiering**: `s3.list_bucket_intelligent_tiering_configurations(
  Bucket=..., ContinuationToken=...)`. Response
  `{"IsTruncated": bool, "NextContinuationToken": str,
  "IntelligentTieringConfigurationList": [{Id, Filter, Status, Tierings}]}`.
  Manual pagination (no registered paginator); loop on `IsTruncated`.
  - **No configs** → empty list, NOT an error.
  - Prefer `list_...` (one call, full bodies) over N× `get_...by Id`.

## Read-only + IAM

All three are HTTP GET subresource reads — no side effects. Minimum IAM:
`s3:GetLifecycleConfiguration`, `s3:GetIntelligentTieringConfiguration`.

**403 vs 404** (read `e.response["Error"]["Code"]`):
- `AccessDenied` (403) → "unknown — no permission to read config".
- `NoSuchLifecycleConfiguration` (404) → "no live config" (diff vs empty).
- IT: empty list = no config (nothing to catch on the list path).
- Gotcha: a wrong `ExpectedBucketOwner` returns 403 — don't set it.

## Diff normalization (so semantically-equal rules don't read "changed")

1. Strip `ResponseMetadata` AND top-level
   `TransitionDefaultMinimumObjectSize` from the live response.
2. Canonicalize the prefix: AWS may echo a bare-prefix rule as rule-level
   `Prefix` (no `Filter`), or collapse a single-condition `And` to
   `Filter.Prefix`. Our generated side uses `Filter.And.Prefix`. Extract
   the effective prefix from whichever of `rule["Prefix"]`,
   `rule["Filter"]["Prefix"]`, `rule["Filter"]["And"]["Prefix"]` exists.
3. Map absent `Filter` / `{}` / `Prefix: ""` all to canonical `""`.
4. Sort `Transitions` by `(Days, StorageClass)` and `Tierings` by
   `(Days, AccessTier)` before comparing — AWS does not guarantee order.
5. Compare only the subset of keys our generator emits (ID/Status/prefix/
   Transitions/Expiration for lifecycle; Id/Status/prefix/Tierings for
   tiering). Live rules may carry `NoncurrentVersion*`,
   `AbortIncompleteMultipartUpload`, `Expiration.Date` — restrict the
   comparison, don't let extras read as "changed".
6. Guard the `Date`-vs-`Days` axis: a live rule expressed with `Date` has
   no `Days` — surface as a genuine difference, never a crash.

## Freshness

Neither GET returns a `LastModified`/`ETag`/version token — there is NO
server-side config-age signal. A freshness/drift check must be
CONTENT-BASED: the diff itself IS the freshness signal (clean diff = live
already matches what we'd generate; non-empty diff = drift).

## Unconfirmed (flagged)

- Exact error code for `get_bucket_intelligent_tiering_configuration`
  with a nonexistent `Id` — non-issue since we use `list_...`.
- No dedicated paginator for the IT list — manual token loop confirmed.
