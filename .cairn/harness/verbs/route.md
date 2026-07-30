---
verb: route
args: "insert|remove|edit <N> [\"name\"]"
status: live
---

Roadmap surgery. Never renumbers existing phases — decimal insertion only
(renumbering is where GSD broke).

- **insert `<N.5>` "name"** — confirm placement, then `plan_scaffold_phase`
  with the decimal number and name, `plan_phase_ensure` for the tracker
  object, add the roadmap.md row between its neighbors. Existing phases
  untouched.
- **remove `<N>`** — show what dies first: the phase's open issues
  (`issue_list` by phase) and artifacts. One batched AskUserQuestion:
  confirm removal + per open issue close-or-reassign. Then: close/reassign
  issues (`issue_update`/`issue_close`), close the tracker phase object if
  the backend supports it (`hasPhaseClose` — else annotate its name via the
  backend's usual update path and say so), move the phase dir to
  `.cairn/plans/milestones/removed/`, strike the roadmap row
  (`~~Phase N~~`).
- **edit `<N>` "new name"** — retitle/rescope: rename the phase dir slug
  (git mv), update the roadmap row and PLAN.md/CONTEXT.md headings, update
  the tracker phase name (backend update path). Scope changes to CONTEXT.md
  are locked-decision edits — record what changed and why.
