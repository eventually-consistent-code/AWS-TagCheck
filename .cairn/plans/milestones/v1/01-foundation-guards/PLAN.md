---
issues: [2, 5, 1, 4]
depth: standard
---
# Phase 1: Foundation & guards — Plan

## Goal

Walking skeleton: Python 3 + boto3, validate AWS credentials, enforce expected
account, smoke-test EC2 region listing — then exit cleanly. No full tag scan,
no HTML report.

## Produces

- Installable/runnable Python 3 entry (`aws-tag-check` / `aws_tag_check.py`)
- `aws.py` session helpers on boto3 (no secrets in source)
- Guard exit codes documented in README
- Smoke path ready for phase 2 to hang the scan on

## Consumes

- Existing flat modules and `canonical.json` (unchanged data file)
- Operator-provided credentials via default AWS chain
- Env `AWS_TAGCHECK_EXPECTED_ACCOUNT`

## Tasks

### T1 — Packaging foundation (REQ-01 → #2)

1. Add `pyproject.toml`: name `aws-tag-check` (or `aws_tag_check`),
   `requires-python >=3.10`, dependency `boto3`, console script
   `aws-tag-check = "aws_tag_check:main"`.
2. Set shebang on `aws_tag_check.py` to `#!/usr/bin/env python3`; keep
   `if __name__ == '__main__': main()`.
3. Rewrite `requirements.txt` → `boto3` (drop `boto` and `PTable` for now).
4. Rewrite `virtShell.sh` → `python3 -m venv .venv`, activate, `pip install -r
   requirements.txt` and/or `pip install -e .`.
5. Update `README.txt` with venv bootstrap, entrypoint, and required env var
   (details filled after T4 exit codes land).

**Done when:** clean venv install; `python aws_tag_check.py` starts without
importing `boto`.

### T2 — boto3 session module (REQ-02 → #5)

1. Rewrite `aws.py` (Purpose/Author, `LOG`): `build_session()`,
   `ec2_client(session, region)`, `list_ec2_regions(session)` via
   `describe_regions`.
2. Remove all `boto` / `boto.ec2` imports and hard-coded key kwargs.
3. Keep `check_data` for phase 2 or leave as-is without using it in phase 1
   main path.

**Done when:** `rg` finds no `boto` (except boto3) and no
`aws_access_key_id` / `aws_secret_access_key` in source; module imports clean.

### T3 — Credential validation (REQ-03 → #1)

1. Implement `validate_credentials(session)` → STS `get_caller_identity`.
2. Map `NoCredentialsError` / `PartialCredentialsError` / auth `ClientError`
   to fail path with chatty `LOG` messages (`checking credentials...` /
   `credentials ok...` / clear error).
3. Call first thing in `main()` after setup; `sys.exit(2)` on failure.
4. Never log secrets; logging account + ARN on success is fine.

**Done when:** no creds → exit 2; valid creds → continues to account guard.

### T4 — Account guard (REQ-04 → #4)

1. Read `AWS_TAGCHECK_EXPECTED_ACCOUNT` from the environment.
2. Unset → log and `sys.exit(4)`.
3. Mismatch vs STS `Account` → log expected vs actual, `sys.exit(3)`.
4. Match → `account guard ok...` and continue.
5. Document env var + exit codes in `README.txt`.

**Done when:** wrong/missing expected account refuses before any EC2 call
beyond what STS already did; match continues.

### T5 — Walking skeleton orchestration

1. `main()` order: status → credentials (T3) → account (T4) → EC2
   `list_ec2_regions` smoke (count/log) → `guards passed...` → `sys.exit(0)`.
2. Remove import-time `index.html` write and do not run the full instance loop
   or PrettyTable path this phase (leave phase 2/3 hooks as comments if useful).
3. Preserve `BAD_REGIONS` constant only if still referenced; otherwise note for
   phase 2.

**Done when:** end-to-end local run with valid role/profile + matching expected
account exits 0 after smoke; wrong account never enumerates regions for scan
purposes (smoke is post-guard only).

### T6 — Hygiene acceptance

1. Grep: no legacy `boto`, no hard-coded keys, no import-time HTML write.
2. Manual checklist: install, missing creds (2), missing env (4), wrong
   account (3), happy path (0).
3. Strike credential/account README TODOs; leave empty-region HTML TODO for
   phase 3.

**Done when:** checklist passes; phase ready for `/cairn:verify 1` after work.

## Order / dependencies

```
T1 → T2 → T3 → T4 → T5 → T6
```

All sequential (no parallel waves): each task builds on the previous.

## Verification preview

- Exit code matrix as in CONTEXT
- Source hygiene greps
- Smoke region list only after guards
