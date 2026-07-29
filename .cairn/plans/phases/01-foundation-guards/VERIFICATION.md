# Phase 1: Foundation & guards — Verification

**Status:** PASS  
**Date:** 2026-07-29  
**Depth:** standard  
**Commit range:** `45721ee..bc5480a` (implementation) + ledger/roadmap follow-ups

## Goal (from PLAN / CONTEXT)

Walking skeleton: Python 3 + boto3, validate AWS credentials, enforce expected
account, smoke-test EC2 region listing — then exit cleanly. No full tag scan,
no HTML report.

## Checks

### Packaging & entry (REQ-01 / #2)

| Check | Result |
|-------|--------|
| `pyproject.toml` with `requires-python >=3.10` | PASS |
| Console script `aws-tag-check = aws_tag_check:main` | PASS (present on venv PATH) |
| Shebang `#!/usr/bin/env python3` | PASS |
| `requirements.txt` is boto3-only | PASS |
| `virtShell.sh` targets `.venv` + editable install | PASS |
| Editable install + imports | PASS (Python 3.14.6, boto3 1.43.58) |
| Legacy `boto` package not required | PASS (`find_spec('boto')` is None) |

### boto3 session surface (REQ-02 / #5)

| Check | Result |
|-------|--------|
| `build_session`, `ec2_client`, `list_ec2_regions` present | PASS |
| No legacy `boto` / `boto.ec2` imports | PASS |
| No `aws_access_key_id` / `aws_secret_access_key` in source | PASS |
| `check_data` retained for phase 2 | PASS |
| `canonical.json` still present | PASS |

### Credential validation (REQ-03 / #1)

| Check | Result |
|-------|--------|
| STS `GetCallerIdentity` via `validate_credentials` | PASS (Stubber + live) |
| No usable credentials → exit 2 | PASS |
| Live credentials → continues to account guard | PASS |

### Account guard (REQ-04 / #4)

| Check | Result |
|-------|--------|
| Missing `AWS_TAGCHECK_EXPECTED_ACCOUNT` → exit 4 | PASS |
| Mismatch → exit 3 | PASS (unit + live with `000000000000`) |
| Match → continues | PASS |
| Documented in README (env + exit codes) | PASS |

### Walking skeleton / import purity (T5–T6)

| Check | Result |
|-------|--------|
| `main()` order: session → creds → account → `list_ec2_regions` → exit 0 | PASS (AST) |
| No import-time HTML write | PASS |
| No PrettyTable / full instance scan on path | PASS |
| Live smoke: matching account → exit 0, listed 17 regions | PASS |
| Credential/account README TODOs struck | PASS (empty-region TODO remains for phase 3) |

### Tracker / plan hygiene

| Check | Result |
|-------|--------|
| Phase open/in_progress issues | PASS (empty for phase tracker id) |
| Issues #2, #5, #1, #4 closed | PASS |
| LEDGER.md lines for all four issues | PASS |
| PLAN.md `tdd:` frontmatter | N/A (none) |
| `plan_drift` closed-unverified flags | Expected pre-VERIFICATION; resolved by this file |

## Deviations

- Host default `python3` is 3.9.6; package correctly requires ≥3.10. `virtShell.sh` prefers Homebrew 3.10+ (e.g. `/opt/homebrew/bin/python3`). Documented in run path.
- Empty credential chain sometimes surfaces as a config-file error message from the environment’s AWS config settings; still maps to exit **2** (fail closed). Not a phase failure.
- Live happy path exercised against account `511531327508` (operator identity). No secrets logged.

## Evidence summary

```
no-creds exit=2
missing env → 4; mismatch → 3; match → ok
live match → exit 0, found 17 region(s), guards passed
live wrong account → exit 3
source greps: no boto / keys / PrettyTable / HTML open
```

## Verdict

**PASS** — phase promises delivered. Ready for `/cairn:ship` when you want this on the remote, or continue with `/cairn:plan 2`.
