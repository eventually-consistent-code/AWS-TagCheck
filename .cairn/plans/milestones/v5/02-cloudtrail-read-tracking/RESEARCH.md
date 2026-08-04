# Phase 2: CloudTrail read tracking — Research

Researched: 2026-07-31 (live AWS docs — CloudTrail record reference,
S3 data-event docs, log-file format).

## CloudTrail S3 data-event shape (confirmed field paths)

- **File**: one gzipped JSON object per file, top-level `{"Records":
  [...]}`. Load via `gzip.open → json.load → obj["Records"]`. Delivered
  under `AWSLogs/<acct>/CloudTrail/<region>/YYYY/MM/DD/*.json.gz`.
- **Per event** (S3 GetObject): `eventSource` = `"s3.amazonaws.com"`,
  `eventName` = `"GetObject"`, `eventCategory` = `"Data"`, `eventTime`
  ISO-8601 UTC (`"2026-07-30T14:22:09Z"`), `requestParameters.bucketName`
  + `requestParameters.key`, `readOnly` true, and `resources[]` carrying
  an `AWS::S3::Object` entry with `ARN: arn:aws:s3:::<bucket>/<key>`.
- **Bucket/key source**: `requestParameters.bucketName`/`key` is primary
  (flat, cheap). Fallback when requestParameters is truncated (dropped
  above 100 KB): parse the `AWS::S3::Object` ARN —
  `arn.split(":::",1)[1].split("/",1)` → `[bucket, key]`.
- **Trust `eventTime`, NOT the log-file path date** — a file delivered
  at T can hold records written earlier.

## Which events are content READS

- INCLUDE: `GetObject`, `SelectObjectContent` — actual object-body reads.
  These match the existing access-log parser's `REST.GET.OBJECT` (body
  reads only).
- EXCLUDE: `HeadObject` (metadata only — the access-log parser already
  excludes REST.HEAD.OBJECT, so match it), and all `GetObjectTagging` /
  `GetObjectAcl` / `GetObjectAttributes` etc. (metadata/ACL reads, all
  `readOnly:true` — so `readOnly` alone is NOT a sufficient filter; the
  eventName allowlist is required).

## Cost / enablement caveat (must surface)

Object-level data events are **OFF by default** and **bill per event**
(AWS: "By default, trails and event data stores do not log data events.
Additional charges apply for data events."). A parser must not assume
they exist; the tool documents that enabling them costs money and that
absent logs simply mean no enrichment.

## Design fit

- Mirrors the existing `access_log.py` / `build_access_report` /
  `AccessIndexReport` path exactly: a new `cloudtrail_log.py` with
  `parse_record` + `load_cloudtrail_index`, feeding the SAME
  `(bucket, key) -> newest-read` index.
- Both sources MERGE into one index — newest read wins across sources;
  the lower-bound / best-effort semantics are identical.
- Source labeling (issue #37): the report tracks which sources
  contributed so output can say "access-aware — S3 access logs +
  CloudTrail".
- Scope: CLI/service scan-time path (like `--access-logs`), not a web
  target option this phase.

## Sources
- record contents: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html
- S3 data events: https://docs.aws.amazon.com/AmazonS3/latest/userguide/cloudtrail-logging-s3-info.html
- data-event cost/enablement: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html
- log-file format: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-examples.html
