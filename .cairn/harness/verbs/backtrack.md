---
verb: backtrack
args: "<phase|plan> | --apply"
status: live
---

Safe git undo, scoped to what the ledger says shipped — never a blind
`reset`. `backtrack <phase|plan>` computes the exact revert set and shows
it; `--apply` is the only path that touches history, and it only ever
adds revert commits, never removes the originals.

## `backtrack <phase|plan>` (compute, never mutate)

1. Read `LEDGER.md` for the target phase (or every phase in the named
   plan) — the commit ranges it recorded as this work landing.
2. Build the revert set: exactly the commits the ledger attributes to
   that phase/plan, nothing inferred, nothing added because it "looks
   related."
3. **Overlap check.** For every commit in the revert set, look for LATER
   commits (by the same range, any author) that touch the same files.
   A later commit touching a file the revert set also touches means that
   file can't revert cleanly without risking the newer work — flag it,
   named file by file: which file, which later commit, which revert-set
   commit it collides with. Overlap is never resolved automatically — it
   means manual review before `--apply`, full stop.
4. Present the plan: the ordered revert list (newest-first, the order
   `--apply` will actually run in), the overlap findings if any, and what
   `--apply` will do next. Nothing has been touched yet — this is a dry
   run every time it's called without `--apply`.

## `--apply`

Only after the plan above has been shown and any overlap has been
reviewed and accepted.

1. `git revert --no-edit`, one commit at a time, in reverse order (newest
   commit in the set reverted first) — never a single squashed revert,
   so each original commit keeps its own paired revert commit in the log.
2. Run the test suite after the reverts land. A red suite is reported as
   part of the outcome, not silently swallowed — `--apply` doesn't stop
   partway through to "fix" a failure; it reports what broke and lets a
   human decide the next move.
3. Report: which commits were reverted, in what order, the suite result,
   and any overlap that was accepted going in.
4. Tracker mirror: `issue_comment` on the phase's (or plan's) tracker
   issues naming what was reverted and why — plain language, same
   discipline as `trace`/`audit`/`triage`, no code blocks, no file paths.
5. `audit_record(scope: "backtrack-<phase|plan>", verdict, findings)` —
   the revert set, the overlap findings, the suite result, all as one
   record, whether or not `--apply` ran.

## NEVER-rules

- **NEVER `git reset --hard`.** A backtrack is additive — it reverts, it
  does not rewrite history out from under anyone who already pulled it.
- **NEVER force-push.** `--apply` operates on the local branch; getting
  the reverts onto the remote is a normal push, and that push is the
  user's call to make, not this verb's.
- **NEVER touches anything outside the ledgered manifest.** Only commits
  the ledger attributes to the named phase/plan are ever candidates for
  the revert set — no "while I'm in here" scope creep.
- **Remote untouched, always.** `backtrack` computes and applies local
  reverts; it never pushes, never opens a PR, never notifies anyone
  before the tracker-mirror comment in step 4. Pushing the reverts is the
  user's call.

## Discipline

Every finding and every applied revert lands in the record — a bare
compute run with nothing to revert (empty ledger range) still writes a
`verdict: pass` record, same as a clean `audit` or `triage` pass proves
the check ran. Overlap is the one thing this verb refuses to decide for
itself; naming it clearly and stopping is the safe side to be wrong on.
