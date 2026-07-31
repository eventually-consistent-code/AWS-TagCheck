---
milestone: 5
---
# TagManager — Roadmap

Milestone 4 — storage lifecycle optimizer. Static/unstructured data in mass
storage: find old data by user-defined age, price what it costs to keep,
generate management options (delete / age-out / tiering / archive), and
recommend saner storage structures. Posture: analyze + generate artifacts;
a human applies them. Targets: S3 first (walking skeleton), then Azure Blob,
GCS, SMB/local filesystem.

| Phase | Name | Status | Requirements |
|-------|------|--------|--------------|
| 1 | Inventory core & age scan | planned | REQ-01, REQ-02 |
| 2 | Cost analysis engine | planned | REQ-03, REQ-04 |
| 3 | Lifecycle recommendations | planned | REQ-05, REQ-06, REQ-07 |
| 4 | Multi-backend expansion | planned | REQ-08, REQ-09, REQ-10 |
| 5 | Structure recommendations & reporting | planned | REQ-11, REQ-12 |

## Phase notes

### Phase 1 — Inventory core & age scan
Backend-agnostic inventory model + scanner interface; S3 scanner collecting
size/storage-class/LastModified; user-configurable age thresholds. Thin
vertical slice: scan → age bands → summary output end-to-end.

### Phase 2 — Cost analysis engine
Per-backend/per-class pricing maps, stale-data monthly cost report by
bucket/prefix and age band, savings projections per management option
(including transition/retrieval caveats).

### Phase 3 — Lifecycle recommendations
Generated, human-applied artifacts: delete manifests, S3 lifecycle policy
JSON from age thresholds, Intelligent-Tiering configs, archive/batch move
plans (Glacier tiers, S3 Batch Operations manifests).

### Phase 4 — Multi-backend expansion
Azure Blob + GCS scanners behind the phase-1 interface; SMB/local filesystem
scanner (atime/mtime); access enrichment — last-READ signals from S3 access
logs / Storage Class Analysis / FS atime, so read-hot-never-edited data isn't
flagged stale.

### Phase 5 — Structure recommendations & reporting
Reorg proposals from observed inventory (group by data type, owner/principal,
access frequency) with move manifests; HTML/CSV report sections for age, cost,
options, and structure.

## Out of scope (later milestones)

- Apply mode (tool executing deletes/tiering itself behind --apply)
- CloudTrail data-event ingestion for per-object read tracking
- Multi-resource tag matrix (RDS, ELB, …), notifications (email/Slack/SNS)
- Replacing Jenkins/Apache publish path (remains external)

## Archived — v1

Modernized AWS-TagCheck: Python 3 + boto3 foundation with credential/account guards, multi-region EC2 Environment/Product scan vs canonical.json, stdlib HTML report with empty-region polish, and pytest + lint green. — see milestones/v1/

## Archived — v3

Milestone 3: HTML compliance report shipped end-to-end — multi-region EC2 Environment/Product scan vs canonical.json, HTML report with empty-region polish, S3 report/gold upload, platform-core package (providers/scanner/serve/scheduler) merged, 82 tests + pylint 10.00 green. — see milestones/v3/

## Archived — v4

Storage lifecycle optimizer shipped: multi-backend age scans (S3/Azure/GCS/filesystem) with access-aware aging, honest cost analysis and per-option savings projections, validated ready-to-apply artifacts (lifecycle configs, tiering configs, delete/batch-copy/move manifests), structure recommendations with two-pass move plans, and one-page HTML + web UI reporting. 186 tests, three adversarial verification rounds. — see milestones/v4/
