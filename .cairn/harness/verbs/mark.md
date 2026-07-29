---
verb: mark
args: "\"<text>\" [--seed \"<trigger>\"] [--note]"
status: live
---

Capture in ONE tool call. NO questions — never AskUserQuestion, never
"want to add detail?". Structure happens at pickup, not capture (#1309).

- Default (backlog): `issue_create(title: <text>, labels: ["cairn:backlog"])`.
  Echo the id. Done.
- `--seed "<trigger>"`: `issue_create(title: <text>, labels: ["cairn:seed"],
  body: "Trigger: <trigger>")`. Seeds fire as judgment — `status` lists open
  seeds and flags any whose trigger reads as met.
- `--note`: `mem_card_create(type: "note", body: <text>)` scoped to the
  active phase/issue from `context_get` (include scopePhase/scopeIssue when
  set). Notes are knowledge, not work — they never become tracker noise.

Pickup paths: backlog marks get adopted by `plan` (via `plan_unplanned`) or
triaged later; notes surface through `recall` and the session banner.
