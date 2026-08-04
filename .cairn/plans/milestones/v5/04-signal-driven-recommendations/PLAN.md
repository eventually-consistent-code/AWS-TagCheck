---
issues: [39]
---
# Phase 4: signal driven recommendations — Plan

Goal: the recommendation engine consumes phases 1–3's telemetry —
read-verified confidence, write-driven expire-in-place advice, and a
confidence label naming each rec's evidence.

No research fan-out: entirely internal engine refinement; the confidence
rubric, churn trigger, and precedence slot are locked in CONTEXT.

## Tasks

### Issue #39 — signal-driven recommendation upgrades

1. Confidence + evidence on `Recommendation`: add `confidence`
   (high/medium/low) and `evidence` (list). A `_grade(kind, sig,
   access_aware, rate)` helper computes both per the CONTEXT rubric
   (cold kinds high+verified on access-aware runs, low+age-only
   otherwise; fan-out/compact-first/expire-in-place high; type-split
   medium). Wire into `_build_one_rec` and the orphan-fanout path.
   `recs_to_json` persists both; unit tests per kind incl. the
   access-aware confidence bump.
2. `expire-in-place` rec kind: fires per CONTEXT (rates recorded +
   write_rps past `CHURN_WRITE_FRACTION` of the write ceiling + cold
   data present). Slots into `_recommend_for_prefix` precedence BELOW
   fan-out (checked in `_build_one_rec` after fan-out, before the
   lifecycle chain) and ABOVE the transition kinds. Rationale carries
   the write rate + the min-duration-charge warning + the conditional
   "if short-lived/rewritten" honesty. `out_of_scope_notes` drops
   CHURN_NOTE when rates recorded. Tests: fires on a write-hot cold
   prefix, silent without rates or without cold data, beats every
   transition kind but loses to fan-out.
3. Surface confidence + evidence on all five rec surfaces: CLI console
   line + `--structure-csv` columns, PROPOSAL.md per-rec block,
   `html_report` recommendations table column, and the /storage
   recommendations template. `expire-in-place` gets PROPOSAL guidance
   (`output.py` guidance map). Tests: HTML/console show the confidence;
   the web recs page renders the new columns.

## Notes

- Task order 1 → 3; task 1 (confidence) is the widest plumbing, task 2
  the new kind, task 3 the surface pass. The rec-shape change touches
  the persisted `structure_recs` JSON and the HTML table row width — the
  existing structure tests that pin row shape update in the same commit
  (evidence/confidence added, behavior otherwise unchanged).
- expire-in-place is advisory (PROPOSAL guidance), NOT a move-plan kind —
  no key-level manifest; the user applies a lifecycle Expiration.
