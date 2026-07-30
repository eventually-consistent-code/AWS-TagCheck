---
verb: resync
args: ""
status: live
---

Both directions of drift in one verb: commits the plan never saw (git
side) and tracker changes the plan never saw (tracker side).

## Git side

1. `plan_resync()` — first run just initializes the marker (say so).
2. No out-of-band commits → git side clean.
3. Otherwise group the commits by likely phase (file paths vs each phase's
   PLAN.md task areas — judgment, say your reasoning) and present the
   report: sha, subject, files, suspected phase.
4. For each affected phase, batched into one AskUserQuestion per phase at
   most: refresh CONTEXT.md (what the out-of-band work changed about the
   locked decisions) and PLAN.md task notes. Assumptions broken outright →
   offer `/cairn:plan <N> --gaps`.
5. The git marker already advanced (the tool did it) — re-running reports
   clean from here.

## Tracker side

6. `plan_tracker_delta()` — peek (no `ack`). First run initializes the
   cursor (say so, done). Clean → report clean, done.
7. Render the grouped delta, then batch adoption into one AskUserQuestion:
   - **New phase (epic)** → `plan_import` with the phase reference — the
     standard gap interview follows.
   - **New issue (story/task)** → best-fit phase by judgment (topic and
     file-path match against each phase's PLAN.md — show your reasoning),
     folded in via `plan_issues_set` plus a PLAN.md task note. No
     confident fit → offer the phase choice explicitly.
   - **Edited issue** → integrates forward: a cursor-detected edit is
     provenance-known newer human intent and wins over the plan docs.
     Title/scope → PLAN.md task text; labels/priority → wave and ordering
     notes; body → the phase CONTEXT.md refresh. Exception: an edit that
     collides with a locked decision in CONTEXT.md stops for the user —
     conflict, not adoption — with the collision spelled out.
   - **State change** → remedy only: externally closed-unverified points
     at `/cairn:verify <N>` (or reopen); externally reopened points at the
     phase's plan.
   - **Declined items** → label `cairn:backlog` via `issue_update` so
     `status` keeps surfacing them; declined edits get a ⚠ reconcile
     `issue_comment` so the editor sees why the plan didn't follow.
8. Adoption flow complete → `plan_tracker_delta(ack: true)` to advance the
   cursor. Un-acked deltas re-surface on every scan — never ack before the
   adoption question has been answered.
