# Phase 4: signal driven recommendations — Context

## Locked decisions

- **No external research** — this phase consumes signals phases 1–3 already
  produce (data types, access-aware last-read, per-prefix request rates).
  Pure engine refinement in structure.py + the five rec surfaces.

- **Every rec carries confidence + evidence.** `Recommendation` gains
  `confidence` (`high`/`medium`/`low`) and `evidence` (list of source
  labels). Persisted in `structure_recs`, surfaced on console, CSV,
  PROPOSAL.md, HTML report, and /storage. The rubric:
  - `prefix-fanout` → high, evidence `["request-rate telemetry"]`.
  - `expire-in-place` → high, evidence `["write-rate telemetry"]`.
  - `compact-first` → high, evidence `["object-size distribution"]`
    (deterministic from the scan, not an inference).
  - cold-driven kinds (`date-split`, `straight-lifecycle`, `zone-split`):
    **high** when the run is access-aware (a still-cold object on an
    access-aware run is telemetry-VERIFIED unread — the enrichment would
    have flipped it fresh otherwise), evidence `["age", "access telemetry
    (verified unread)"]`; **low** when age-only, evidence `["age (no
    access telemetry)"]`.
  - `type-split` → medium, evidence `["age", "data types"]`.

- **Read-verified zone splits = the access-aware confidence bump above.**
  The insight: enrichment already flips read-hot objects into the fresh
  band, so on an access-aware run "cold" means "old AND unread by
  telemetry". No new logic — the cold-driven kinds' confidence encodes it.

- **churn/expire-in-place is a new rec kind.** Fires when rates were
  recorded, a prefix shows meaningful WRITE activity
  (`write_rps >= CHURN_WRITE_FRACTION` of the write ceiling, default
  0.02), AND the prefix has cold data (a transition would otherwise be
  advised). Rationale: names the write rate, warns that transitioning
  churning/short-lived data bills minimum-duration early-delete charges,
  advises expiry-in-place (a lifecycle Expiration) over a transition.
  **Honesty**: logs can't tell overwrite from first-write, so the advice
  is conditional ("if these are short-lived/rewritten objects"), never a
  hard determination.

- **Precedence gains one slot, below fan-out, above transitions:**
  prefix-fanout > expire-in-place > compact-first > date-split >
  straight-lifecycle > zone-split > type-split. Rationale: a live perf
  ceiling is most urgent; then don't-transition-churning-data beats every
  transition-advising kind (including compact-first — compacting churning
  data is pointless).

- **CHURN_NOTE retires** when the run recorded rates (write telemetry
  now feeds expire-in-place). `out_of_scope_notes` drops it under
  `rates_recorded`, same as the fan-out note.

- **Confidence never invents certainty.** age-only cold recs are labeled
  low precisely so a user without telemetry sees the recommendation is a
  weaker inference; folding logs is what earns "high".
