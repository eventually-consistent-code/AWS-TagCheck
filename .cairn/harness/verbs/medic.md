---
verb: medic
args: "[--repair] | forensics [phase]"
status: live
---

A health check for the planning directory itself — not the code, not the
tracker's issue hygiene (that's `triage`), the plan artifacts and whether
they still line up with what actually happened. Bare `medic` reports;
`--repair` fixes only what's mechanical; `forensics` reconstructs a story
from the evidence trail. All three close the same way: a record.

## `medic` (health)

1. `plan_status` — every phase's declared state and what artifacts exist
   for it.
2. `plan_drift` — where the plan docs and the live repo have quietly
   diverged.
3. `plan_check` — contract drift and unanchored thresholds per phase.
4. Ledger/file cross-checks: does every phase `plan_status` reports have
   a `LEDGER.md`, a `PLAN.md`, a phase directory that actually exists on
   disk? Does every ledger entry point at commits that are still there?
   A phase marked verified with no ledger evidence behind it is a finding,
   not a pass.
5. Rank findings — a missing phase directory blocks everything downstream
   of it; a stale plan-issue link is cosmetic. Rank by what breaks next if
   it's ignored, not by how many there are.
5b. Dependency-graph integrity (trackers with `hasDependencies`):
   `graph_report()` — every entry in `dangling` is a broken relationship
   (an edge whose issue no longer exists). Report each as
   "`<from>` —`<type>`→ `<to>`: endpoint missing." Skip silently on
   `UNSUPPORTED` backends.
6. `audit_record(scope: "medic", verdict, findings)` — same discipline as
   `audit`: the record is the source of truth even when every finding is
   minor, and a clean bill of health still gets a `verdict: pass` record
   as proof the check ran.

## `--repair` (mechanical structure only)

Only after the health record exists. Three moves, and only three:

| finding | fix |
|---|---|
| phase directory missing or incomplete | `plan_phase_ensure` |
| phase scaffold missing (PLAN.md, LEDGER.md, etc.) | `plan_scaffold_phase` |
| stale or missing plan↔issue links | `plan_issues_set` |
| dangling issue-graph edge (endpoint deleted) | `issue_unlink` per `graph_report().dangling` entry |

**Never-rule: `--repair` touches structure, never content.** It creates a
missing directory, scaffolds a missing file, or relinks a stale issue
reference — it never rewrites what a `PLAN.md` says, never resolves a
`plan_drift` finding by editing the plan to match reality (or reality to
match the plan), and never guesses at what an ambiguous phase state
*should* mean. Anything judgment-shaped — a drift finding with no obvious
correct side, a plan that contradicts itself, a phase whose scope clearly
changed mid-flight — gets reported in the record and named explicitly as
"not auto-repaired, needs a human call." Executing a judgment call under
`--repair`'s roof is exactly the failure mode this verb exists to avoid.

Each mechanical repair is one tool call, logged in the record against the
finding it closed. `--repair` never invents a new finding to fix — it
only acts on findings the health pass already surfaced.

## `forensics [phase]`

Reconstruct what actually happened, from evidence, not from what the plan
docs claim happened. No phase named means the most recently active one
per `plan_status`.

1. `LEDGER.md` for that phase — the append-only record of what was
   claimed done and when.
2. `git log` scoped to the phase's commit range — what actually landed,
   in what order, and whether it matches the ledger's story.
3. Tracker issue history for the phase's labeled issues — what was
   opened, when it closed, and what the closing comment said actually
   happened.
4. Weave the three into one narrative: what was planned, what shipped,
   where the ledger and the git history and the tracker agree or don't.
   A forensics answer names the disagreement when there is one — "ledger
   says phase 4 closed clean; git log shows two commits after that claim
   touching the same files" is the shape of answer this exists to produce.
5. `audit_record(scope: "medic-forensics-<phase>", verdict, findings)` —
   the narrative and any discrepancies found, written as the record.

**Nothing is mutated.** Forensics reads three sources and writes one
record — no repair, no tracker comment, no file edit. It answers "what
happened," full stop; if the answer implies a repair, that's a follow-up
`medic --repair` or a human decision, never something forensics does on
its own initiative mid-narrative.

## Discipline

Same house rules as `audit`/`triage`: the record exists even on a clean
pass, plain language wherever a finding is described, and `--repair`
never operates without the health record it's repairing already on file.
