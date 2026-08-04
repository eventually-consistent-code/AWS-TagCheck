# Technical Reference

Everything the classic CLI and the platform expose: flags, env vars, exit codes, and dev workflow. For day-2 operations (deploying, credentials, incidents), see the [Runbook](runbook.md). Back to the [README](../README.md).

## Classic AWS CLI (`aws-tag-manager`)

Purpose: gather tag data from AWS EC2 instances, compare it against canonical lists to ensure environmental consistency, report deviations (log + HTML), and optionally merge a desired-tags CSV into a reviewed "gold list" and publish results to S3.

### Run

1. Bootstrap the venv:

   ```bash
   source virtShell.sh
   ```

   or:

   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e . && pip install -r requirements.txt
   ```

2. Put AWS credentials in the default chain (env keys, shared credentials, SSO, or instance role). Do not put secrets in the repo.

3. Set the expected account id (required):

   ```bash
   export AWS_TAGMANAGER_EXPECTED_ACCOUNT=123456789012
   ```

4. Optional — link to your tag policy docs in the HTML report:

   ```bash
   export AWS_TAGMANAGER_GUIDANCE_URL=https://example.com/your-tag-guide
   ```

5. Run either:

   ```bash
   ./aws_tag_manager.py
   aws-tag-manager
   ```

The tool validates credentials and the expected account, loads `canonical.json`, scans EC2 instances in every accessible region (except terminated) for Environment and Product tags, logs violations, and writes `index.html`. Only regions with findings get a table section. Jenkins / Apache publish of `index.html` remains external.

### CSV gold-list merge and S3

| Flag | What it does |
|------|--------------|
| `--csv FILE\|s3://bucket/key` | merge a CSV of desired tags (columns: `resource_id`, `tag_key`, `tag_value`) with the scanned AWS tags; CSV wins on conflict and each conflict is recorded for review |
| `--write-gold` | write the merged result to `gold-list.json` plus `conflicts.json` |
| `--gold-output PATH` | change the gold-list output path |
| `--s3-bucket BUCKET` | upload `index.html` to `s3://BUCKET/reports/YYYY-MM-DD.html` after the scan; with `--write-gold` and `--csv`, also uploads `gold-list.json` and `conflicts.json` |

The CSV is read and validated before the scan starts, so a bad path or S3 key fails in seconds instead of after a full region sweep. The scan itself runs once — the same instance snapshot feeds both the violation report and the gold-list merge. A failed S3 upload logs an error; if the scan itself was clean, the run exits 4 so CI notices the missing report.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | scan finished, zero tag violations (HTML still written) |
| 1 | scan finished, one or more Environment/Product tag violations (HTML written) |
| 2 | credential failure (missing/invalid AWS credentials) — no HTML |
| 3 | account mismatch (caller is not `AWS_TAGMANAGER_EXPECTED_ACCOUNT`) — no HTML |
| 4 | config missing (expected account unset, bad `canonical.json`, unreadable `--csv`), or clean scan whose S3 upload failed (HTML written locally) |

## Platform (web UI + API)

Start the full stack (app + Postgres):

```bash
docker compose up
```

The web UI runs at http://localhost:8080 and provides a read-only dashboard to browse tags across cloud providers. Database defaults to SQLite; to use PostgreSQL, pass `TAGMANAGER_DB_URL` as an environment variable. The container entrypoint is `tagmanager-serve` — it builds the schema, seeds rules from `canonical.json` (first boot only), starts the scheduler, and serves uvicorn on port 8080, all in one process.

### API endpoints

| Endpoint | What it returns |
|----------|-----------------|
| `GET /api/health` | liveness probe — `{"status": "ok"}`; always open, even with auth on |
| `GET /api/resources` | catalog listing; filters: `cloud`, `scope_id`, `rtype`, `tag_key`, `tag_value` |
| `GET /api/violations` | violations joined to resources, latest scan run only; `?all=1` for full history; filters: `cloud`, `rule_key` |
| `GET /api/scans` | scan-run history, newest first — status, resources seen, violation count, skips |

UI routes: `/` (dashboard), `/resources`, `/violations` — same filters as the API, rendered server-side.

