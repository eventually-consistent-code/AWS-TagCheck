---
verb: brief
args: "[--stdout]"
status: live
---

Onboarding briefing for someone who wasn't there (#1219). A view, not a
source of truth — regenerate wholesale each run.

1. Gather: PROJECT.md (vision, requirements), roadmap.md (milestone,
   phase table, archive section), per-phase one-liners from LEDGER.md
   summaries, decision/constraint cards at confidence high (medium only
   when directly load-bearing) via `mem_card_list`.
2. Compose one readable briefing: what this project is, where it stands
   (milestone/phases shipped), how it's structured, the decisions and
   constraints a newcomer must respect, where to start.
3. Cache-stability rules: no volatile timestamps (date granularity only),
   stable ordering.
4. Default: write `docs/BRIEF.md` (full overwrite — it is generated) and
   say so; `--stdout`: print instead of writing.
