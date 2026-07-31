---
type: constraint
provenanceFiles: [tagmanager/scheduler.py, tagmanager/serve.py]
provenanceCommits: [4b51cef, a1ee608]
created: 2026-07-31
confidence: high
---
The scheduler is in-process (runs inside serve, a1ee608) with an overlap guard so a slow scan never double-runs; a deadlock in it was found and fixed at final review (4b51cef). When touching scheduler.py or serve.py, mind lock acquisition order and never hold the overlap-guard lock across a scan await — that was the deadlock shape.
