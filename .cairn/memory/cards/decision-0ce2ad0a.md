---
type: decision
provenanceFiles: [tagmanager/app/queries.py, tagmanager/scanner.py]
provenanceCommits: [4b51cef, ceb58e7]
created: 2026-07-31
confidence: high
---
Compliance/violations queries are scoped to the LATEST scan run only — earlier runs' rows must not leak into current-compliance answers (ceb58e7, re-confirmed in the final-review fix 4b51cef "violations scoping"). API exposes tag_key and cloud filters on top of that scope. Any new query surface (UI, reports, API endpoints) must inherit the latest-run scoping or it will resurface the stale-rows bug.
