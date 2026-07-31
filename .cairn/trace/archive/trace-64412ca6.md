---
status: resolved
issue: 46
created: 2026-07-31
resolved: 2026-07-31
---
# Trace: Phase 6 verify: storage executor registered in serve.py not build_scheduler (plan drift) — submit_scan against a bare build_scheduler silently queues forever and index-blocks the target; plus dead target options and untested flush-seconds arm

## verdict — 2026-07-31
Fixed in 727c8a2: register_storage_executor moved into build_scheduler per the plan's pinned location (serve.py drops its call) — bare-build_scheduler execution now pinned by a real-APScheduler test; target options honor prefix_depth; NULL age_band_days guarded; flush-seconds arm tested with injected clock. 202 tests + lint green. Accepted as documented: cancelled-status partial→cancelled window, stuck-active on add_job/commit failure (single-replica boot sweep covers), CLI end-of-process session cleanup, cancel-after-last-flush lands done.

## resolution — 2026-07-31
Executor registration moved into build_scheduler (silent-stuck trap closed, pinned by a real-APScheduler test); prefix_depth honored, NULL age-bands guarded, flush-seconds arm covered. 727c8a2; 202 tests + lint green.
