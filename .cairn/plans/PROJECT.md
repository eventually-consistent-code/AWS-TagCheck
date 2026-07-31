# TagManager

## Vision

TagManager grew from an EC2 tag compliance checker into a multi-cloud data
platform (see milestones/v1, v3). Milestone 4 — **storage lifecycle
optimizer** — turns it toward static/unstructured data in mass storage:
identify data that is old (against user-defined age thresholds), establish
when it was last touched/opened/edited, price what keeping it costs, and
present concrete management options — full deletion, age-out rules,
intelligent tiering, archive/mass-move plans — plus recommendations for more
logical storage structures based on data type, who interacts with it, and how
often it's accessed.

Posture: **analyze + generate**. The tool produces reviewable artifacts
(delete manifests, lifecycle policy JSON, tiering configs, reorg proposals);
a human applies them. Apply mode is a later milestone.

Targets: S3 first as the walking skeleton, then Azure Blob, GCS, and
SMB/local filesystem behind one scanner interface.

Collaboration: **vibe** (cairn drives; human steers).

## Requirements (milestone 4)

- REQ-01: Backend-agnostic inventory model + scanner interface (path, size, class/tier, last-modified, owner, backend)
- REQ-02: S3 inventory scanner with user-configurable age thresholds; end-to-end scan → age bands → summary
- REQ-03: Pricing maps per backend/class; stale-data monthly cost report by bucket/prefix and age band
- REQ-04: Savings projections per option (delete / age-out / tiering / archive) incl. transition/retrieval caveats
- REQ-05: Deletion candidate manifests — generated, human-applied, never auto-deleted
- REQ-06: Age-out rule generator → S3 lifecycle policy JSON from user thresholds
- REQ-07: Intelligent-Tiering configs + archive/batch move plans (Glacier tiers, S3 Batch Operations)
- REQ-08: Azure Blob + GCS scanners behind the inventory interface, with tier pricing
- REQ-09: SMB/local filesystem scanner (atime/mtime age, directory rollups, owners)
- REQ-10: Access enrichment — last-READ signals (S3 access logs / Storage Class Analysis / FS atime) so read-hot data isn't flagged stale
- REQ-11: Structure recommendation engine — reorg proposals by data type, principal, access frequency, with move manifests
- REQ-12: Report integration — HTML/CSV sections for age, cost, per-option savings, artifacts index, structure recommendations

## Project files

- canonical.json — authoritative Environment/Product lists (repo root)
- index.html — generated report (output)
- .cairn/ — project plans, roadmap, and continuity artifacts

## Notes

- Exit codes: 0=OK, 1=violations, 2=credential failure, 3=account mismatch, 4=config error
- Tag checks remain case-sensitive to match existing canonical lists
- Prior-milestone requirement history lives in milestones/v1/ and milestones/v3/
