---
verb: scout
args: "<N>"
status: live
---

Research the given phase WITHOUT planning it — `plan`'s research stage alone,
resumable (#1961 shape: never redo finished research).

1. `plan_status()` — phase dir must exist (else `plan_scaffold_phase` with
   `research: true` first).
2. If RESEARCH.md exists, parse its section markers: each `## <topic>`
   section carries `<!-- scout: done -->` or `<!-- scout: pending -->` on
   the line after the heading. Sections marked `done` are FINISHED — do not
   re-research them. No marker = legacy content, treat as done.
3. Determine research topics from CONTEXT.md unknowns + PLAN.md gaps (depth
   dial and model routing per the `cairn-planning` skill). New topics get
   `pending` sections appended; only `pending` sections get researched.
4. Research each pending section (fan out per the model-routing rubric);
   write findings into its section and flip its marker to `done` as EACH
   section completes — a kill mid-run must lose at most one section.
5. `mem_index` the finished brief (source: the RESEARCH.md path). Report
   sections done/remaining and suggest `/cairn:plan <N>`.
