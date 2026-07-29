---
verb: waypoint
args: "[resume]"
status: live
---

Pause or resume session continuity, per the `continuity` block in cairn.json.

No `resume` argument — pause:

1. Ask for `next_action` (what to pick up next) and `notes` (anything else
   worth remembering), batched in one question.
2. `continuity_checkpoint(source: "waypoint", next_action: <answer>, notes:
   <answer>)` — this merge-patches over the existing handoff, so any stale
   fields it doesn't touch survive; `continuity_clear()` first if a clean
   slate is needed. Phase/issue context comes from `context_get()`.
3. `continuity.wipCommits` is `true` and there's uncommitted work: offer a
   `wip(cairn): waypoint — <next_action>` commit. Never commit without
   asking, flag or not.

`resume` argument — resume:

1. `continuity_get()` — no handoff, or one flagged stale (>14 days): say so,
   offer to inspect or discard, stop.
2. Cross-check trust order (the handoff is a hint, never authority): tracker
   + `git log` outrank LEDGER.md, which outranks the handoff. `issue_get`
   the handoff's issue, read the phase's LEDGER.md, skim `git log` for the
   phase's files. Handoff contradicting the tracker (names an issue as open
   that's actually closed, claims a task the ledger already shows landed):
   report the discrepancy and correct the resume target before proceeding.
3. Confirm the (possibly corrected) task/issue/next_action with the user,
   then resume the work.
4. On confirmed resume: `continuity_clear()`. Offer each
   `decisions_in_flight` entry to `mem_card_create(type: "decision", body:
   <entry>)` — the distill moment a crash would otherwise have destroyed.
