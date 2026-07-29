---
mode: agent
description: Cairn ship gate — drift-clean + no open issues, then push
---

Run the cairn `ship` verb (no arguments: ${input:args}).

1. Read `.cairn/harness/SKILL.md` — the verb registry and shared rules
   apply to every step.
2. Read `.cairn/harness/verbs/ship.md` and execute it with the given
   arguments, exactly as written.
3. Every tool it names (plan_*, issue_*, mem_*, ...) lives on the `cairn`
   MCP server — call the tools; never edit `.cairn/` state by hand.