### Configuration reference

All platform settings load from environment variables with the `TAGMANAGER_` prefix.

| Variable | Default | Purpose |
|----------|---------|---------|
| `TAGMANAGER_DB_URL` | `sqlite:///tagmanager.db` | database connection URL (file-backed SQLite); use `postgresql+psycopg://` for PostgreSQL |
| `TAGMANAGER_AUTH_MODE` | `none` | `none` (open, dev only) or `oidc`; anything else refuses to boot — fails closed |
| `TAGMANAGER_OIDC_ISSUER` | — | OpenID Connect issuer URL (required if `AUTH_MODE=oidc`); app derives the discovery endpoint itself |
| `TAGMANAGER_OIDC_CLIENT_ID` | — | OIDC client ID (required if `AUTH_MODE=oidc`) |
| `TAGMANAGER_OIDC_CLIENT_SECRET` | — | OIDC client secret (required if `AUTH_MODE=oidc`) |
| `TAGMANAGER_SCAN_INTERVAL_MINUTES` | `60` | how often to scan clouds |
| `TAGMANAGER_SESSION_SECRET` | random per boot | secret key for signing session cookies. Unset is fine for a quick local run, but every restart invalidates all logged-in sessions — set it explicitly for anything long-lived so restarts/redeploys don't boot everyone out |
| `TAGMANAGER_AWS_ROLE_<account_id>` | — | assume-role ARN for an AWS scope. For a Scope row with `cloud="aws"` and `scope_id="<account_id>"`, set this to the role ARN the scanner should assume in that account; e.g. `TAGMANAGER_AWS_ROLE_123456789012` sets the role for scope_id `123456789012`. Leave unset to use the default credential chain with no assume-role hop |

## Storage optimizer CLI (`tagmanager-storage-scan`)

The storage side is `python -m tagmanager.storage.cli` (console script
`tagmanager-storage-scan` in the image / after `pip install .`). It scans
mass storage into age-band rollups, prices what stale data costs, projects
savings, recommends a better layout, emits ready-to-apply artifacts, and —
new in v5 — reads access/write telemetry to sharpen those recommendations
and diffs your live config against what it would generate. **Everything is
read-only against the cloud.** Nothing here ever moves, deletes, or
rewrites your data or config; the tool emits files and prints diffs, and
you apply them.

The model is scan-once, analyze-many: one scan saves a run to the database,
and every other flag works off the latest saved run (so `--cost-report`,
`--recommend-structure`, `--dry-run-diff`, and the `--emit-*` flags need no
re-scan). Run without `--bucket` to work from the latest run.

### Scan and scope

| Flag | What it does |
|------|--------------|
| `--backend s3\|azure\|gcs\|fs` | storage backend (default `s3`); `fs` treats `--bucket` as a root directory path |
| `--account-url URL` | Azure: `https://<account>.blob.core.windows.net` |
| `--bucket NAME` | bucket / container to scan (repeatable; omit with an analysis flag to work from the latest run) |
| `--prefix P` | only scan keys under this prefix |
| `--age-bands 90,365` | comma-separated day thresholds for the age bands |
| `--prefix-depth N` | path segments to roll prefixes up to |
| `--rollup-owners` | also key rollup cells by object owner (cardinality cost; Azure/GCS record no owner) |
| `--rollup-types` | also key cells by coarse data type (logs / media / archives / data / docs / other) from the key extension |
| `--csv-out PATH` | write the rollup summary to CSV |

### Access & write telemetry (sharpens ages and recommendations)

By default an object's age is its `LastModified`. Fold in access logs and
the age becomes access-aware — the newer of modified-or-**read** — and the
recommendations gain read/write signals. All local-file parsing; the tool
never enables logging or pulls events for you.

| Flag | What it does |
|------|--------------|
| `--access-logs GLOB` | scan mode: local S3 server-access-log files to fold into a last-read index (ages become access-aware lower bounds; read + write ops feed request rates) |
| `--cloudtrail-logs GLOB` | scan mode: local CloudTrail data-event log files (`.json`/`.json.gz`) for GetObject reads — merges into the same index. S3 data events are off by default and bill per event; this parses only what you exported |

