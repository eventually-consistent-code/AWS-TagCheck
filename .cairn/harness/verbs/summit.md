---
verb: summit
args: ""
status: live
---

Complete the current milestone. The server gates hard — nothing archives
until every phase is verified.

1. `milestone_list()` + `plan_status()` — show what's completing: phases,
   verification state, native milestone (when the backend has one). Any
   unverified phase → stop, list them, point at `/cairn:verify <N>`. If the
   backend has `hasMilestones` and `milestone_list()` shows no current
   native milestone id (first-milestone case — nothing has stamped one
   yet), fold an offer to create one now into step 2's question.
2. Interview the milestone summary (1–3 sentences, what shipped) — one
   AskUserQuestion, batched with the "start next milestone?" question and,
   when step 1 flagged a missing native milestone, a "create the native
   milestone for v<N> now?" question (suggest name `v<N>`). On yes:
   `milestone_create("v<N>")` before step 3.
3. `milestone_complete(summary)` — closes tracker phases (skips recorded
   for backends whose phase primitive can't close), releases the native
   milestone when supported, archives `phases/` → `milestones/vN/`, bumps
   roadmap. On PRECONDITION_FAILED or TRACKER_DOWN: report and stop —
   re-running after a fix is safe (idempotent).
4. Git (agent-side, server never writes git): commit the archive
   (`chore(cairn): summit — v<N> archived`) and tag `v<N>`.
5. `continuity_clear()` — the milestone is done; no handoff survives it.
6. If starting the next milestone (from step 2's answer):
   `milestone_create("<name>")`, then the next-milestone interview —
   goals, first phases — batched; scaffold via `plan_scaffold_phase` +
   `plan_phase_ensure`; add roadmap rows. Otherwise report and stop.
