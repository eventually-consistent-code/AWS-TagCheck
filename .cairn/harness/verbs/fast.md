---
verb: fast
args: "\"<change>\""
status: live
---

Trivial inline change. No plan artifacts, no phase — but still
tracker-first: every change is visible where the team looks.

1. Guardrail first: if the change plausibly touches >3 files or needs
   design judgment, STOP and suggest `/cairn:plan` — before creating
   anything.
2. `issue_create(title: <change>, labels: ["fast"])`.
3. Make the change. The moment it grows past 3 files: stop, report, leave
   the issue open with a note, suggest `/cairn:plan`.
4. Tests relevant to the touched files pass → ONE atomic commit
   (conventional message).
5. `issue_close(id)` — close note carries the commit sha. No ledger entry
   (no phase). Report: issue, files, sha.

## Paper trail

Every tracker state transition this verb makes carries a comment — claim
("starting: <one line of intent>"), close (what shipped, evidence, "time
spent: ~Xm (approximate)" from claim to close, passed to `issue_close` as
`timeSpentMinutes`), or parked (why, what remains). Milestone progress
comments where the work is long enough to have milestones; batch small
steps into one comment. Leak-guard discipline applies to every comment.
