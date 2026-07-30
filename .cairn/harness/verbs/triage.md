---
verb: triage
args: "[--stale-days N] | --apply"
status: live
---

Open-issue sweep against project conventions — a health check on the
tracker itself, not a review of the code (that's `review`) or a retro
against old claims (that's `audit`). Report by default; `--apply` executes
only the safe subset. Every run closes the same way: a record, then
(under `--apply`) a comment on the issue itself — never a new issue about
an issue.

## The sweep

`issue_list(state: "open")`, then classify each issue:

| class | rule | severity |
|---|---|---|
| resolved-but-open | `cairn:bug`/`cairn:audit`/`cairn:review` label AND its trace (via `session_landscape` resolutions) or audit record names it resolved | important |
| stale | `updatedAt` older than N days (default 14) | minor |
| unlabeled | zero labels | minor |
| bodiless | empty body | minor |
| unowned-in-progress | `state: in_progress`, no assignee | minor |
| possible-duplicate | title near-match against another open issue (judgment, not regex — reason about it) | minor |
| priority-inversion | `graph_report()` `priorities` names it — declared priority label weaker than the effective priority it inherits from what it blocks | important |

`--stale-days N` overrides the default of 14; no config key, it's a flag
only — this isn't `cairn.json` surface.

**Resolved-but-open is an evidence rule, not a vibe.** Cross-check
`cairn:bug` issues against `session_landscape` resolutions, and
`cairn:audit`/`cairn:review` issues against `.cairn/audit/` records. No
evidence naming the resolution means the issue doesn't land in this
class, full stop — a hunch that a bug "feels fixed" isn't evidence.

**Priority-inversion comes from the graph, not from judgment.** On trackers
with `hasDependencies` (e.g. `local`), call `graph_report()` once for the
sweep; each `priorities` row IS the finding — issue, effective priority,
and the issue it inherits from. Skip the class silently on `UNSUPPORTED`
backends; never infer inversions by eyeballing titles.

## Report (always)

`audit_record(scope: "triage", verdict, findings)` — one finding per
flagged issue, every finding carrying its `issue:` id. Plain-language
summary to the user, grouped by class, with a proposed action per issue.

No new issues are ever created here — the mirror touch is a comment on
the existing issue, and only under `--apply`. This is the one deliberate
deviation from `audit`/`review`'s "critical/important → new tracker
issue" rule: every triage finding already has a tracker object, the issue
itself. Filing a new issue about an issue is noise, not signal.

## `--apply` (the safe subset only)

| class | action |
|---|---|
| unlabeled | `issue_update` adding the best-fit label — from the labels already in use on the project (`issue_list` shows the vocabulary), never a new label name |
| stale | `issue_comment` nudge, plain language, one line |
| resolved-but-open | `issue_comment` naming the evidence (trace id / record scope + resolution text), then `issue_close` |
| possible-duplicate | cross-linking `issue_comment` on BOTH issues |
| priority-inversion | `issue_comment` naming the inheritance in plain language — what it blocks, that issue's priority, what this issue is labeled — so a human can raise the label |
| bodiless | report-only, always |
| unowned-in-progress | report-only, always |

**Never-rules:**

- Duplicates are never auto-closed — cross-link and stop; closing a
  duplicate is a human call (or a later explicit instruction).
- Bodiless and unowned-in-progress are always report-only — writing
  someone else's issue body or assigning their work isn't triage's job.
- Labels come only from the vocabulary already in use — `issue_list`
  shows what's live on the project; inventing a new label name is not
  triage's call to make.
- Priority labels are never rewritten — an inversion gets a comment
  naming the inheritance; raising the declared priority is the human's
  move.
- A close always quotes its evidence in the comment first, then
  `issue_close` — never close on the strength of the classification
  alone.

## Discipline

Leak-pattern rules apply to every comment triage writes, same as `trace`,
`audit`, and `review` — plain language, no code blocks, no file paths, no
internal refs a non-engineer would bounce off of.

Re-running triage the same day supersedes the record — same semantics as
`audit`/`review`, free from `audit_record`'s date-suffixed scope. Nothing
is ever deleted — not a finding, not a comment, not an issue. A `--apply`
run that finds nothing to apply still writes the report; a bare `verdict:
pass` is proof the sweep ran, same as it is for `audit`.

## Bare vs. `--apply`

A bare `triage` mutates nothing on the tracker — it reads, classifies,
and records. `--apply` is the only path that writes a comment, adds a
label, or closes an issue, and it only ever touches the safe subset above.
When in doubt about whether a finding qualifies for `--apply`, it doesn't
— report-only is the safe side to be wrong on.
