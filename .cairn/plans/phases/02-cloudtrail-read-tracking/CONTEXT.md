# Phase 2: cloudtrail read tracking — Context

## Locked decisions

- **Second source, one index.** CloudTrail data-event logs feed the SAME
  `(bucket, key) -> newest-read` index the S3 server-access-log parser
  feeds. Both merge; newest read wins across sources. Identical
  lower-bound / best-effort semantics (log delivery lags; absence just
  means no enrichment).
- **Mirror the access-log module.** New `cloudtrail_log.py` with
  `parse_record(rec)` + `load_cloudtrail_index(paths)`, shaped like
  `access_log.py`. Files are gzipped `{"Records": [...]}` — gzip-aware,
  also accept plain `.json`. Parse `eventTime` (ISO-8601 UTC), not the
  path date.
- **Content-read allowlist = {GetObject, SelectObjectContent}** — body
  reads only, matching the access-log parser's REST.GET.OBJECT (which
  already excludes HEAD). `readOnly` alone is NOT a filter (tagging/ACL
  reads are readOnly too); the eventName allowlist is required. Filter
  on `eventSource == s3.amazonaws.com` first.
- **Bucket/key from `requestParameters`, ARN fallback.** Primary:
  `requestParameters.bucketName`/`key`. When requestParameters is
  truncated (>100 KB), fall back to the `AWS::S3::Object` entry's ARN.
- **Source labeling (issue #37).** `AccessIndexReport` grows a `sources`
  list; `build_access_report` merges access-log + cloudtrail paths and
  records which contributed. Output says "access-aware — <sources>";
  the existing single-source note stays correct when only one is used.
- **Cost caveat surfaced.** `--cloudtrail-logs` help text and the scan
  output state that S3 data events are off by default and bill per
  event — the tool never enables anything, just parses what the user
  exported.
- **Scope: CLI/service scan-time path**, like `--access-logs`. Not a web
  target option this phase (web enrichment is a later concern). No new
  DB columns — enrichment rides the existing `last_accessed` /
  `access_aware` machinery.
