# AWS-TagCheck — Roadmap

| Phase | Name | Status | Requirements |
|-------|------|--------|--------------|
| 1 | Foundation & guards | verified | REQ-01, REQ-02, REQ-03, REQ-04 |
| 2 | EC2 compliance scan | verified | REQ-05 |
| 3 | HTML report, polish & quality | verified | REQ-06, REQ-07, REQ-08 |

## Phase notes

### Phase 1 — Foundation & guards
Python 3 layout, dependency update (boto3), credential check, account guard.
Walking skeleton that can authenticate and refuse unsafe runs before any scan.

### Phase 2 — EC2 compliance scan
Enumerate regions/instances, compare Environment/Product tags to
`canonical.json`, collect noncompliance data (no report polish yet).

### Phase 3 — HTML report, polish & quality
Generate HTML report, hide empty regions, clean copy, tests + lint green end-to-end.

## Out of scope (later milestones)

- Multi-resource types (RDS, S3, ELB, …) / config-driven resource matrix
- Notifications (email/Slack/SNS)
- Replacing Jenkins/Apache publish path (remains external)
