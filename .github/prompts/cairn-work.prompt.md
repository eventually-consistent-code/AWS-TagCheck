---
mode: agent
description: Execute a cairn phase — claim issues, do the work, close on verified done
---

Run the cairn `work` verb (phase number, e.g. 2: ${input:args}).

1. Read `.cairn/harness/SKILL.md` — the verb registry and shared rules
   apply to every step.
2. Read `.cairn/harness/verbs/work.md` and execute it with the given
   arguments, exactly as written.
3. Every tool it names (plan_*, issue_*, mem_*, ...) lives on the `cairn`
   MCP server — call the tools; never edit `.cairn/` state by hand.
