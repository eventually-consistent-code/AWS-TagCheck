# Phase 2: EC2 compliance scan — Verification

**Status:** PASS  
**Date:** 2026-07-29  
**Depth:** standard  
**Commit range:** `6ca2fba..fd83ad5` (implementation) + ledger `6a358ba`

## Goal (from PLAN / CONTEXT)

After phase 1 guards, scan EC2 instances across accessible regions, compare
Environment and Product tags to `canonical.json`, collect structured
noncompliance rows, and exit `0` (clean) or `1` (any violation). No HTML.

## Checks

### Canonical load + pure evaluation (T1)

| Check | Result |
|-------|--------|
| `load_canonical` loads Environment/Product lists | PASS |
| Missing file → exit 4 | PASS |
| Clean tags → no findings | PASS |
| Missing keys → sentinels + `issue=missing` | PASS |
| Invalid values (incl. empty string) → `issue=invalid` | PASS |
| Both tags bad → two findings | PASS |

### Pagination + helpers (T2)

| Check | Result |
|-------|--------|
| `iter_instances` uses `get_paginator("describe_instances")` | PASS |
| Default filters exclude terminated only | PASS |
| `tags_to_dict` handles missing/None Tags | PASS |

### Per-region scan + skip (T3)

| Check | Result |
|-------|--------|
| Violation rows include full phase-3 shape | PASS |
| `ClientError` → skip (empty viol, skip record) | PASS |
| Name fallback / Name tag | PASS (via unit instance with Name) |

### Multi-region orchestration + exit (T4–T5)

| Check | Result |
|-------|--------|
| `main` order: creds → account → load → scan | PASS |
| No PrettyTable / `open(HTML_FILE)` | PASS |
| README documents exit 0/1 and phase-3 HTML | PASS |
| Live multi-region scan completes | PASS |
| Live exit class 0 or 1 (not guard-only) | PASS (exit **1**, 2 violations) |

### Live evidence (2026-07-29)

```
regions=17 skips=0 instances=1 violations=2
violation us-east-1 i-060e838538a751a2d rightsize-test1 Environment=missing environment (missing)
violation us-east-1 i-060e838538a751a2d rightsize-test1 Product=missing product (missing)
live_exit=1
```

### Tracker / plan hygiene

| Check | Result |
|-------|--------|
| Issue #8 closed | PASS |
| Open issues on phase tracker | none |
| LEDGER.md line for #8 | PASS |
| PLAN.md `tdd:` | N/A |
| `plan_drift` closed-unverified on #8 | Expected pre-VERIFICATION; resolved by this file |

## Deviations

None relative to CONTEXT. HTML remains explicitly out of scope (phase 3).

## Verdict

**PASS** — phase promises delivered. Next: `/cairn:ship` or `/cairn:plan 3`.
