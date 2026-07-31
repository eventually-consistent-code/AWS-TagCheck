---
milestone: 5
---
# TagManager — Roadmap

Milestone 5 — deeper signals. Sharpen what the optimizer knows before it
ever acts: data-type awareness, CloudTrail read tracking, request-rate
signals, evidence-labeled recommendations — and the apply ladder's first
rung, a zero-write dry-run diff engine. Destructive-surface posture:
dry-run-first ladder; nothing writes to cloud state this milestone.

| Phase | Name | Status | Requirements |
|-------|------|--------|--------------|
| 1 | Data type signals | planned | REQ-01, REQ-02 |
| 2 | CloudTrail read tracking | planned | REQ-03 |
| 3 | Request rate awareness | planned | REQ-04 |
| 4 | Signal-driven recommendations | planned | REQ-05 |
| 5 | Dry-run diff engine | planned | REQ-06 |

## Phase notes

### Phase 1 — Data type signals
Extension-derived coarse type dimension in rollups (opt-in, like owner);
type-aware structure recommendations — closes v4's declared REQ-11 gap.

### Phase 2 — CloudTrail read tracking
CloudTrail data-event logs as a second access-index source feeding the
same per-key last-read enrichment; source labeled, cost warning stated.

### Phase 3 — Request rate awareness
Per-prefix read/write rate estimates from access-log/CloudTrail op counts,
persisted with the run; unlocks the perf fan-out advice v4 excluded.

### Phase 4 — Signal-driven recommendations
Recommendations consume the new signals: telemetry-verified zone splits,
churn/expiry-in-place advice, per-rec confidence labels naming evidence.

### Phase 5 — Dry-run diff engine
Apply-ladder rung one, zero writes: diff live bucket lifecycle/tiering
config against generated artifacts, rule-by-rule "what would change" +
manifest freshness checks. Guarded applies remain a later milestone.

## Out of scope (later milestones)

- Actual apply mode (writes to cloud state) — ladder rungs two and three
- S3 Inventory-report ingestion for billion-object buckets; more pricing
  regions; scheduler-driven storage scans
- Multi-resource tag matrix (RDS, ELB, …), notifications (email/Slack/SNS)
- Replacing Jenkins/Apache publish path (remains external)

## Archived — v1

Modernized AWS-TagCheck: Python 3 + boto3 foundation with credential/account guards, multi-region EC2 Environment/Product scan vs canonical.json, stdlib HTML report with empty-region polish, and pytest + lint green. — see milestones/v1/

## Archived — v3

Milestone 3: HTML compliance report shipped end-to-end — multi-region EC2 Environment/Product scan vs canonical.json, HTML report with empty-region polish, S3 report/gold upload, platform-core package (providers/scanner/serve/scheduler) merged, 82 tests + pylint 10.00 green. — see milestones/v3/

## Archived — v4

Storage lifecycle optimizer shipped: multi-backend age scans (S3/Azure/GCS/filesystem) with access-aware aging, honest cost analysis and per-option savings projections, validated ready-to-apply artifacts (lifecycle configs, tiering configs, delete/batch-copy/move manifests), structure recommendations with two-pass move plans, and one-page HTML + web UI reporting. 186 tests, three adversarial verification rounds. — see milestones/v4/
