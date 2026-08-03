---
issues: [40]
---
# Phase 5: dry run diff engine — Plan

Goal (#40): a read-only `--dry-run-diff` that fetches live S3 lifecycle +
intelligent-tiering config, diffs it rule-by-rule against what this run
would generate, and reports what an apply WOULD change — shaped for a
future guarded apply. Zero writes, guaranteed.

Milestone-5 closer. Standard depth; research (RESEARCH.md) covered the
boto3 GET surface, error modes, and normalization.

## Tasks

### Issue #40 — dry-run diff engine (apply-ladder rung one)

1. **Diff core (`storage/diff.py`) — pure, AWS-free.** Normalize +
   set-diff two rule collections by ID/Id. `_normalize_lifecycle_rule` /
   `_normalize_tiering_config` collapse the prefix representation, sort
   Transitions/Tierings, and project onto the generator-emitted key
   subset (per RESEARCH). `diff_rule_set(generated, live)` returns a
   `RuleSetDiff` (would_add / would_remove / would_change / unchanged,
   each a list of rule IDs + bodies). `ConfigDiff` bundles per-bucket
   lifecycle + tiering diffs plus `unknown` (403) / `no_live_config`
   (404) flags. Fully unit-tested with dict fixtures — including the
   would-remove drop case, the prefix-shape normalization (rule-level
   `Prefix` vs `Filter.And.Prefix` compare equal), unordered
   Transitions, and a `Date`-based live rule flagged changed not crashed.

2. **Live read (S3 provider), read-only.** Add `fetch_lifecycle(bucket)`
   and `fetch_tiering(bucket)` to `S3Provider`: lifecycle catches
   `NoSuchLifecycleConfiguration` → empty and `AccessDenied` → an
   unknown sentinel; tiering pages the list, empty list → no config.
   Only GET/list client calls. Tests use a stub boto3 client: assert the
   returned shapes, the 404→empty and 403→unknown mapping, IT
   pagination, AND that no mutating method (`put_*`/`delete_*`) is ever
   called on the stub (read-only guarantee pinned).

3. **Orchestrate + CLI render.** A service (`services.dry_run_diff`)
   regenerates lifecycle + tiering configs in-memory from the run
   (`build_lifecycle_configs` / `build_tiering_configs`), fetches live
   per bucket, builds the `ConfigDiff`. `--dry-run-diff` on the CLI
   renders it rule-by-rule: would-add / would-change / and the LOUD
   would-remove ("apply REPLACES the whole config — these live rules
   would be dropped"), plus the honest unknown/no-config lines. Non-S3
   backend → clean "dry-run-diff is S3 only" error. Tests: end-to-end
   render on a run with a stubbed provider (add + remove + change all
   present), the S3-only guard, and the drop-warning text.

## Notes

- Diff core is deliberately AWS-free so the risky logic (what would be
  DROPPED) is exhaustively unit-testable without moto/live creds.
- No new persistence and no web surface this phase — CLI-only, matching
  the issue. The `ConfigDiff` dataclass is the seam a later guarded-apply
  rung consumes; keep it clean and serializable-friendly.
- Read-only is the headline invariant — the task-2 "no mutating call"
  test is the guard that keeps rung one honest.
