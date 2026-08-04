---
issues: [37]
---
# Phase 2: cloudtrail read tracking — Plan

Goal: CloudTrail data-event logs become a second last-READ source feeding
the same enrichment index as S3 access logs — so read-hot data stays out
of the stale slice even where access logs aren't configured.

Research done (RESEARCH.md): exact CloudTrail S3 data-event field paths
confirmed against live AWS docs; the design mirrors access_log.py.

## Tasks

### Issue #37 — CloudTrail data-event ingestion

1. `tagmanager/storage/cloudtrail_log.py` — `parse_record(rec) ->
   (bucket, key, aware datetime) or None` (eventSource == s3, eventName
   in {GetObject, SelectObjectContent}, bucket/key from
   requestParameters with the AWS::S3::Object ARN fallback, eventTime
   parsed ISO-8601 UTC) + `load_cloudtrail_index(paths) -> (index,
   used)` opening each file gzip-first then plain-JSON, folding
   `{"Records": [...]}` into `(bucket, key) -> newest-read`. Pure, unit
   tested against the RESEARCH example record incl. the ARN-fallback and
   the exclude cases (HeadObject, GetObjectTagging, non-s3, malformed).
2. Merge both sources into one report: `AccessIndexReport` gains
   `sources: list`; `build_access_report(access_log_paths=(),
   cloudtrail_paths=())` loads each present source, merges newest-wins
   into one index, and records the contributing source labels. Existing
   single-arg callers keep working (access_log_paths positional/kw).
   `ScanOptions.cloudtrail_log_paths` added; `_walk` builds the report
   from both path sets. Tests: merge picks the newest read across
   sources; sources list reflects what was loaded.
3. CLI `--cloudtrail-logs GLOB` (scan mode): globs files, feeds
   cloudtrail_paths, prints the readiness line naming the source(s) and
   the cost/off-by-default caveat; the access-aware summary label names
   the sources. `--access-logs` and `--cloudtrail-logs` combine.
   Tests: cloudtrail-only scan flips a stale-by-mtime object fresh;
   access-logs + cloudtrail combined; empty-glob exits 4 like
   --access-logs.

## Notes

- One issue, three tasks — a parser, a merge, and CLI wiring. No schema
  change; enrichment rides the existing last_accessed / access_aware
  path (phase 4 of v4). The web target form is untouched — scan-time
  CLI/service only, matching --access-logs.
- Semantics stay honest: lower-bound reads, best-effort delivery, and
  the data-events-cost-money caveat surfaced in help + output.