Request rates are **averages** over the sample window, never the peak the
AWS per-prefix ceilings are measured against — the recommendation carries
that caveat.

### Analysis and recommendations

| Flag | What it does |
|------|--------------|
| `--cost-report` / `--cost-csv PATH` | price the rollups with the shipped pricing snapshot |
| `--project-savings` / `--savings-csv PATH` | project per-option savings (delete / age-out / intelligent-tiering / archive) for the stale slice, with break-even months |
| `--recommend-structure` | derive per-prefix layout recommendations and persist them (date-split, zone-split, compact-first, type-split, prefix-fanout, expire-in-place) |
| `--structure-csv PATH` | write the recommendations to CSV |

Each recommendation carries a **confidence** label (high / medium / low)
and the **evidence** it rests on — telemetry-backed advice (fan-out from
request rates, expire-in-place from write rates, compact-first from the
object-size distribution) grades high; an age-only cold-data recommendation
grades low precisely so you can tell the difference. A prefix whose write
telemetry shows churn on cold data gets an **expire-in-place** warning —
transitioning churning data bills minimum-duration early-delete charges, so
it advises a lifecycle Expiration in place over a transition.

### Emit artifacts (you apply them)

| Flag | What it does |
|------|--------------|
| `--emit-lifecycle DIR` | per-bucket lifecycle config JSON + `APPLY.md` (applying REPLACES the bucket's entire lifecycle config) |
| `--delete-after DAYS` | add Expiration rules to `--emit-lifecycle` (the async, AWS-managed mass-delete path) |
| `--emit-tiering DIR` | per-bucket Intelligent-Tiering configs + `APPLY.md` |
| `--age-out-map 90=STANDARD_IA,365=DEEP_ARCHIVE` | override the age-out transition targets, keyed on threshold days |
| `--emit-structure DIR` | `PROPOSAL.md` with suggested layouts + apply guidance |
| `--emit-delete-manifests DIR` | scan mode: stream stale objects into chunked delete-objects JSON manifests |
| `--emit-batch-copy DIR` | scan mode: stream stale objects into S3 Batch Operations copy manifests (CSV) |
| `--emit-move-plan DIR` | scan mode: old-key,new-key move plans from the latest run's recommendations (two-pass: `--recommend-structure` first) |
| `--html-report PATH` | one-page HTML insights report (age, cost, savings, structure, artifacts) |

### Dry-run diff (apply-ladder rung one, zero writes)

| Flag | What it does |
|------|--------------|
| `--dry-run-diff` | **S3 only.** Read the LIVE bucket lifecycle / intelligent-tiering config and diff it, rule-by-rule, against what the latest saved run would generate — read-only, zero writes |

The diff is a whole-config **set diff by rule ID**, because applying a
lifecycle config REPLACES the bucket's entire rule set. It classifies each
rule as would-add, would-change, unchanged, or **would-remove** — a live
rule you don't generate would be dropped by an apply, and that case is
called out loudly. A config kind the run generates nothing for is reported
as "not generated — an apply would not touch it" (never a false drop). No
read permission on a bucket's config surfaces as "unknown — no permission",
never conflated with "no config present". The output is shaped for a future
guarded apply.

### Exit codes

`0` OK · `4` config error (nothing to do, no saved run to analyze,
`--dry-run-diff` on a non-S3 backend, or key-level manifests requested
without a scan).

## Dev: tests and lint

```bash
pip install -e ".[dev]"
# or: pip install -r requirements-dev.txt

pytest
./static_analysis.sh
```

`static_analysis.sh` runs pylint (repo `pylintrc`, 10.00/10 expected) and pycodestyle (max line length 120, per `tox.ini`). CI runs the pytest suite on every push.

## TODO

  # - decide what an empty tag_value in the CSV means (today it overwrites
  #   the AWS value with "" and records a conflict — maybe it should clear
  #   or skip instead)
  # - conflicts.json path is hardcoded while --gold-output is configurable
  # - one live end-to-end run with --s3-bucket against a real account
  #   (S3 paths are currently verified against stubbed clients only)

More to come...
