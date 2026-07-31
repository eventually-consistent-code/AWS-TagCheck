# Phase 6: storage service layer — Verification

Verified: 2026-07-31 (deep — adversarial verification per depth dial)

## Goal-backward check

Phase promise: everything the CLI can do becomes a callable service (CLI
preserved by the parity gate), plus targets and background jobs so scans
can start from a browser.

Adversarial verdict: **NOT REFUTED** — with one real drift fixed via
trace-64412ca6 (tracker issue 46, commit 727c8a2): the storage executor
was registered in serve.py instead of the plan-pinned build_scheduler,
and the verifier PROVED the failure mode — submit_scan against a bare
build_scheduler silently queued a job forever while the active-job index
blocked the target until restart. Now registered inside build_scheduler
(every caller inherits it), pinned by a real-APScheduler end-to-end
test. Same fix round: target options honor prefix_depth (were mostly
dead config), NULL age-band guard, and the flush-seconds arm gained an
injected-clock test.

## What survived attack (verifier-run evidence)

- **Parity beyond the suite**: live CLI drive of scan + emit-lifecycle +
  recommend-structure + html-report — correct print ordering, files on
  disk, artifacts recorded; error paths exit 4 with EMPTY stdout (the
  pinned stdout/LOG channel split holds). Full suite 200 green at
  verification start with zero test edits since extraction.
- **Session discipline**: jobs.py closes every session in finally;
  _progress_hook opens/closes per flush; the walk runs with NO session
  open — grep-audited plus live run.
- **Racing index proven three ways**: ORM double-active insert →
  IntegrityError; done rows don't block; true 2-thread barrier race →
  exactly one ok, one refused. Postgres partial-index DDL compiles.
- **Cancellation**: ScanCancelled outside the walk's isolation tuple,
  propagates; objects_seen max() correct on cancel; live
  fake-clock run flushed on the seconds arm and picked up cancel.
- **Startup**: import graph clean; add_executor before start() verified
  on real APScheduler 3.11.3; WAL pragma on file DBs, harmless on
  :memory:.

## Gates

- Tests: 202 passed, 0 failed (16 new this phase incl. 2 verify fixes).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flags on 41/42 normalize
  with this file. Open issues in phase: none. TDD frontmatter: none.
- Ledger: both issues with commit ranges (d49d142..da61566,
  da61566..6872361) + fix 727c8a2.

## Result

PASS — after one traced fix round.

## Deviations (accepted, documented)

- Cancelled runs are briefly visible as "partial" between the persist
  commit and the status override (single-process; poller-visible window
  only).
- add_job or final-commit failure can leave a stuck active job until the
  boot sweep — consistent with the locked single-replica design.
- CLI sessions in _scan/_analyze_latest close at process exit (CLI
  lifetime is the request); service/job paths close explicitly.
- Cancel raised after the final flush boundary lands the job "done"
  with cancel_requested still set — documented next-flush semantics.
- Per-bucket skips collected before a cancel are replaced by the
  synthetic cancel skip — acceptable; the run is marked cancelled.
