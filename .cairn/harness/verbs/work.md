---
verb: work
args: "<N> [--wave [N]]"
status: live
---

Execute the given phase per the `cairn-planning` skill.

**Mode check:** read `user.mode` from cairn.json (`config_get`). Absent or
`vibe` → the procedure below runs exactly as written. `engineer` → the
pairing overlay applies:

- After step 1's issue list, ask "mine or yours?" ONCE for the whole
  wave/phase — one AskUserQuestion listing the issues, the user marks
  which they're taking. Never per-issue friction.
- **cairn-claimed** issues run the unchanged lifecycle below, except the
  finished work lands as a branch/PR and does NOT merge — the close
  comment links the PR and names the human as reviewer (no-self-merge
  gate; `ship` enforces it).
- **human-claimed** issues: cairn scaffolds and steps back — create the
  branch, move the issue to in_progress with `assignee: <user.handle>`,
  and post the claim comment carrying the context: the PLAN.md task text,
  files likely touched, and (for `tdd:` issues) the failing test written
  first. Then wait — do not write further code for that issue.
- **Human says done** (or `resync`/`plan_tracker_delta` shows their
  commits landed): run the tests and the phase's verify posture against
  their work, then the standard close — close comment with evidence and
  approximate time ("logged by cairn for <handle>"),
  `issue_close(timeSpentMinutes: ...)`, ledger entry with their commit
  range. Offer `/cairn:review` on their diff — offer, not force; a
  decline is recorded in the close comment as "review declined".
- Wave ordering, TDD gates, and the failed-issue stop rule apply
  identically regardless of who holds an issue.

0. `plan_tracker_delta()` — peek. Anything in the delta → say so in one
   line ("tracker delta: 2 new, 1 edited — `/cairn:resync` to integrate")
   and continue; a non-empty delta never blocks this verb. First run:
   the tool initializes silently, don't mention it.
1. `plan_status()` → this phase's `issues` list. Empty → stop and point at
   `/cairn:plan <N>`.
2. `--wave` (only when PLAN.md has `wave_N` frontmatter — else say so and
   point at `/cairn:plan <N>`): run waves in order (`--wave N` runs just
   that wave). Within a wave, dispatch one subagent per issue IN PARALLEL —
   worktree isolation for any file-mutating issue. Each subagent runs the
   full per-issue lifecycle below (claim → work → close → ledger). Wave
   N+1 starts only when every wave-N issue is closed and merged. A failed
   issue: let the wave's others finish, then STOP before the next wave and
   report — never build on possibly-broken foundations.
3. For each issue id, in order: `issue_get(id)` — skip closed ones. If it's
   assigned to someone who is not you (compare against `user.handle` in
   cairn.json, only when it's set there — if unset, there are no ownership
   checks), say so and skip unless the user overrides.
4. Before starting an issue: record `git rev-parse HEAD` as this issue's
   `baseCommit` and the current time as its `startedAt` (both feed the
   close in steps 6-7). Then `issue_update(id, state: "in_progress")` —
   and when `user.handle` is set in cairn.json, also pass
   `assignee: <handle>` so teammates see who holds it. Then post the
   claim comment: `issue_comment(id, ...)` — starting now, which wave and
   PLAN.md task this is, base commit as a short ref on its own line.
   Plain language throughout (leak-guard discipline, same as `trace`).
   Then `context_set(phase: <N>, issueId: id)`.
5. Do the work the issue + PLAN.md describe. Track in-session with TaskCreate;
   the tracker stays the durable truth.
   When this issue's id is in PLAN.md `tdd:` frontmatter, the work is
   RED → GREEN → REFACTOR, each its own commit: (RED) write the failing
   test, run it, show the failure, commit; (GREEN) minimal code to pass,
   run, commit; (REFACTOR) clean up, tests stay green, commit. Record the
   RED and GREEN shas — `ledger_append` takes them as `redCommit` /
   `greenCommit` at close. Skipping RED on an eligible task: stop and
   restart the task; verify fails the phase on a missing pair regardless.
   A bug surfacing mid-issue that is NOT this issue's scope routes to
   `trace` (fast lane allowed) — never an inline detour; the trace's
   tracker issue keeps the discovery visible.
   Progress comments as the work lands — real milestones only:
   RED/GREEN/REFACTOR committed, a subtask done, a blocker hit, a trace
   spun off. Several small steps batch into ONE `issue_comment`; tracker
   noise is a failure mode, not diligence. No silent state transitions,
   ever — if the tracker state changes, a comment says why.
6. On completion **with tests passing**: post the close comment first —
   `issue_comment(id, ...)`: what shipped in plain language, the commit
   range as short refs on their own line, the test evidence (suite name +
   pass count), and "time spent: ~Xm (approximate)" computed from
   `startedAt`. When the cost log has rows for this issue
   (`node "$CLAUDE_PLUGIN_ROOT/hooks/scripts/cost-report.mjs" --issue <id>`
   returns > 0), add "agent cost: ~$X (approximate)" beside the time
   line — estimate vs actual vs spend in one comment.
   Then `issue_close(id, timeSpentMinutes: <X>)` — backends
   with worklog support (`worklogLogged: true` in the result) get a real
   worklog entry; the comment line covers the rest. On stopping early:
   leave in_progress and post a parked comment — why it stopped, what
   remains.
7. On `issue_close`: `ledger_append(phaseDir: <NN-slug>, taskRef: id, summary:
   <one line — what shipped>, baseCommit: <HEAD when this issue started>,
   headCommit: <HEAD now>, issueId: id, closedDate: <today, YYYY-MM-DD>,
   redCommit: <RED sha — TDD tasks only>, greenCommit: <GREEN sha — TDD
   tasks only>)` — the durable, git-committed record that the task landed.
8. After the last issue: `context_set(issueId: null)` and suggest
   `/cairn:verify <N>`.
