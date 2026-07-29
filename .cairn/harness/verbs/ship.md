---
verb: ship
args: ""
status: live
---

Pre-ship gate, then ship:

1. `plan_drift()` — anything flagged: **stop** and report; do not push.
2. `plan_status()` — every phase with VERIFICATION.md must show all its issues
   closed (`issue_get` spot-check); report any still open and stop.
3. Engineer mode only (`user.mode: engineer` in cairn.json): no
   cairn-authored PR may still be awaiting human review — list any that
   are and stop. Human review is the merge gate; ship never overrides it.
4. Clean gate → commit outstanding plan-doc changes, push the branch,
   `continuity_clear()` (shipping ends the session), and (if the project uses
   PRs) offer to open/update one.

Never push with flagged drift or open issues on a verified phase.
