---
issues: [38]
---
# Phase 3: request rate awareness — Plan

Goal: fold access-log/CloudTrail op counts into per-prefix read/write rate
estimates persisted with the run, and unlock the fan-out recommendation
v4 deferred pending this telemetry.

Research done (RESEARCH.md): AWS per-prefix ceilings carried from
milestone-4 phase-5; the average-over-sample vs peak honesty problem and
the minimum-window guard are the load-bearing design points.

## Tasks

### Issue #38 — per-prefix request-rate signals + fan-out rec

1. Op classification in the parsers: `parse_line` / `parse_record` return
   `(bucket, key, time, optype)` with optype `read`/`write` (write
   allowlists per RESEARCH); `fold_reads` filters `optype == "read"` so
   the phase-2 last-read index is byte-identical. Parser unit tests
   extended for write ops + the read/write split. **Risk task — touches
   phase-2's fresh parser contract; its exclude/ARN tests stay green.**
2. `tagmanager/storage/request_rate.py` — `RatePrefixStat` (read_count,
   write_count, window_start, window_end) + `fold_rates(events,
   prefix_depth) -> {(container, prefix): RatePrefixStat}` and
   `estimate_rates(rate_stats, min_window_seconds) -> {prefix: {read_rps,
   write_rps, window_s, sample_ops}}` applying the minimum-window guard.
   Pure, unit tested incl. the sub-window-guard suppression.
3. Single-pass wiring + persistence: `build_access_report(...,
   prefix_depth=)` builds last-read index AND rates in one sweep per
   source; `AccessIndexReport` gains `rates`. `StorageScanRun` gains a
   `request_rates` JSON column (schema guard extended, roundtrip test);
   `run_storage_scan` persists the estimated rates; CLI readiness line
   reports rate coverage. Tests: rates persisted + read back; combined
   with the object walk.
4. Fan-out recommendation: `prefix-fanout` rec kind, FIRST in precedence,
   fires when `request_rates` shows a prefix's read or write average past
   `FANOUT_CEILING_FRACTION` of the ceiling; rationale names rate +
   ceiling + the average-vs-peak caveat. `build_recommendations` takes
   `request_rates`; `out_of_scope_notes(types_recorded, rates_recorded)`
   splits the bundled note (fan-out half retires when rates recorded,
   churn half stays). PROPOSAL/HTML/`/storage` surface via the existing
   rec plumbing (kind + rationale). Tests: fires past the fraction,
   silent below it and below the window guard, beats every other kind,
   note splits correctly.

## Notes

- Task order 1 → 4; task 1 is the risky parser-contract change (land its
  green tests before building on it). No new move-plan kind — fan-out is
  advisory (PROPOSAL guidance only), not a key-level manifest.
- Persist per-prefix rates keyed on the run's prefix_depth so the
  fan-out rec and the object-walk recs share one prefix view.
