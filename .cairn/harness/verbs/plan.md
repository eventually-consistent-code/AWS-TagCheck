---
verb: plan
args: "<N> [--quick|--deep] [--model <auto|haiku|sonnet|opus>] [--tdd] [--mvp] [--prd <file>] [--ingest <glob>] [--gaps]"
status: live
---

Plan the given phase per the `cairn-planning` skill's depth dial.

0. `plan_tracker_delta()` — peek. Anything in the delta → say so in one
   line ("tracker delta: 2 new, 1 edited — `/cairn:resync` to integrate")
   and continue; a non-empty delta never blocks this verb. First run:
   the tool initializes silently, don't mention it.
1. `plan_status()` — confirm the phase dir exists (else `plan_scaffold_phase` first;
   deep depth passes `research: true`).
2. Depth (flag > PLAN.md frontmatter `depth:` > cairn.json default > standard):
   - quick: no research; draft PLAN.md tasks directly.
   - standard: one research subagent for unknowns; write RESEARCH.md if material.
   - deep: parallel research fan-out per the skill's model-routing rubric, then a
     plan-checker pass over the draft.
3. Write the task breakdown into the phase's PLAN.md body. Keep decisions in
   CONTEXT.md (precedence per shared rules — the tracker gets updated, not
   followed).
   - Estimate every issue this verb creates (`issue_create` here and in
     steps 4–5): `estimatePoints` from task complexity (quick/mechanical
     1–2, standard 3–5, deep/cross-cutting 8), `estimateMinutes` as an
     honest wall-clock guess. Backends without estimate fields ignore them
     silently — always pass both. Worklog on close records the actual;
     together they make burndown/velocity/estimate-vs-actual reports real.
4. Flags (combinable; all task-list changes still flow through `plan_issues_set`
   / `plan_meta_set`, never hand-edits):
   - `--mvp`: shape tasks per the cairn-planning skill's vertical-slice-first
     policy before writing PLAN.md.
   - `--prd <file>`: read the file first; interview ONLY the gaps it leaves,
     batched into one AskUserQuestion.
   - `--ingest <glob>`: read matching docs; write their decisions into
     CONTEXT.md as locked decisions with source links. Conflicting docs →
     surface the conflict, never silently pick.
   - `--tdd`: per task, judge eligibility per the cairn-planning rubric;
     batch the proposed eligible/ineligible split into ONE AskUserQuestion
     for overrides; then `plan_meta_set(phaseDir, tdd: [<eligible ids>])`.
   - `--gaps`: read this phase's VERIFICATION.md failures + the latest
     `plan_resync` report; propose new/amended tasks. Goal-breaking gaps →
     issues in this phase now (`issue_create` + `plan_issues_set`); minor →
     offer to backlog. Severity call is yours; say which and why.
   - Wave grouping (with or without flags): when tasks are independent,
     propose waves and write them with `plan_meta_set(phaseDir,
     waves: [[ids…], …])`. Waves must partition cleanly — an issue in two
     waves is a tool error.
5. Reconcile: `plan_drift()` — resolve anything flagged for this phase
   (recreate missing issues via `issue_create` + `plan_issues_set`; question
   closed-unverified ones with the user).
6. Adopt: `plan_unplanned()` — for any unplanned issue that belongs to this
   phase, add its id via `plan_issues_set` (and set its tracker phase with
   `issue_update` if the backend supports phases). Ask before adopting.
7. Report the plan summary and next step `/cairn:work <N>`.
