Purpose: This script is used to gather tag data from AWS EC2 instances
and compare them against canonical lists to ensure environmental consistency,
and report any deviations to the appropriate parties.
------------------------------------------------------------------------------------
 Author(s): John Reed, Nick Bitzer

## Run (phase 1 — guards + region smoke)

1. Bootstrap the venv:
     source virtShell.sh
   or:
     python3 -m venv .venv && source .venv/bin/activate
     pip install -e . && pip install -r requirements.txt

2. Put AWS credentials in the default chain (env keys, shared credentials,
   SSO, or instance role). Do not put secrets in the repo.

3. Set the expected account id (required):
     export AWS_TAGCHECK_EXPECTED_ACCOUNT=123456789012

4. Run either:
     ./aws_tag_check.py
     aws-tag-check

Phase 1 exits after credential check, account guard, and a read-only
describe_regions smoke test. Full EC2 tag scan + HTML report (index.html)
come in later phases. Jenkins / Apache publish path remains external.

## Exit codes

  0  guards passed (phase 1 success)
  1  reserved for tag violations (phase 2+)
  2  credential failure (missing/invalid AWS credentials)
  3  account mismatch (caller is not AWS_TAGCHECK_EXPECTED_ACCOUNT)
  4  config missing (AWS_TAGCHECK_EXPECTED_ACCOUNT unset)

## TODO

# - Prevent table headers from printing if no bad data exists in a region (phase 3)
# - Full EC2 tag scan vs canonical.json (phase 2)
# - HTML report generation (phase 3)
More to come...
