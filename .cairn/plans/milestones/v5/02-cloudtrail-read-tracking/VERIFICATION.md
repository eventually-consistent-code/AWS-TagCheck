# Phase 2: cloudtrail read tracking — Verification

Verified: 2026-07-31

## Goal-backward check

Phase promise: CloudTrail data-event logs become a second last-READ
source feeding the same enrichment index as S3 access logs, so read-hot
data stays out of the stale slice even where access logs aren't
configured.

Live end-to-end drive (real CLI, real gzipped CloudTrail file with the
AWS delivery filename `123_CloudTrail_us-east-1_..._abc.json.gz`):

- **Gzip parse + counting**: "cloudtrail index: 2 read events over 2
  keys" — both the `requestParameters` GetObject AND the truncated
  record resolved via the `AWS::S3::Object` ARN fallback counted; the
  `GetObjectTagging` noise correctly excluded (would be 3 if the
  eventName allowlist leaked).
- **Cost caveat printed**: "CloudTrail S3 data events are off by default
  and bill per event — parsing only what you exported, enabling
  nothing."
- **Source labeled**: "access index ready: ... from CloudTrail".
- **Enrichment effect proven**: `archive/hot-read.dat` — 700 days old by
  mtime but read 3 days ago per CloudTrail — landed in the `<90d` fresh
  band; `archive/cold.dat` (never read) stayed `>365d`. The
  read-hot-never-edited object is kept out of the stale slice by
  CloudTrail alone. Summary labeled "age = access-aware".

Locked decisions honored: same index as access logs (merge tested in
`test_build_access_report_merges_sources` — newest wins, sources
recorded); content-read allowlist {GetObject, SelectObjectContent} with
readOnly NOT the filter (exclude cases unit-tested); requestParameters
primary + ARN fallback; gzip-or-plain files; eventTime not path date;
cost caveat surfaced; CLI/service scan-time scope, no schema change.

## Gates

- Tests: 230 passed, 0 failed (8 new this phase).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flag on 37 normalizes with
  this file. Open issues in phase: none. TDD frontmatter: none.
- Ledger: issue 37 with commit range (8549ead..8b0ca83).

## Result

PASS.

## Deviations

- The live drive exercised the CloudTrail-only path (the new code); the
  access-log + CloudTrail two-source merge is covered by unit test, not
  a second live drive — same `build_access_report` merge either way.
- "S3 export" ingestion (issue text) is served by the local-file glob:
  users sync the CloudTrail S3 prefix down and point `--cloudtrail-logs`
  at it. Direct S3-read of the trail bucket was not in scope this phase.
