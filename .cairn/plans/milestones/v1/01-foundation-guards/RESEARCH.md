# Phase 1 RESEARCH — Foundation & guards

**Depth:** standard  
**Scope:** REQ-01–04 (packaging, boto3, credentials, account guard)  
**Out of scope:** full EC2 tag scan (phase 2), HTML report (phase 3)

## Current state

| Artifact | Role today |
|----------|------------|
| `aws_tag_check.py` | Entry: regions loop, PrettyTable → `index.html`, exit `error_count` |
| `aws.py` | Legacy `boto` connect; **empty hard-coded key placeholders**; `check_data()` |
| `requirements.txt` | `boto`, `PTable` |
| `virtShell.sh` | `virtualenv` → `./aws` venv (name collides with `aws.py`) |
| `canonical.json` | Allowed Environment/Product (phase 2 consumer) |
| Import-time side effect | Module open-writes `index.html` header on import — footgun |

## Packaging

**Recommendation:** flat layout + `pyproject.toml` (console script) + `#!/usr/bin/env python3`. No `src/` move this phase.

- `requires-python = ">=3.10"`
- Deps: `boto3` only (drop `boto`; defer `PTable` to phase 3)
- Entrypoint: `aws-tag-check` → `aws_tag_check:main` and keep `python aws_tag_check.py`
- Rewrite `virtShell.sh` → `python3 -m venv .venv` + `pip install -e .` / requirements

## boto3 surface

- Default credential chain only — never pass access keys in code
- `boto3.Session()` → STS + per-region `ec2` clients
- Regions later: prefer `describe_regions` over static catalog; keep `BAD_REGIONS` as safety net until phase 2
- Phase 2 will need: paginated `describe_instances`, tags as `[{Key, Value}]`

## Credential validation (REQ-03)

- Probe: STS `GetCallerIdentity` (no extra IAM beyond calling it)
- Catch `NoCredentialsError`, `PartialCredentialsError`, `ClientError` (invalid/expired token)
- Fail closed; do not treat “credentials object present” as success alone

## Account guard (REQ-04)

- Compare `identity["Account"]` to env **`AWS_TAGCHECK_EXPECTED_ACCOUNT`**
- Missing env → fail closed (config error)
- Mismatch → refuse before any EC2 enumeration
- No multi-account allowlist this phase

## Exit codes (proposed)

| Code | Meaning |
|------|---------|
| 0 | Guards passed (phase 1 success) |
| 1 | Reserved for tag violations (phase 2+) |
| 2 | Credential failure |
| 3 | Account mismatch |
| 4 | Config missing (expected account unset) |

## Walking skeleton

`main()`: check credentials → account guard → optional EC2 smoke (`describe_regions`) → exit 0.  
No full scan, no HTML write on import or run.

## Risks

1. Jenkins may treat any non-zero as “N bad tags” — document guard exit codes
2. Import-time HTML mutation must die in phase 1
3. Fail-open on missing expected account would scan wrong account
4. Old `./aws` venv name confuses tooling — move to `.venv`
