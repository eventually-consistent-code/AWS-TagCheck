---
type: gotcha
provenanceFiles: [tagmanager/storage/access_log.py, .cairn/plans/milestones/v4/04-multi-backend-expansion/RESEARCH.md]
provenanceCommits: [5813bde, e099064]
created: 2026-07-31
confidence: medium
---
Per-object last-READ truth varies wildly by platform (milestone 4 research + implementation): S3 has NOTHING native — server access logs give a lower bound (best-effort delivery, hours of lag, REST.GET.OBJECT parsing) and Storage Class Analysis is aggregate-only (no per-object rows — useless for enrichment, easy trap); Azure last_accessed_on works but only with account-level tracking enabled and ~daily resolution (first read per 24h); GCS exposes nothing per-object; filesystems give atime (unless noatime mounts). Consequence baked into the stack: age basis = newest of modified/accessed, and EVERY output surface labels whether ages are last-modified-only or access-aware lower bounds. Read-hot-never-edited data must land in the fresh band, not on a delete manifest.
