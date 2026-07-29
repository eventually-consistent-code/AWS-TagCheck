Purpose: This script is used to gather tag data from AWS EC2 instances
and compare them against canonical lists to ensure environmental consistency,
and report any deviations to the appropriate parties.
------------------------------------------------------------------------------------
 Author(s): John Reed, Nick Bitzer

## Run

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

The tool validates credentials and the expected account, loads
canonical.json, then scans EC2 instances in every accessible region
(except terminated) for Environment and Product tags. Missing or
non-canonical values are logged as violations. HTML report (index.html)
comes in a later phase. Jenkins / Apache publish path remains external.

## Exit codes

  0  scan finished, zero tag violations
  1  scan finished, one or more Environment/Product tag violations
  2  credential failure (missing/invalid AWS credentials)
  3  account mismatch (caller is not AWS_TAGCHECK_EXPECTED_ACCOUNT)
  4  config missing (AWS_TAGCHECK_EXPECTED_ACCOUNT unset, or bad canonical.json)

## TODO

# - Prevent table headers from printing if no bad data exists in a region (phase 3)
# - HTML report generation (phase 3)
# - Tests and lint green (phase 3)
More to come...
