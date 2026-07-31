---
issues: [35, 36]
---
# Phase 1: data type signals — Plan

Goal: the optimizer knows WHAT the data is, not just how old — closing
v4's declared REQ-11 gap with an extension-derived type dimension and
type-aware recommendations.

No research fan-out: the dimension is the owner-dimension pattern from
v4 applied verbatim, and the taxonomy is a design constant (standard
depth, no material unknowns).

## Tasks

### Issue #35 — data-type dimension in rollups

1. `tagmanager/storage/datatypes.py` — `EXTENSION_MAP` constant +
   `classify_key(key) -> str` (logs/media/archives/data/docs/other;
   compound extensions outermost-meaningful, case-insensitive, no
   extension → other). Pure function, exhaustive unit tests including
   `.tar.gz`, `.CSV`, `README`, dotfiles.
2. Dimension plumbing, one commit, every unpacker (constraint card
   constraint-d876930a): cell key → always-6-tuple with `data_type` ""
   when off; `RollupBuilder(rollup_types=)`; `--rollup-types` flag with
   cardinality note; `StoragePrefixStat.data_type` column + schema
   guard + persist + rollup CSV column; cost-report merge keeps its
   location-level key (type slices merge like owner slices). Tests:
   6-tuple lookups updated, roundtrip with types on/off, combined
   owners×types scan, cost-report single-row merge.

### Issue #36 — type-aware structure recommendations

3. Signals + attribution: `_PrefixSignals.type_bytes`; recs gain
   `top_types` (mirroring `top_owners`) persisted in `structure_recs`
   JSON; surfaced in console output, PROPOSAL.md, HTML report
   recommendations table, and /storage template. Compact-first and
   zone-split rationales name the dominant cold type when recorded.
4. `type-split` rec kind: fires only when the run recorded types, ≥2
   types each hold ≥ MIXED_BAND_MIN_SHARE of prefix bytes, and no
   stronger rec applies (precedence per CONTEXT). Suggested layout
   `prefix/<type>/...` in PROPOSAL.md guidance. OUT_OF_SCOPE_NOTES
   updated: data-type note becomes conditional ("recorded only when
   --rollup-types"). Tests: fires on mixed types, loses to every
   stronger kind, absent when types weren't recorded.

## Notes

- Task order 1 → 4; 2 is the risky one (key-shape change) — its tests
  update the v4 5-tuple assertions in the same commit.
- Move-plan emitter is untouched: type-split produces PROPOSAL guidance
  only this phase; key-level type-move manifests would need a rec-kind
  entry in MOVABLE_KINDS and are deferred until someone asks.
