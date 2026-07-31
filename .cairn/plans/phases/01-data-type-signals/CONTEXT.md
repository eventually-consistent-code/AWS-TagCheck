# Phase 1: data type signals — Context

## Locked decisions

- **Coarse taxonomy, named constant, extension-derived at scan time** —
  zero API cost, works on every backend. Buckets: `logs`, `media`,
  `archives`, `data`, `docs`, `other` (default). Compound extensions
  resolve to the outermost meaningful one (`.tar.gz` → archives);
  matching is case-insensitive; keys without an extension → `other`.
  The map is a module constant — arguable, greppable, testable.
- **Opt-in dimension exactly like owner** (`--rollup-types`): cell key
  grows to an ALWAYS-6-tuple (container, prefix, class, band, owner,
  data_type) with `""` when the flag is off — per constraint card
  constraint-d876930a, every unpacker updates in the same commit
  (band_totals, persist_rollups, write_csv, cost merge). Additive
  `data_type` column on StoragePrefixStat, schema guard extended,
  roundtrip test per column.
- **Dimensions combine** — owners × types multiplies cells; the --help
  text carries the cardinality warning for both flags.
- **Recommendations, not new machinery**: `type-split` is a fifth rec
  kind that fires ONLY when the run recorded types, ≥2 types each hold a
  meaningful byte share at one level, and no stronger rec applies.
  Precedence stays: compact-first > date-split > straight-lifecycle >
  zone-split > type-split. Compact-first and zone-split rationales name
  dominant types when known; recs carry `top_types` attribution beside
  `top_owners`, surfaced in console, PROPOSAL.md, HTML report, and
  /storage.
- **v4's out-of-scope declaration retires**: the "data-type grouping out
  of scope" note in structure.py OUT_OF_SCOPE_NOTES is replaced by a
  "types recorded only when --rollup-types was used" note when absent —
  the gap closes, the honesty stays.
