AWS TagManager
------------------------------------------------------------------------------------
Purpose: Gather tag data from AWS EC2 instances, compare it against canonical
lists to ensure environmental consistency, report deviations (log + HTML),
and optionally merge a desired-tags CSV into a reviewed "gold list" and
publish results to S3.
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
     export AWS_TAGMANAGER_EXPECTED_ACCOUNT=123456789012

4. Optional — link to your tag policy docs in the HTML report:
     export AWS_TAGMANAGER_GUIDANCE_URL=https://example.com/your-tag-guide

5. Run either:
     ./aws_tag_manager.py
     aws-tag-manager

The tool validates credentials and the expected account, loads
canonical.json, scans EC2 instances in every accessible region (except
terminated) for Environment and Product tags, logs violations, and writes
index.html. Only regions with findings get a table section. Jenkins /
Apache publish of index.html remains external.

## CSV gold-list merge and S3

  --csv FILE|s3://bucket/key   merge a CSV of desired tags (columns:
                               resource_id, tag_key, tag_value) with the
                               scanned AWS tags; CSV wins on conflict and
                               each conflict is recorded for review
  --write-gold                 write the merged result to gold-list.json
                               plus conflicts.json
  --gold-output PATH           change the gold-list output path
  --s3-bucket BUCKET           upload index.html to
                               s3://BUCKET/reports/YYYY-MM-DD.html after the
                               scan; with --write-gold and --csv, also
                               uploads gold-list.json and conflicts.json

The CSV is read and validated before the scan starts, so a bad path or S3
key fails in seconds instead of after a full region sweep. The scan itself
runs once — the same instance snapshot feeds both the violation report and
the gold-list merge. A failed S3 upload logs an error; if the scan itself
was clean, the run exits 4 so CI notices the missing report.

## Exit codes

  0  scan finished, zero tag violations (HTML still written)
  1  scan finished, one or more Environment/Product tag violations (HTML written)
  2  credential failure (missing/invalid AWS credentials) — no HTML
  3  account mismatch (caller is not AWS_TAGMANAGER_EXPECTED_ACCOUNT) — no HTML
  4  config missing (expected account unset, bad canonical.json, unreadable
     --csv), or clean scan whose S3 upload failed (HTML written locally)

## Dev: tests and lint

  pip install -e ".[dev]"
  # or: pip install -r requirements-dev.txt

  pytest
  ./static_analysis.sh

## Platform (web UI)

  docker compose up

The web UI runs at http://localhost:8080 and provides a read-only dashboard to
browse tags across cloud providers. Database defaults to SQLite; to use
PostgreSQL, pass TAGMANAGER_DB_URL as an environment variable.

Configuration:
  TAGMANAGER_DB_URL              database connection URL (default: SQLite
                                 in-memory); use postgresql+psycopg://
                                 for PostgreSQL
  TAGMANAGER_AUTH_MODE           "none" (default) or "oidc"
  TAGMANAGER_OIDC_DISCOVERY_URL  OpenID Connect discovery URL (required if
                                 AUTH_MODE=oidc)
  TAGMANAGER_OIDC_CLIENT_ID      OIDC client ID (required if AUTH_MODE=oidc)
  TAGMANAGER_OIDC_CLIENT_SECRET  OIDC client secret (required if AUTH_MODE=oidc)
  TAGMANAGER_SCAN_INTERVAL_MINUTES  how often to scan clouds (default: 60)

## TODO

  # - decide what an empty tag_value in the CSV means (today it overwrites
  #   the AWS value with "" and records a conflict — maybe it should clear
  #   or skip instead)
  # - conflicts.json path is hardcoded while --gold-output is configurable
  # - one live end-to-end run with --s3-bucket against a real account
  #   (S3 paths are currently verified against stubbed clients only)

More to come...
