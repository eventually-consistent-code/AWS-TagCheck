# Phase 1: Foundation & guards — Context

## Locked decisions

- **Layout:** Keep flat repo modules (`aws.py`, `aws_tag_check.py`). Add `pyproject.toml` with console script `aws-tag-check` → `aws_tag_check:main`. Shebang `#!/usr/bin/env python3`. No `src/` package move this phase.
- **Python:** `requires-python = ">=3.10"`.
- **Credentials:** Default boto3/botocore credential chain only. Never hard-code access keys/secrets (remove empty-string key kwargs from legacy `aws.py`). Support profiles/env/instance role by not special-casing them.
- **Credential check:** STS `GetCallerIdentity` is the pass/fail probe. Fail closed on `NoCredentialsError`, `PartialCredentialsError`, and auth-related `ClientError`.
- **Account guard:** Required env var `AWS_TAGCHECK_EXPECTED_ACCOUNT` (12-digit account id). Compare to STS `Account`. Fail closed if unset or mismatch. No `--allow-any-account` in this phase.
- **Exit codes:** `0` guards ok; `1` reserved for later tag violations; `2` credential failure; `3` account mismatch; `4` missing expected-account config.
- **Phase 1 end state:** After guards pass, run a read-only EC2 smoke (`describe_regions` via boto3) to prove REQ-02 wiring, log a short summary, exit `0`. Do **not** run the full instance/tag scan or write HTML.
- **Import purity:** Remove import-time `index.html` header write from `aws_tag_check.py`. No file I/O at import.
- **Deps:** `requirements.txt` / project deps → `boto3` only for the active path. Drop `boto`. Defer `PTable`/PrettyTable to phase 3.
- **Venv bootstrap:** Rewrite `virtShell.sh` to `python3 -m venv .venv` (not `./aws`) and install deps / editable package.
- **Style:** Match John Reed voice — Purpose/Author module docstring, `LOG`, `main()`, `UPPER_SNAKE` constants, chatty lowercase status with trailing `...`.
- **`check_data` / `canonical.json`:** Leave available for phase 2; not required for guards. Do not delete `canonical.json`.

## Precedence

On conflict, this CONTEXT + PLAN win over tracker issue text — update issues if they drift.

## Out of scope (this phase)

- Full multi-region instance enumeration and tag comparison (phase 2)
- HTML report generation and empty-region polish (phase 3)
- Multi-resource types, notifications, multi-account allowlists
