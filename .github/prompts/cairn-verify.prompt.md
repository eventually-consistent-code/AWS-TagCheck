---
mode: agent
description: Goal-backward cairn phase check — drift clean, VERIFICATION.md
---

Run the cairn `verify` verb (phase number, e.g. 2: ${input:args}).

1. Read `.cairn/harness/SKILL.md` — the verb registry and shared rules
   apply to every step.
2. Read `.cairn/harness/verbs/verify.md` and execute it with the given
   arguments, exactly as written.
3. Every tool it names (plan_*, issue_*, mem_*, ...) lives on the `cairn`
   MCP server — call the tools; never edit `.cairn/` state by hand.
