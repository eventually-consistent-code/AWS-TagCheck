# Phase 5: structure recommendations and reporting — Verification

Verified: 2026-07-31 (deep — adversarial verification per depth dial)

## Goal-backward check

Phase promise: grounded layout recommendations with move plans, and one
report surface carrying everything the milestone computes.

Adversarial verdict: **NOT REFUTED at blocker level** — the engine,
two-pass move plans, both report surfaces, and every checker-locked
amendment behaved as specified under attack. Two genuine ISSUEs surfaced
and were fixed via trace-7301f7e8 (tracker issue 34, commit a15921c):

- Zone-split's "strongly bimodal ages" trigger was unreachable (needed
  ≥3 significant bands; a 50/50 fresh-vs-cold prefix got nothing). Now
  fires on meaningful bytes at both temperature extremes — tested.
- Move-plan CSVs wrote unquoted keys — comma-bearing keys (legal in
  object stores) produced unparseable rows. Now csv.writer throughout —
  comma-key roundtrip tested.
- Nits fixed in the same commit: zero-byte fresh markers count as fresh
  activity; all-conforming reruns say "nothing to move"; persisted-rec
  truncation echoed to console; HTML report gained top-owners and the
  out-of-scope notes.

## What survived attack (verifier-run evidence)

- Threshold boundaries exact (70%/50% strict-greater per CONTEXT);
  compact-first precedence over all transition advice; per-prefix single
  rec with owner attribution; duplicate-prefix guard.
- Every checker-locked item: 5-tuple key at every unpacker (grep-swept),
  schema guard covers owner/artifacts/structure_recs, rec cap with
  truncation marker, S3 FetchOwner live, cost report merges owner slices
  (2 cells not 4, verified live with --rollup-owners).
- Two-pass move plans live: correct year/month rewrites, idempotent
  conforming-skip on rerun, third-scan refusal pointing at
  --recommend-structure, artifacts metadata recorded.
- HTML report under hostile keys/owners (<script>, quotes, onerror=):
  zero unescaped fragments; artifacts index from recorded metadata only;
  fs report omits costs honestly.
- /storage page: latest-run scoping with two runs, owner-merged cells,
  truncated-marker row renders, Jinja autoescape holds, stale-schema
  notice instead of 500.

## Gates

- Tests: 186 passed, 0 failed (19 new this phase incl. 3 verify fixes).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flags on 29/30 normalize
  with this file. Open issues in phase: none. TDD frontmatter: none.
- Ledger: both issues carry commit ranges (165db52..4910203,
  4910203..24a996b) + fix a15921c.

## Result

PASS — after one traced fix round.

## Deviations (accepted, documented)

- latest_complete_run treats partial (buckets-skipped) runs as eligible
  rec sources for move plans — docstring says so.
- Root-prefix ("") recommendations produce no move-plan rows; overlapping
  prefix recs resolve first-match-by-cost; date-conformance heuristic is
  a 4-digit first segment.
- "Fresh-run-after-move-scan refusal" verified live by the adversarial
  agent but not pinned as a named test; per-column roundtrips covered
  end-to-end rather than individually.
- REQ-11 data-type grouping remains declared out of scope (no
  content-type signal) — stated on every output surface.
