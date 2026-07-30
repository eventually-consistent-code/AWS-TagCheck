---
verb: retro
args: "[<N> | --milestone]"
status: live
---

Write the lessons a future session needs (#1003). Default scope: the last
phase with VERIFICATION.md; `--milestone` spans every phase of the current
milestone (including just-archived `milestones/v<N>/`).

1. Gather evidence: the scope's LEDGER.md lines (what shipped, commit
   ranges), VERIFICATION.md (what passed/failed and how), `git log` over
   the ledger ranges, closed issues (`issue_get` per ledger issue id).
2. Extract lessons — what surprised, what broke, what a future session
   must know. Draft each as a card: `type` decision/constraint/gotcha,
   provenance = the files+commits from the ledger range that prove it,
   confidence: `high` = verified by this scope's events, `medium` =
   plausible inference, `low` = hunch worth recording.
   - **Observation review:** read `.cairn/observations/observations.jsonl`
     (passive capture from the PostToolUse hook — tool, target, error flag
     per call). Look for candidate patterns the ledger can't show: repeated
     error→retry churn on one file or command (a gotcha hiding there),
     hotspot files edited far more than their diff size explains. A pattern
     worth keeping becomes a draft card like any other — confidence `low`
     unless the ledger corroborates it, provenance pointing at the real
     files. Observations NEVER become cards without this review, and after
     the batch is approved, truncate the reviewed observations file —
     retro is the gate and the garbage collector.
3. Re-grade prior knowledge: `mem_card_recall` scoped to this phase — for
   each card, did this scope's events confirm or contradict it? Confirmed
   → `mem_card_update` confidence up one step. Contradicted → down to
   `low`, and draft the corrected lesson as a NEW card (bodies are
   immutable — corrections are new cards, not edits).
4. ONE AskUserQuestion approving the whole batch (new cards + re-grades),
   then write via `mem_card_create` / `mem_card_update`.
5. Report: cards written, cards re-graded (old → new confidence), and the
   one-line reason each.
