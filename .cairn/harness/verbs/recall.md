---
verb: recall
args: "\"<query>\" [--phase N] [--issue <id>]"
status: live
---

Search memory per the `cairn-memory` skill, scoped tight by default.

1. Scope: flags > active context (`context_get`) > whole project.
2. `mem_card_recall(query, scope)` for durable cards — surface each card's
   staleness: `STALE`/`changed`/`deleted` cards are reported with what moved,
   then re-verified per the skill (update or retire; never silently trust).
3. `mem_search(query, filter, limit)` for index matches — matched sections
   only, never raw bulk.
4. Present cards first (they're decisions/constraints/gotchas), index hits
   second; each item cites its source and scope.
