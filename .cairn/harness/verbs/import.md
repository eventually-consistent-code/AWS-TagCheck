---
verb: import
args: "<phase url, id, or name>"
status: live
---

Import tracker-origin work into cairn, per the `cairn-planning` skill.

1. Resolve the phase reference from the argument: if it's a URL, extract the
   identifying segment (milestone number, epic key, list id) for the
   configured backend; otherwise pass the id/name through as-is.
2. `plan_import(phaseRef: <resolved>)` — scaffolds PROJECT.md/roadmap/phase
   docs and writes the phase's issue ids into PLAN.md frontmatter.
   - Ambiguous name → the error lists candidates; re-run with the exact id.
3. Gap interview: the tracker says *what*; ask the user *why* — capture
   vision into PROJECT.md and the phase's locked decisions into CONTEXT.md.
4. Report: phase dir created, issues mapped, next step
   `/cairn:plan <N>` to flesh out the task breakdown or `/cairn:work <N>`
   to start executing.
