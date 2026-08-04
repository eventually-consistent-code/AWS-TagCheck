---
issues: [41, 42]
depth: deep
---
# Phase 6: storage service layer — Plan

Goal: everything the CLI can do becomes a callable service the web app
can call — with the CLI preserved byte-for-byte by the parity gate — plus
targets and background jobs so scans can start from a browser.

## Tasks

### Issue #41 — service layer, CLI parity kept

1. `tagmanager/storage/services.py` — typed Options dataclasses
   (ScanOptions, AnalyzeOptions, EmitOptions; field defaults mirror CLI
   flag defaults exactly) + service functions returning data objects,
   extracted from the 14 args-coupled cli.py functions per the seam map:
   `run_storage_scan(session_maker, options, provider=None)` — takes
   the MAKER, opens short sessions at the pre-scan touchpoint (emitter
   construction, prior-run lookup) and post-scan touchpoint (persist +
   record_artifact), none held across the walk — plus
   `analyze_cost / analyze_projections / recommend_structure /
   emit_lifecycle / emit_tiering / render_report` (compute + file
   artifacts; NO printing — results carry what the CLI prints). Service
   errors are typed exceptions, not exit codes.
2. Thin the CLI onto services: cli.py keeps parse_args, maps namespace →
   Options, calls services, prints via output.py, converts typed errors
   → exit 4. **Parity gate: full suite green with ZERO test-file edits**
   — any needed test change means the extraction drifted. Two pinned
   seams the thinning must preserve (checker-verified): the
   `cli.main(argv, provider=...)` test injection point, and the
   stdout/LOG channel split (capsys .out substrings are pinned).
3. Service-level tests (no CLI): options-default equivalence asserted
   against parse_args defaults programmatically; each service exercised
   directly incl. error paths that CLI maps to exit 4.

### Issue #42 — scan targets + async jobs

4. Tables + helpers: `StorageTarget` (Scope pattern — backend,
   account_url, buckets JSON [doubles as fs root paths, per CLI
   convention], prefix, age_band_days JSON, options JSON, enabled) and
   `StorageJob` (state queued/running/done/failed/cancelled/interrupted,
   cancel_requested, objects_seen, error, target FK, scan_run FK
   nullable, timestamps) **with a partial unique index on (target_id)
   WHERE state IN ('queued','running')** — concurrent submits race to
   insert; the loser's IntegrityError IS the overlap refusal. Schema
   guard extended + roundtrip tests; `storage_targets_loader` mirroring
   _scopes_loader; WAL/busy_timeout enabled on the engine.
5. Job runner `tagmanager/storage/jobs.py`: dedicated APScheduler
   executor ("storage", 2 workers) added inside build_scheduler (no
   signature ripple — checker-verified against serve.py and
   test_scheduler.py); `submit_scan(scheduler, session_maker,
   target_id)` → job row COMMITTED BEFORE add_job (the worker's fresh
   session must see it), overlap refusal via the partial-index
   IntegrityError. Worker builds its own sessions, runs
   run_storage_scan with a progress/cancel hook: flush every
   batch_size objects or flush_seconds (runner PARAMETERS, defaults
   5,000/5 s — injectable so tests observe flushes without sleeps);
   cancel raises typed ScanCancelled (propagates past scan_buckets'
   error isolation by design), runner sets job "cancelled" and
   overrides the persisted run's status to "cancelled" post-persist.
   Errors captured to the job row, state "failed". ScanExtras grows the
   per-object progress/cancel callable pair.
6. Startup sweep beside reap_stale_runs in serve startup — BOTH queued
   and running orphans → "interrupted" (crash between row-commit and
   thread start, or jobs parked behind the pool, leave queued rows that
   never run). Tests: submit→done with flushes observed (small
   batch_size), cancel mid-bucket at a batch boundary, overlap refusal
   on a busy target via concurrent-submit IntegrityError, boot sweep on
   both orphan states. Runner tested with a synchronous FakeScheduler
   (add_job runs inline) — no sleeps.

## Notes

- Task order 1 → 6; 1–2 land together (the extraction and the thinning
  are one movement), 3 immediately after as the regression net for 4–6.
- Web routes/UI are phase 7 — this phase exposes NOTHING over HTTP; the
  deliverable is the callable surface + job machinery, tested directly.
- html_report/output.py already service-shaped; task 1 only re-homes
  their call sites.
