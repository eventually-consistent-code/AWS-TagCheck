---
verb: audit
args: "<mode> [target] | --fix"
status: live
---

Cross-phase quality audits — a retro-check against what was already
claimed done, not a new review invented on the spot. Every mode closes the
same way: a record, then tracker issues for anything that matters.

## Modes

| mode | scope | how |
|---|---|---|
| `uat [phase]` | walk shipped flows as a user would | pick the flows a user actually runs, walk each one end to end on a named platform matrix (desktop + mobile viewport at minimum), capture evidence and a pass/fail verdict per flow; sweep requirement traceability (map edges) and name any untraced requirement as an important finding — dispatch to the `cairn-uat` agent as the specialist |
| `milestone [n]` | every phase in the milestone | goals vs delivered, phase by phase: `plan_status` for what was planned and what artifacts exist, `issue_list` for what's still open, ledger entries for what's actually verified |
| `security [phase]` | retro-audit against the phase's own bar | re-check the phase's stated security criteria against what shipped — not a generic scan, the criteria the phase itself committed to |
| `security --surface` | the agent-config attack surface | sweep the layer code audits never see: `.claude/` settings + hooks (commands that curl-pipe, write outside the project, or run with `dangerouslyDisableSandbox`), plugin manifests and their hook definitions, `.mcp.json` / MCP configs (servers pulled from unpinned or untrusted sources, env-var names that leak secrets into args), permission allowlists broader than the project needs, and any credential literal in config files (`cairn.json` refuses them; other tools' configs don't). Severity scale unchanged; every Critical/Important finding mirrors as a tracker issue like any other audit |
| `ui [phase]` | same, against the phase's UI criteria | includes the fidelity contract: compare shipped UI against the draft session's decided direction and `tokens.json`; a divergence is a finding citing the specific decision entry it violates — the `cairn-uat` agent hands these off when its walk turns one up |
| `eval [phase]` | same, against the phase's eval criteria | |
| `validation [phase]` | same, against the phase's validation criteria | |
| `tests [phase]` | find untested requirements | walk the phase's requirements against what's actually covered, and where a requirement has no test, WRITE it — don't just flag the gap — then `ledger_append` the evidence |
| `plans [phase]` | plan-quality scan | `plan_check(phase)` for contract drift and unanchored thresholds, findings translated into plain language before they go anywhere near a human |
| `docs [scope]` | sweep README/docs claims against the codebase | read every claim a README or `docs/**` file makes about what's shipped (tool counts, verb lists, table shapes, file paths, commands) and check each one against the real codebase — `check-surface.mjs`'s numbers, `server/src/index.ts`'s registry, the actual files on disk. A claim that's drifted from what's actually there is a finding, same severity scale as every other mode. No `scope` means sweep every README + `docs/**` file; a `scope` narrows to one file or directory. |

**Visual evidence:** when the tracker declares `hasIssueAttachments`
(jira, local), `issue_attach` the walk's screenshots and renders to the
finding's issue — visual findings get a tracker-visible home, not just a
repo path. Backends without attachment support keep today's behavior:
the evidence path lives in the audit record only.

`security` / `ui` / `eval` / `validation` are the same shape: pull the
phase's own stated criteria (PLAN.md, SPEC docs — whatever that phase
committed to), check delivered state against it, don't substitute a
generic checklist for the phase's actual bar.

**Milestone mode resolution:** resolve `n` via `milestone_list` first (handles
both current and archived milestones). No `n` means audit the current milestone.
If `n` is archived, read artifacts from `milestones/v<n>/` instead of live
`plan_status` phases.

No target on a phase-scoped mode means: figure out the most recently
active phase from `plan_status` and audit that.

## Closing discipline — every mode, no exceptions

1. `audit_record(scope, verdict, findings)` — `scope` names the mode and
   target (e.g. `"uat-12"`, `"milestone-3"`), `verdict` is `pass` or
   `findings`, and `findings` is the full list even when most of them
   never make it to the tracker. This file is the source of truth; the
   tracker is the summary.
2. For each finding rated **critical** or **important**: `issue_create`
   with label `cairn:audit`, a plain-language title a non-engineer could
   read cold, and the severity as the literal first line of the body
   (`Critical: …` / `Important: …`) — no burying it in paragraph three.
3. **Minor** findings stay in the audit record only. Not every rough edge
   earns a tracker issue; the record already has them, and a tracker full
   of minors is a tracker nobody reads.

Skipping the record because the audit came back clean is still skipping
it — a `pass` verdict is a finding too, and it's the one that proves the
audit ran.

## `--fix`

Only after the record exists and the audit-worthy issues are filed. Two
shapes, and only two:

- **Mechanical** (the fix is obvious and small — a missing null check, a
  stale config value, a skipped test now written): fix it directly, one
  commit per finding, then `issue_comment` with a plain-language "what was
  wrong / what changed" note, then `issue_close`. For `docs` mode, a
  drifted claim is always mechanical — edit the README/doc line to say what
  the codebase actually does, one commit per finding, same close discipline.
- **Investigation-shaped** (the fix isn't obvious, or fixing it risks
  touching more than the finding itself): open `trace_start` instead and
  hand it off — don't guess at a fix under audit's roof.

Never an improvised inline fix for anything in between. If it's not
clearly mechanical, it's investigation-shaped by default — that's the
safe side to be wrong on.

## Paper trail

Every tracker state transition this verb makes carries a comment — claim
("starting: <one line of intent>"), close (what shipped, evidence, "time
spent: ~Xm (approximate)" from claim to close, passed to `issue_close` as
`timeSpentMinutes`), or parked (why, what remains). Milestone progress
comments where the work is long enough to have milestones; batch small
steps into one comment. Leak-guard discipline applies to every comment.

## Mirror rules

Same discipline as `trace` and `probe`: plain language, no code blocks, no
file paths, no internal refs a non-engineer would bounce off of. The
severity-first-line rule on `issue_create` bodies is the one addition —
audit issues get triaged by severity before anyone reads the rest.
