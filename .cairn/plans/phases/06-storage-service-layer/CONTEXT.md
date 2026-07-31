# Phase 6: storage service layer — Context

## Locked decisions

- **Services return data, never print.** All compute extracted from
  cli.py's 14 args-coupled functions into a service module taking typed
  Options dataclasses (defaults mirror CLI flag defaults exactly);
  printing and CSV writing stay in cli.py/output.py. The CLI becomes
  parse_args → Options → service → print.
- **The parity contract is a hard gate**: the ~100-test storage CLI
  suite passes UNCHANGED — zero test-file edits in the #41 commit(s).
  If a test needs editing, the extraction changed behavior; fix the
  extraction.
- **Job execution reuses the running APScheduler BackgroundScheduler**
  with a DEDICATED "storage" executor (2 workers) — trigger-less
  add_job for run-now. Periodic tag scans keep the default pool;
  storage walks must never starve them. No Celery, no ProcessPool
  (IO-heavy, GIL-releasing), no FastAPI BackgroundTasks (no status
  handle). Single-replica in-process execution — documented assumption.
- **StorageJob is a separate table from StorageScanRun**: job = intent
  and lifecycle (queued/running/done/failed/cancelled/interrupted,
  cancel_requested, error, target FK, progress counter); run = scan
  data, FK-linked when the scan starts. StorageTarget follows the Scope
  enabled-config-row pattern (backend, account_url, buckets/roots,
  prefix, age bands, option flags, enabled).
- **Progress + cancel share one boundary**: flush objects_seen every
  5,000 objects or 5 s (whichever first) in a short-lived session, and
  read cancel_requested in the same touch. Sessions are built INSIDE
  the job thread (sessionmaker is thread-safe; Session instances are
  not). Cancel raises a typed ScanCancelled from the hook — it
  propagates past scan_buckets' (ClientError, BotoCoreError, OSError)
  isolation on purpose — and the runner overrides the persisted run's
  status to "cancelled" post-persist (persist_rollups only knows
  complete/partial). Flush batch size and clock are runner parameters
  (defaults 5,000/5 s) so tests observe flushes without sleeps.
- **Session-boundary scoping (checker amend)**: services take
  session_maker, not a session — short sessions at the pre-scan
  touchpoint (emitter construction, prior-run lookups) and post-scan
  touchpoint (persist + artifact recording), NONE held across the walk.
  The "no session outlives a flush" rule covers the walk and the flush
  loop; pre/post touchpoints are their own short sessions.
- **Double-submit race closed by schema, not lock**: partial unique
  index on storage_jobs(target_id) WHERE state IN ('queued','running');
  concurrent submits race to insert and the loser's IntegrityError IS
  the overlap refusal. No held locks (card constraint-db8a9d4e).
- **Boot sweep covers queued AND running** → "interrupted" — a crash
  between job-row commit and thread start (or jobs parked behind the
  2-worker pool) leaves queued orphans that would otherwise never run.
- **SQLite concurrency**: enable WAL / busy_timeout on the engine when
  the job runner lands — flush writes + periodic tag scans on
  default-journal SQLite invite SQLITE_BUSY.
- **Startup sweep**: any StorageJob still running at boot →
  "interrupted" (generalizing reap_stale_runs); runs alongside the
  existing reaper in serve startup.
- **Card constraint-db8a9d4e applies**: never hold an overlap-guard
  lock across a scan await/iteration — the job runner's per-target
  overlap check is a count query at submit time, not a held lock.
- Phase-7 consumers decided here so the service API fits them: htmx
  2s-poll progress fragments stopped by HX-Trigger done; BytesIO zip
  StreamingResponse artifact downloads.
