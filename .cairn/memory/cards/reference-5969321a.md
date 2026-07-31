---
type: reference
provenanceFiles: [tagmanager/providers/aws_provider.py, tagmanager/providers/azure_provider.py, tagmanager/providers/gcp_provider.py]
provenanceCommits: [ac72ff8, 681b8e2, e1df9d1]
created: 2026-07-31
confidence: high
---
Platform-core layout (merged PR #16): tagmanager/{providers,scanner,serve,scheduler,app,models,rules,config}. Provider layer is read-only by design — AWS via boto3 with assume-role coverage (ac72ff8), Azure via Resource Graph (681b8e2), GCP via Cloud Asset Inventory (e1df9d1) — all implementing one provider interface consumed by scanner.py. Milestone-4 storage scanners should follow the same interface-first pattern.
