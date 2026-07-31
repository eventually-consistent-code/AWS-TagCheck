# Phase 6: storage service layer — Research

Researched: 2026-07-31 (repo seam map + background-job pattern sweep).

## Refactor seams (repo map)

- **14 args-coupled functions** in storage/cli.py are the decoupling
  targets, each interleaving a portable compute step (stats_for_run /
  project_options / build_* calls) with print_*/write_* output calls.
  Attribute inventory per function captured in the fan-out (e.g. _scan
  reads bucket/csv_out/prefix/prefix_depth/rollup_owners).
- **Already service-shaped**: scan_buckets (provider, buckets, prefix,
  builder, extras), _parse_age_out_map, _load_backend_pricing,
  _open_session, _finish_emitters — and the whole compute layer
  (cost/projections/structure/lifecycle_gen/tiering_gen/html_report)
  never touches argparse.
- **Parity net**: ~100 tests across 12 storage test files with ~53
  direct cli.main references pinning exit codes and printed/CSV output.
  test_storage_rollup.py is already service-level (0 cli refs).
- **Wiring points**: create_app registers routers at main.py:95
  (include_router(ui_router(...))); JSON API is inline closures; Scope
  rows (enabled-config pattern + _scopes_loader) are the StorageTarget
  precedent; ScanRun.status="running" + scheduler's count-based overlap
  guard is the job-status precedent; StorageScanRun already carries
  status/counters/artifacts/structure_recs.
- **Scheduler**: APScheduler BackgroundScheduler, interval job added in
  build_scheduler, started in serve.main before uvicorn — one process.

## Background-job patterns (sourced)

- **Execution**: reuse the running BackgroundScheduler —
  add_job(fn, args=[job_id]) with NO trigger runs immediately in the
  scheduler's thread pool. Give user scans a DEDICATED executor
  (default pool is 10 threads shared with periodic tag scans; an
  hours-long storage walk must not starve them). FastAPI
  BackgroundTasks rejected (no status handle, request-lifecycle
  coupling); ProcessPool rejected (IO-heavy, GIL-releasing work —
  threads are right).
- **Progress**: local counter, flush every N objects / T seconds
  (5,000 / 5 s), each flush a short-lived transaction. Engine and
  sessionmaker are thread-safe factories; a Session instance is NOT
  thread-safe "in any way, shape, or form" (maintainer quote) — build
  sessions inside the job thread, open-short close-fast over multi-hour
  runs.
- **Cancellation**: cooperative — a cancel_requested column read at the
  same flush boundary (the cancel endpoint just flips the column);
  threads cannot be killed, batch-boundary exit is the pattern.
- **Restart safety**: app restart silently kills job threads — startup
  sweep marks RUNNING jobs INTERRUPTED (generalizes the existing
  reap_stale_runs). Single-replica assumption; document it.
- **htmx progress** (phase-7 consumer, decided now): inner div
  hx-trigger="every 2s" polling a progress fragment; server sends
  HX-Trigger: done to stop the poller and swap the final state.
- **Zip downloads** (phase-7 consumer): BytesIO + zipfile into
  StreamingResponse for artifact-dir scale; stream-zip only if
  artifacts ever hit GB scale.
