---
verb: auto
args: ""
status: live
---

Chained hands-off execution of remaining phases. OPT-IN and explicit: show
exactly what will run before anything runs.

1. `plan_status()` — the run list is every phase with CONTEXT.md and
   without VERIFICATION.md, in order. Show it (phases, issue counts) with
   ONE confirmation question. No CONTEXT.md → that phase is excluded and
   listed as skipped — auto never invents context.
2. Per phase, in order: plan if PLAN.md has no tasks (the `plan` verb's
   steps, standard depth) → the `work` verb's steps → the `verify` verb's
   steps. The A0 handoff tools track progress automatically; a killed run
   resumes via `/cairn:waypoint resume`.
3. HARD STOPS — halt the run, report, hand back: failed verify;
   `plan_drift` flags; any tracker error; any security-relevant decision
   (auth, secrets, data exposure, dependency trust).
   On a failed-verify stop, the report includes the ready-made trace
   handoff: the exact `trace_start` description + first-evidence text.
   auto never starts the trace itself — no self-repair; that is the
   user's move next session.
   Engineer mode (`user.mode: engineer`) adds one more: a completed
   cairn-authored issue whose PR awaits human review is a natural stop —
   auto never merges its own work past a human gate. The run report
   lists the waiting PRs.
4. Unattended decisions resolve against these principles, in order: prefer
   completeness over shortcuts; match existing patterns; choose reversible
   options; mirror the user's past choices; defer ambiguity (pick the
   defer-able reading, note it); escalate security (that's a hard stop,
   not a principle call). Every such decision is logged in the run report
   with the principle that resolved it.
5. Genuinely subjective taste calls (naming, UX copy, structure with no
   pattern to match) do NOT stop the run: take the reversible option, add
   it to the taste batch, present the batch as ONE review at the end.
6. End of run (or stop): report — phases completed, decisions + principles,
   taste batch, stop reason if stopped, next step.
