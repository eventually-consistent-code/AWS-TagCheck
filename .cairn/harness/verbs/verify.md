---
verb: verify
args: "<N>"
status: live
---

Verify the given phase per the `cairn-planning` skill.

1. Goal-backward: re-read the phase's CONTEXT.md and PLAN.md; check the codebase
   delivers what the phase PROMISED, not merely that tasks closed. Run the test
   suite. Deep depth: adversarial verification subagent per the routing rubric.
2. `plan_drift()` — this phase must contribute nothing flagged.
3. `issue_list(phase: <tracker phase id>, state: "open")` — must be empty; report
   stragglers instead of closing them unexamined.
4. TDD evidence: for every id in PLAN.md `tdd:` frontmatter, this phase's
   LEDGER.md line for that id must carry a `tdd <red>..<green>` segment.
   Any TDD task missing its pair → the phase FAILS verification — report
   which ids, do not write VERIFICATION.md.
5. Write `.cairn/plans/phases/<NN-dir>/VERIFICATION.md`: what was checked, what
   passed, deviations. (Its presence marks the phase verified — drift treats
   closed issues in verified phases as normal.)
6. Report pass/fail and next step (`/cairn:ship` or the fixes needed).
7. FAILED verification routes to `trace` — MANDATORY (#726): open a trace
   (`trace_start` with the failure as the description), log the failing
   output as the first `evidence`, and continue there. Never patch-and-
   rerun inline. Proven-obvious ≤3-line causes may take trace's fast lane —
   still traced, still mirrored.
