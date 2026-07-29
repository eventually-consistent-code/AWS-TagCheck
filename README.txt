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

4. Optional — link to your tag policy docs in the HTML report:
     export AWS_TAGCHECK_GUIDANCE_URL=https://example.com/your-tag-guide

5. Run either:
     ./aws_tag_check.py
     aws-tag-check

The tool validates credentials and the expected account, loads
canonical.json, scans EC2 instances in every accessible region (except
terminated) for Environment and Product tags, logs violations, and writes
index.html. Only regions with findings get a table section. Jenkins /
Apache publish of index.html remains external.

## Exit codes

  0  scan finished, zero tag violations (HTML still written)
  1  scan finished, one or more Environment/Product tag violations (HTML written)
  2  credential failure (missing/invalid AWS credentials) — no HTML
  3  account mismatch (caller is not AWS_TAGCHECK_EXPECTED_ACCOUNT) — no HTML
  4  config missing (expected account unset, or bad canonical.json) — no HTML

## Dev: tests and lint

  pip install -e ".[dev]"
  # or: pip install -r requirements-dev.txt

  pytest
  ./static_analysis.sh

More to come...
