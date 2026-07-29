---
verb: thread
args: "[\"<name>\" | (none = list open) | --wrap]"
status: live
---

Persistent context threads — long-running context that survives `/clear`,
mirrored to the tracker like every other session. A thread isn't a bug hunt
or a spike; it's the running memory for something that spans more sittings
than your context window does.

## `thread "<name>"` — start or resume

1. `thread_start(description)` — creates the `cairn:thread` issue. If one's
   already open under this name, the already-open guard fires: resume IS
   the point, not a duplicate. Re-read `.cairn/thread/<id>.md` and pick up
   from the last entry — don't start over, don't re-derive context you
   already wrote down.
2. On a genuine start, mirror comment #1 via `issue_comment`: "Thread
   started: <plain summary>" — what this thread is tracking and why it
   needs to outlive a single sitting.
3. On resume, re-ground silently — the file is the memory, not your head.
   No mirror comment on resume; the tracker already knows this thread is
   open.

## Bare `thread` — list open threads

1. `session_landscape` — the only source of truth for what threads are
   open. Don't reconstruct the list from `.cairn/thread/` or from memory.
2. Show the open threads and offer to resume one — bare `thread` is a menu,
   not an action.

## Entry discipline

Log as the work happens, not in a batch at the end — a thread that only
gets written to at wrap time isn't doing its job.

- `thread_log(kind: "note")` — a fact worth keeping that doesn't fit the
  other two kinds.
- `thread_log(kind: "link")` — a reference (file path, issue id, session
  id, URL) PLUS one line of why it matters. A bare reference with no why
  is worthless six sittings from now.
- `thread_log(kind: "decision")` — a choice made and its reasoning, logged
  when it's made, not reconstructed later from memory.

## `--wrap`

1. Log a `wrap` entry summarizing where the thread landed — the wrap gate
   is what makes `thread_close` possible, same as `trace`'s verdict gate.
2. `thread_close(resolution)` — comments "Resolved: <resolution>" on the
   issue and closes it. This is the C2 session factory's close behavior,
   free with the fourth kind — nothing bespoke here.

## Mirror rules

Plain language on the tracker, same as `trace`/`probe`: no code blocks, no
file paths, no internal refs a non-engineer would bounce off of. Two
touches only — start and wrap — not one per entry. The detail lives in
`thread_log`; the tracker gets the arc.

## Leak rules

Same discipline as every other session kind: nothing in a mirror comment
that wouldn't read fine to someone outside the codebase. If an entry has to
reference a file path or a stack trace to make sense, that detail stays in
`thread_log` and never rides a mirror comment.
