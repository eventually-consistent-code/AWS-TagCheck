---
verb: trace
args: "[\"<bug>\" | <id> | close <id>]"
status: live
---

Persistent debugging session — survives /clear, mirrored to the tracker in
plain language a manager reads (#726). Never debug a routed failure inline.

- **Start** (`trace "<bug description>"`): `trace_start` (creates/links the
  `cairn:bug` issue) → mirror comment #1 via `issue_comment`:
  "Investigation started: <plain summary>". Then the loop, each step logged
  with `trace_log`: `evidence` FIRST (reproduce before hypothesizing) →
  `hypothesis` → `test` (an experiment that can DISPROVE it) → repeat.
  Never two open hypotheses without distinguishing evidence. Hypothesis
  confirmed → mirror comment #2: "Cause identified: <plain language>".
- **Resume** (bare `trace` or `trace <id>`): `trace_list` → pick (bare =
  most recent open) → re-read `.cairn/trace/<id>.md` — the file IS the
  context that survived — continue from the last entry.
- **Close** (`trace close <id>`): fix landed with tests passing → log a
  `verdict` (cause + fix + commit sha) → `trace_close(resolution)` — it
  refuses without a verdict, comments "Resolved: …" and closes the issue.
  Then write the gotcha card: `mem_card_create(type: "gotcha",
  provenance: [files+commits involved], confidence: "high")` — it's
  proven, that's what high means. Commit the archived session file.
- **Fast lane** (cause already proven obvious AND fix ≤3 lines):
  `trace_start` → one `evidence` + one `verdict` → fix → `trace_close`.
  One motion, full paper trail, both mirror touches.
- **Mirror rules:** plain language; no code blocks, no file paths, no
  internal refs; comments at milestones only (started / cause identified) —
  the resolution rides the close.

## Paper trail

Every tracker state transition this verb makes carries a comment — claim
("starting: <one line of intent>"), close (what shipped, evidence, "time
spent: ~Xm (approximate)" from claim to close, passed to `issue_close` as
`timeSpentMinutes`), or parked (why, what remains). Milestone progress
comments where the work is long enough to have milestones; batch small
steps into one comment. Leak-guard discipline applies to every comment.
