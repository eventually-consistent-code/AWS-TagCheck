---
verb: distill
args: ""
status: live
---

Ship-time knowledge synthesis (#3519) — run at/after `ship` or `summit`.
The output must read as if the repo never had planning scaffolding.

1. Inputs: shipped phases' CONTEXT.md locked decisions, PLAN.md outcomes,
   LEDGER.md summaries, decision/constraint cards in scope
   (`mem_card_list`).
2. Generate into `docs/`:
   - ARCHITECTURE.md — per-section merge for what structurally changed.
     NEVER clobber hand-written content: update matching sections, append
     new ones, and surface conflicts to the user instead of overwriting.
   - docs/adr/NNNN-<slug>.md — one ADR per locked decision that shaped
     code (next free NNNN; context/decision/consequences; reference
     commits, not phase dirs).
   - CHANGELOG.md — entries from ledger summaries grouped by milestone or
     phase, newest first.
3. Sanitize BEFORE writing: run
   `node <plugin>/hooks/scripts/leak-patterns.mjs <each generated file>`
   (write to a temp path first). Any hit → rewrite that line to
   public-safe form: tracker ids → plain prose ("the issue tracker"),
   phase/dir refs → the milestone or version name, `.cairn/` paths →
   remove. Re-scan until clean — the scanner exiting 0 is the gate.
4. Show the diff summary (files, sections touched, ADR titles) — ONE
   confirmation — then write and offer a `docs(distill): …` commit.
5. When a docs connector is configured (`docs:` in cairn.json), offer
   `/cairn:docs publish` as the follow-up — distill synthesizes into
   `docs/`; docs publish mirrors it (plus the README) into the connector
   as a landing page + page tree.
