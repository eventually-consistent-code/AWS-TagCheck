# Phase 3: request rate awareness — Verification

Verified: 2026-07-31 (standard + an adversarial pass, given the parser-
contract change touched phase-2's fresh code).

## Goal-backward check

Phase promise: fold access-log/CloudTrail op counts into per-prefix
read/write rate estimates persisted with the run, and unlock the fan-out
recommendation v4 deferred pending this telemetry.

Adversarial verifier: **NOT REFUTED** — all four PLAN tasks and every
CONTEXT locked-decision behave as specified. It confirmed by
hand-computation and repro:

- **Parser migration is clean**: `fold_reads` filters writes out of the
  last-read index; a write-only object stays age-by-mtime (NOT
  access-aware) yet its writes feed the rate map — writes drive rates,
  not freshness, exactly as designed.
- **Rate math correct**: read_rps = count / (max−min eventTime);
  single-instant window suppressed; two-source merge SUMS counts and
  UNIONS windows (no double-count, no overwrite).
- **Fan-out precedence + trigger**: checked before every lifecycle kind
  (beats compact-first/date-split/straight-lifecycle/zone-split/
  type-split when hot); inclusive `>=` boundary at the fraction; both
  read-hit and write-hit branches produce correct rationales.
- **Single-pass persistence**: each source file materialized once, fed
  to both index and rate folds; rates persist to `run.request_rates`
  and read back by recommend_structure; `prefix_depth=None` skips
  estimation without crashing.
- **Honesty**: the average-vs-peak caveat is in the rationale; the note
  split is correct (fan-out note retires only when rates recorded, churn
  note always present).
- **Scope boundary with phase 4 clean**: no churn/expiry logic, no
  confidence labels, no rate-based zone-split leaked in.

## Findings fixed (commit 5144d22)

- **ISSUE (low reachability)**: orphan fan-out re-split the loc string
  with `partition("/")`, mislabeling fs container PATHS (which contain
  slashes). Fixed: `estimate_rates` now persists `container`/`prefix`
  explicitly on each rate record and `_orphan_fanout_recs` reads them —
  never re-splits the key. (Matched, non-orphan prefixes were always
  correct; multi-slash S3 prefixes round-tripped fine.)
- **NIT**: `estimate_rates(min_window_seconds=0)` could divide by a
  zero window. Guard hardened to `window <= 0 or window <
  min_window_seconds`.
- Both pinned by new tests (slashed-container orphan, zero-window).

## Gates

- Tests: 242 passed, 0 failed (10 new this phase incl. 2 verify fixes).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flag on 38 normalizes with
  this file. Open issues in phase: none. TDD frontmatter: none.
- Ledger: issue 38 with commit range (0fb20e0..f3ca0c2) + fix 5144d22.

## Result

PASS — after one fix round from the adversarial pass.

## Deviations

- The "fan-out note reappears when logs folded but every window failed
  the guard" case (verifier NIT 3) is left as-is — it is arguably
  correct (no usable rate was recorded), and the message points the user
  at the flags either way. Documented, not changed.
