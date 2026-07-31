---
milestone: 5
---
# TagManager — Roadmap

Milestone 5 — web application + deeper signals. Rescoped 2026-07-31: the
whole optimizer becomes a containerized web application (CLI preserved as
a first-class equal), THEN the signal work sharpens what it knows.
**Execution order: phases 6 → 7 → 8 first, then 1 → 5** (numbers are
identity, not order — decimal-insert rules forbid renumbering).
Destructive-surface posture unchanged: nothing writes to cloud state.

| Phase | Name | Status | Requirements |
|-------|------|--------|--------------|
| 6 | Storage service layer | planned | REQ-07, REQ-08 |
| 7 | Storage web app | planned | REQ-09, REQ-10, REQ-12 |
| 8 | Container packaging | planned | REQ-11 |
| 1 | Data type signals | planned | REQ-01, REQ-02 |
| 2 | CloudTrail read tracking | planned | REQ-03 |
| 3 | Request rate awareness | planned | REQ-04 |
| 4 | Signal-driven recommendations | planned | REQ-05 |
| 5 | Dry-run diff engine | planned | REQ-06 |

## Phase notes

### Phase 6 — Storage service layer
Extract scan/analyze/emit flows into argparse-free services; CLI becomes a
thin shell over them (existing CLI test suite stays green unchanged — the
parity contract). StorageTarget config rows + background scan jobs inside
serve, scheduler-pattern overlap guard.

### Phase 7 — Storage web app
Write-side UI: configure targets, trigger scans, watch job progress;
interactive cost/savings/recommendations pages; artifact generation +
zip download from the browser. OIDC-gated; age-basis labels and estimate
disclaimers on every page. Plus the TagManager rebrand (REQ-12): the
AWS- prefix drops from every user surface — the product is multi-cloud;
GitHub repo already renamed (2026-07-31), aws-tag-manager entry point
kept as a compatibility alias.

### Phase 8 — Container packaging
`docker compose up` = the full web app: artifact volume, credential env
passthrough, healthcheck. CLI ships in the image and on bare installs;
parity documented in README/runbook.

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
