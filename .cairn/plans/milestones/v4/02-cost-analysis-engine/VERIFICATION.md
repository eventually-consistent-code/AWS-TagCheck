# Phase 2: cost analysis engine — Verification

Verified: 2026-07-31 (deep — adversarial verification per depth dial)

## Goal-backward check

Phase promise: price what old data costs to keep; project honest savings
per management option with transition fees, minimum durations, and
small-object penalties modeled — never averaged away.

First adversarial pass **REFUTED** the phase: the age-out projector
omitted the Glacier per-object overhead and recommended a transition that
actually loses money on 1M×1 KiB objects — the exact honesty case the
phase exists for — plus five further findings (unsupported INT→Standard-IA
transition modeled, promised marginal_rate and CLI override missing,
delete blind to non-STANDARD stale classes, refresh region mislabeling).
Routed to trace-65801319 (tracker issue 31) per verify rule #726; all
findings fixed in eb53d3d. A follow-up validation leak in the new
--age-out-map flag (uncaught UnknownStorageClass) went through
trace-ea647ded (issue 32), fixed in 9d2c74f.

Re-verification by the same adversarial agent at HEAD: **9/9 original
findings CONFIRMED-FIXED** by independent hand-math repro — age-out on
tiny objects now −$0.27/mo not_recommended; INT restricted to AWS's
transition matrix; marginal-rate savings exact across tier breaks
($22.528 = tiered(61 TB) − tiered(60 TB)); stale-GLACIER delete real;
guard fires before the bucket walk; empty slice reports calmly.

## What survived attack unchanged

Tier-ladder math exact to hand computation (60 TB → $1,402.88); GB/GiB
consistent (binary GB throughout); billable-floor and INT-exclusion math
exact; band→class mapping keyed on day values end-to-end with custom
--age-bands; split 8/32 KiB overhead and 90/180d durations confirmed
against live AWS docs; no per-cell ladder restart anywhere.

## Gates

- Tests: 123 passed, 0 failed (26 new this phase).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flags on 21/22 normalize with
  this file; all other issues ok. Open issues in phase: none.
- TDD frontmatter: none declared.
- Ledger: both issues carry commit ranges (3123d7c..9b1f7e8,
  9b1f7e8..e1f1c07); verification fixes in eb53d3d, 9d2c74f.

## Result

PASS — after two traced fix rounds.

## Deviations

- Nits accepted as-is: fee_data_region stamped in the snapshot but not
  yet surfaced in report labels (phase-5 report integration); an
  --age-out-map override forcing an INT-disallowed target yields "no
  eligible stale data" without naming the rejection reason.
- AWS's post-2024 default lifecycle size filter (<128 KiB excluded from
  transitions) recorded as a phase-3 CONTEXT requirement:
  ObjectSizeGreaterThan must be explicit in generated rules.
