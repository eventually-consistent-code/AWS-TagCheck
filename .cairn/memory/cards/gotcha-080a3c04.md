---
type: gotcha
provenanceFiles: [.cairn/plans/milestones/v4/02-cost-analysis-engine/PLAN.md, .cairn/plans/milestones/v4/05-structure-recommendations-and-reporting/PLAN.md]
provenanceCommits: [e099064, e099064]
created: 2026-07-31
confidence: high
---
The deep-mode plan-checker pass blocked real spec bugs BEFORE code existed, twice: phase 2's draft priced tiered Standard storage per rollup cell (restarting the 50 TB ladder per cell — every number would have been wrong); phase 5's draft promised an artifacts index with no data source anywhere and an owner dimension the S3 provider never fetched (FetchOwner missing — silently empty on the flagship backend). Both would have shipped as plausible-looking hollow features. Rule: phases with money math or cross-module plumbing get a deep plan (--deep) so the checker reads the draft against the actual codebase.
