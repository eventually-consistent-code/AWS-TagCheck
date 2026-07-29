---
verb: do
args: "\"<request>\""
status: live
---

Freeform smart router — classify the request against the routing table's
purpose column and dispatch.

1. Match the intent to exactly one live verb (and its arguments, extracted
   from the request — phase numbers, queries, flags).
2. Read-only verb (`status`, `recall`, `help`) with a clear match → run it
   directly.
3. Mutating verb (`new plan work verify ship import remember`) or low
   confidence → confirm first: "Sounds like `/cairn:plan 4 --deep` — run it?"
4. Matches a reserved verb's purpose → say which tier ships it and offer the
   nearest live alternative.
5. No plausible match → `verbs/help.md`.
