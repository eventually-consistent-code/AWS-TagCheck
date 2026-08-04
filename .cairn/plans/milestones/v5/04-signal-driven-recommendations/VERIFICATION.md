# Phase 4: signal driven recommendations — Verification

Verified: 2026-08-03 (standard + an adversarial pass, given the phase
changed the engine's core precedence ordering and retired a note the
surfaces render).

## Goal-backward check

Phase promise (#39): recommendations consume phases 1–3's telemetry —
confidence/evidence per rec naming its sources, a write-driven
expire-in-place churn kind, and read-verified confidence on the
cold-driven kinds.

Adversarial verifier: **NOT REFUTED** — all seven attack angles
hand-traced correct, and an `expire-in-place` rec was driven live
through PROPOSAL.md, the HTML report, and CSV with no crashes.

- **Precedence intact**: fan-out write trigger (0.30·3500 = 1050 rps) vs
  churn trigger (0.02·3500 = 70 rps). write_rps in [70, 1050) →
  expire-in-place; ≥1050 → fan-out (checked first, falls through only
  when it doesn't fire). A read-hot prefix that also churns yields
  fan-out — exactly the locked precedence. No band where the intended
  kind loses.
- **Confidence rubric verbatim**: `_grade` returns CONTEXT's exact
  (confidence, evidence) per kind. The access-aware bump reaches ONLY
  the cold-driven fallthrough — type-split/compact-first return before
  it, never wrongly bumped. Orphan fan-out grades high regardless of its
  access_aware=False, evidence stays `["request-rate telemetry"]`.
- **expire-in-place edge cases**: the `cold_bytes == 0` guard precedes
  the `cold_bytes/total_bytes` divide (no ZeroDivisionError; cold_bytes>0
  structurally implies total_bytes>0). Missing/zero write_rps → None.
- **CHURN_NOTE retirement**: with rates recorded both NO_RATES_NOTE and
  CHURN_NOTE are gone; without rates both present. `build_recommendations`
  passes `bool(request_rates)`.
- **Surface completeness**: PROPOSAL guidance dict HAS the
  `expire-in-place` key (no KeyError if that kind appears); HTML header =
  7 cols and both normal AND truncated rows are 7-wide; CSV header = 9
  cols and rows write 9 values; recs_to_json/`_structure_section` use the
  same `confidence`/`evidence` keys (round-trip pinned by
  test_confidence_and_evidence_persist).
- **Honesty**: the churn rationale is genuinely conditional ("IF these
  are short-lived or rewritten … logs can't tell an overwrite from a
  first write — confirm the churn before acting"). Never asserts churn
  as fact.

## Gates

- Tests: 253 passed, 0 failed (11 new in test_storage_signal_recs.py; 2
  updated for the note retirement + reworded CHURN_NOTE).
- Lint: pylint 10.00 (`--rcfile pylintrc`), pycodestyle clean.
- `plan_drift`: transient closed-unverified flag on 39 normalizes with
  this file. Open issues in phase: none. TDD frontmatter: none.
- Ledger: issue 39 with commit range (c319bef..c9d9184).

## Result

PASS — no fixes needed; the adversarial pass found no refutable defect.

## Deviations

- The storage *overview* page (storage.html via app/ui.py) also reads
  `run.structure_recs` but is not one of the five in-scope rec surfaces
  and does not render a per-rec confidence column. Noted, not changed —
  the five named surfaces (CLI console + CSV, PROPOSAL.md, HTML report,
  /storage recommendations) all thread confidence + evidence.
