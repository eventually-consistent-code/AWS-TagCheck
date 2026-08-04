---
status: open
issue: 48
created: 2026-08-04
---
# Trace: Phase-5 dry-run-diff: false would-remove DROP warning when a bucket generates only one config kind (empty generated list for the other kind mis-classifies live rules as dropped); plus a KeyError crash when a live lifecycle rule omits the optional ID field.

## evidence — 2026-08-04
Adversarial verify of phase 5 REFUTED (25 dry-run tests green but neither hole covered).

Finding 1 (ISSUE, safety-critical output): services.dry_run_diff builds buckets = set(generated_lifecycle) | set(generated_tiering). A bucket in the union via ONE kind only has generated == [] for the other kind. diff_rule_set([], live_rules) then classifies every live rule of that kind as would_remove, and output.py prints the loud "- REMOVE ... an apply REPLACES the whole config and would DROP it". But an apply only PUTs the kind actually generated — it never issues a Put for the empty kind, so those live rules would NOT be dropped. False DROP warning exactly where the design promises honesty. Reachable via generator asymmetry: lifecycle_gen skips an INTELLIGENT_TIERING-only prefix (STANDARD_IA not in INT_ALLOWED_TARGETS) while tiering_gen generates it; and tiering_gen's per-(container,prefix) seen-dedup can drop a prefix on a non-eligible first stat row while lifecycle_gen aggregates all classes and generates.

Finding 2 (crash on untrusted input): diff.py diff_rule_set uses {rule[id_key]: rule ...}. S3 lifecycle rule ID is OPTIONAL; a live rule without ID raises KeyError 'ID', aborting the read-only diff with a traceback instead of a clean message.

Root cause (both): the engine treats an empty generated side as "replace with nothing" rather than "not generated for this kind", and assumes every rule carries its id key.

## test — 2026-08-04
Fix verified. diff.py: diff_rule_set rewritten to iterate live rules using rule.get(id_key) — an ID-less live rule reads as would_remove, no KeyError (Finding 2). diff_bucket now distinguishes "generated nothing for this kind" (generated == []) from "replace with nothing": sets lifecycle_not_generated/tiering_not_generated + untouched count, leaves the RuleSetDiff None, so no false would_remove (Finding 1). output._print_rule_set renders "not generated — an apply would not touch it (N live rule(s) left as-is)" and never the DROP warning for that kind.

Live smoke with an INTELLIGENT_TIERING-only object (lifecycle_gen skips it, tiering_gen generates) + a customer live lifecycle rule now prints "lifecycle: not generated — an apply would not touch it (1 live rule(s) left as-is)" — the false "would DROP" is gone. 3 regression tests added (ungenerated-kind-untouched, idless-live-rule-removed-not-crash, render-no-false-drop). Full suite 281 passed; pylint 10.00; pycodestyle clean.

## verdict — 2026-08-04
RESOLVED. Both defects from the phase-5 adversarial verify fixed and pinned by tests. Root cause was the diff engine conflating an empty generated side with "replace with nothing" (false would-remove DROP), plus assuming every rule carries its id key (KeyError on optional lifecycle ID). Fix: per-kind not-generated state + defensive id lookup. No read-only violation was ever involved — the read-only headline held throughout; these were classification/robustness bugs in the reporting.
