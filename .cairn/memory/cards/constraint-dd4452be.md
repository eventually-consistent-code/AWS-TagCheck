---
type: constraint
provenanceFiles: [tagmanager/storage/projections.py, tagmanager/storage/lifecycle_gen.py]
provenanceCommits: [eb53d3d, 368bacd]
created: 2026-07-31
confidence: high
---
Storage savings math is never a $/GB rate delta. The engine must model: marginal rates across tier ladders (removing bytes comes off the top — blended effective rates overstate savings ~4-10% at scale; account-aggregate ladders, never per-cell), 128 KiB billable floors (IA classes + Glacier IR) computed from real small-object bytes, split Glacier metadata overhead (8 KiB at Standard rate + 32 KiB at archive rate per object — applies to EVERY Glacier-bound transition regardless of which option proposed it), the INT transition matrix (INT sources never → Standard-IA), transition fees with break-even months, and explicit ObjectSizeGreaterThan in generated rules (AWS's post-Sept-2024 default excludes <128 KiB from all transitions). Options that lose money say NOT RECOMMENDED. All encoded in pricing.py/projections.py/lifecycle_gen.py; new management options must model the same mechanics.
