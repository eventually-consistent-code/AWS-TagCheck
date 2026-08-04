# Phase 5: dry run diff engine — Verification

Verified: 2026-08-04 (standard + an adversarial pass — warranted: the
phase adds the first path that reads live mutable config and shapes a
future MUTATING apply, and the whole promise is a read-only guarantee).

## Goal-backward check

Phase promise (#40): a read-only `--dry-run-diff` that fetches live S3
lifecycle + intelligent-tiering config, diffs it rule-by-rule against
what the run would generate, and reports what an apply WOULD change —
zero writes.

Adversarial verifier: **REFUTED on first pass** — two classification
defects (the read-only headline itself held). Both fixed under
trace-ba876706 (bug #48, commit 9b88f76) and pinned by regression tests:

- **False would-remove / DROP (ISSUE).** `dry_run_diff` bucket set is the
  union of lifecycle- and tiering-generating buckets; a bucket present via
  ONE kind got `[]` generated for the other, so `diff_rule_set` marked
  every live rule of that kind as would-drop. But an apply issues no Put
  for an ungenerated kind — nothing drops. `diff_bucket` now distinguishes
  "not generated" (untouched, no diff, no would-remove) from "replace with
  nothing"; the render says "not generated — an apply would not touch it
  (N live rule(s) left as-is)". Reproduced live via the real generator
  asymmetry (an INTELLIGENT_TIERING-only prefix: lifecycle skips it,
  tiering generates) — the false DROP is gone.
- **KeyError on an ID-less live rule (crash).** S3 lifecycle `ID` is
  optional; `diff_rule_set` used `rule[id_key]` and aborted the read-only
  diff with a traceback. Now `rule.get(id_key)`; an uncorrelatable live
  rule reads as would-remove, cleanly.

Confirmed sound by the verifier, unchanged:
- **Read-only IS airtight for S3.** Every `--dry-run-diff` path calls only
  `stats_for_run` / `build_lifecycle_configs` / `build_tiering_configs`
  (pure reads) + `fetch_lifecycle` / `fetch_tiering`, which call ONLY
  `get_bucket_lifecycle_configuration` and
  `list_bucket_intelligent_tiering_configurations`. No put_/delete_, no
  file writes, no session.commit in the diff service. The recording-stub
  test pins "no mutating call" against the provider.
- **Normalization sound**: prefix-shape collapse, object-size axis,
  sorted transitions/tierings with a None-safe Date sort key, generator-
  key projection — no false-changed or false-unchanged found. The
  object-size-absent and trailing-slash cases correctly read as
  would-change (genuine differences).
- **Error mapping**: AccessDenied→unknown, NoSuchLifecycleConfiguration→
  absent, else reraise — on both paths; 404-vs-403 never conflated.
- **S3-only** enforced in both the CLI (`args.backend`) and the service
  (`run.backend`); `latest_complete_run(backend="s3")` hardcoded.

## Gates

- Tests: 281 passed, 0 failed (29 this phase: 15 diff core incl. 3 verify
  regressions, 7 read-only fetch, 7 CLI/render).
- Lint: pylint 10.00 (`aws.py aws_tag_manager.py tagmanager`), pycodestyle
  clean. (Test files are outside the gate's targets, per static_analysis.sh.)
- `plan_drift`: transient closed-unverified flag on 40 normalizes with
  this file. Open issues in phase: none (bug #48 closed via the trace).
  TDD frontmatter: none.
- Ledger: issue 40 (8a2a06e..d62ba2f); trace fix 9b88f76.

## Result

PASS — after one fix round from the adversarial pass.

## Deviations

- `_effective_prefix` (an underscore-prefixed helper in diff.py) is
  imported by output.py for the rule summary. Within-package reuse; the
  gate rates it 10.00. Left as-is.
- The union-of-generating-buckets set is retained (correct once the
  per-kind not-generated handling was added) rather than switching to a
  per-kind bucket set — simpler, and the not-generated path is now honest.
