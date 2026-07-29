---
mode: agent
description: Cairn project status — phases, issues, drift, unplanned work
---

Run the cairn `status` verb (optionally --stats: ${input:args}).

1. Read `.cairn/harness/SKILL.md` — the verb registry and shared rules
   apply to every step.
2. Read `.cairn/harness/verbs/status.md` and execute it with the given
   arguments, exactly as written.
3. Every tool it names (plan_*, issue_*, mem_*, ...) lives on the `cairn`
   MCP server — call the tools; never edit `.cairn/` state by hand.
