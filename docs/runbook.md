# TagManager Runbook

Operating guide for the TagManager platform — deploying it, feeding it credentials, keeping it healthy, and digging it out when something breaks. For flags, endpoints, and the full env-var table, see the [Technical Reference](technical-reference.md). Back to the [README](../README.md).

## Service Overview

One container, one process: `tagmanager-serve` boots the database schema, seeds tagging rules from `canonical.json` (first boot only), reaps any scan runs left dangling by a crash, starts the in-process scheduler, and serves the FastAPI app (UI + JSON API) on port 8080. State lives entirely in the database — SQLite by default, PostgreSQL for anything real.

**Single-replica assumption:** the scheduler, its overlap guard, and the boot-time stale-run reaper all assume exactly one app replica writing scan runs. Do not scale this horizontally — two replicas booting at once can reap each other's live runs. If you need HA, that's a design change, not a config change.

## Deploy

### Docker Compose (recommended)

```bash
docker compose up -d
```

Brings up Postgres 16 (volume `pgdata`, healthchecked) and the app on port 8080. The app waits for the DB healthcheck before starting.

### Container only

```bash
docker build -t tagmanager .
docker run -p 8080:8080 -e TAGMANAGER_DB_URL=postgresql+psycopg://user:pass@host/db tagmanager
```

Omit `TAGMANAGER_DB_URL` and you get file-backed SQLite *inside the container* — fine for a smoke test, gone when the container is. Mount a volume or use Postgres for anything you want to keep.

### Bare (dev)

```bash
pip install -e .
tagmanager-serve
```

### Stop / restart

`docker compose down` (add `-v` only if you mean to destroy the Postgres volume — that's the entire catalog). Restarts are safe: schema creation is idempotent, rule seeding only runs on an empty rules table, and the boot reaper cleans up any scan that died mid-flight.

## Configuration

Everything is env vars with the `TAGMANAGER_` prefix — full table in the [Technical Reference](technical-reference.md#configuration-reference). The ones that matter operationally:

- `TAGMANAGER_DB_URL` — point at Postgres in production (`postgresql+psycopg://...`).
- `TAGMANAGER_AUTH_MODE` — `none` means the UI and API are wide open; only acceptable on a trusted network or local dev. `oidc` requires issuer + client id + client secret. Any other value refuses to boot (fails closed) — a typo here is a startup crash, not a silent open door.
- `TAGMANAGER_SESSION_SECRET` — set it explicitly in production; unset means a fresh random secret every boot, which logs everyone out on every restart.
- `TAGMANAGER_SCAN_INTERVAL_MINUTES` — default 60. The first scheduled scan fires one full interval *after* boot, not at boot.

Secrets come from env vars / your orchestrator's secret store only — never in the repo, the image, or the DB.

## Cloud Credentials

The scanner reads, never writes. Grant read-only inventory access per cloud:

### AWS

Default boto3 credential chain (env keys, shared credentials file, SSO, instance/task role). Needs `tag:GetResources` (Resource Groups Tagging API). For multi-account: create a readable role in each target account and set `TAGMANAGER_AWS_ROLE_<account_id>` to its ARN — the scanner does an assume-role hop per scope. Unset means the default chain is used as-is.

### Azure

`DefaultAzureCredential` — for a service principal, set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` in the app environment. The SP needs the Reader role on each target subscription (Resource Graph queries ride on Reader).

### GCP

Application-default credentials — set `GOOGLE_APPLICATION_CREDENTIALS` to a service-account key file path (mount it into the container), or use workload identity. The SA needs `cloudasset.assets.searchAllResources` (e.g. roles/cloudasset.viewer) on each target project.

## Adding Scan Scopes

A "scope" is one AWS account / Azure subscription / GCP project. Scopes live in the `scopes` table; there is no UI or API for them yet (read-only UI is a sub-project-1 constraint), so add rows directly:

Postgres (compose stack):

```bash
docker compose exec db psql -U tagmanager -d tagmanager -c \
  "INSERT INTO scopes (cloud, scope_id, display_name, enabled) VALUES ('aws', '123456789012', 'prod account', true);"
```

SQLite:

```bash
sqlite3 tagmanager.db \
  "INSERT INTO scopes (cloud, scope_id, display_name, enabled) VALUES ('gcp', 'my-project-id', 'core project', 1);"
```

Notes:

- `cloud` is `aws`, `azure`, or `gcp`; `scope_id` is the account id / subscription id / project id.
- `regions` (JSON list) optionally narrows AWS region sweep; null means all accessible regions.
- Set `enabled = false` to bench a scope without deleting it — the scopes list is re-read every tick, so changes take effect on the next scan with no restart.

## Managing Rules

Rules are required-tag checks: a tag key, its allowed values, and optional `applies_cloud` / `applies_type` scoping (null means applies everywhere). On first boot with an empty `rules` table, `canonical.json` seeds one rule per key (Environment, Product). After that the DB is the source of truth — editing `canonical.json` does nothing unless you empty the rules table first.

Add or adjust a rule:

```bash
docker compose exec db psql -U tagmanager -d tagmanager -c \
  "INSERT INTO rules (key, allowed_values, applies_cloud) VALUES ('CostCenter', '[\"eng\", \"ops\"]', 'aws');"
```

A resource missing the key yields issue `missing`; present with a value outside `allowed_values` yields `invalid`. Rule changes apply on the next scan run.

## Storage Optimizer

The storage side scans mass storage (S3, Azure Blob, GCS, local/SMB) for old and costly data, then generates lifecycle artifacts and layout recommendations. The image bundles every backend — no extra install. It is **read-only against the cloud**: it lists objects, reads config, emits files, and prints diffs — it never moves, deletes, or rewrites your data or config. You apply what it emits.

Fold in local access logs (`--access-logs`) or CloudTrail data-event exports (`--cloudtrail-logs`) and object age becomes last-**read**, not just last-modified; the same telemetry drives per-prefix request-rate and write-churn signals that sharpen the recommendations (each carries a confidence label and its evidence). This is opt-in and parses only the files you point it at — the tool never enables logging or pulls events for you.

### Targets and scans (web)

Unlike tag scopes, storage targets have a UI. Go to **Storage → Targets**, add a target (backend, bucket/container names — or root paths for `fs` — one per line, age bands, owner-rollup toggle), and hit **scan now**. **Storage → Jobs** shows progress live (2s polling) and lets you cancel — cancellation lands at the next batch boundary, not instantly. **Storage → Insights** renders cost / savings / recommendations off the latest run per backend; the run page generates and zips artifacts (lifecycle configs, tiering configs, structure proposal, HTML report). Key-level manifests (delete / batch-copy / move plans) remain CLI-only — see the [Technical Reference](technical-reference.md).

### Credentials

Storage backends read the same environment credentials as the tag scanner (AWS chain, `DefaultAzureCredential`, GCP application-default) — see [Cloud Credentials](#cloud-credentials). The storage read paths need list access: `s3:ListBucket` (+ `s3:GetObject` only if you fold in access logs), Azure `Storage Blob Data Reader`, GCS `storage.objects.list`. `--dry-run-diff` additionally needs `s3:GetLifecycleConfiguration` and `s3:GetIntelligentTieringConfiguration` (read-only). Azure last-access enrichment additionally needs last-access-time tracking enabled on the account.

### Artifacts volume

Generated artifacts land under `TAGMANAGER_ARTIFACT_DIR` (default `/data/artifacts` in the image), persisted on the compose `artifacts` volume so they survive restarts. Retrieve them via the browser download or straight off the volume:

```bash
docker compose cp app:/data/artifacts ./artifacts-backup
```

`docker compose down` keeps the volume; add `-v` only to wipe it.

### CLI in the image

Everything the web app does (bar key-level manifests) is also a CLI, shipped in the same image — no server needed:

```bash
docker compose exec app tagmanager-storage-scan --backend s3 --bucket my-lake --age-bands 90,365
docker compose exec app tagmanager-storage-scan --cost-report --project-savings --recommend-structure
docker compose exec app tagmanager-storage-scan --dry-run-diff
docker compose exec app tagmanager-storage-scan --emit-lifecycle /data/artifacts/manual/
```

On a bare install the identical console scripts are on `PATH` after `pip install .` — `tagmanager-serve`, `tagmanager-storage-scan`, and the classic `aws-tag-manager` EC2 scanner. Web app and CLI are the same service layer; neither is a second-class citizen.

### Preview changes before applying (dry-run diff)

Before you apply an emitted lifecycle / tiering config, `--dry-run-diff` (S3 only) reads the **live** bucket config and diffs it, rule-by-rule, against what the latest saved run would generate — read-only, zero writes. Watch for the loud **would-remove** lines: applying a lifecycle config REPLACES the bucket's entire rule set, so any live rule the tool doesn't generate (a hand-authored rule, say) would be dropped by an apply. "unknown — no permission" means the credentials can't read that bucket's config (needs `s3:GetLifecycleConfiguration` / `s3:GetIntelligentTieringConfiguration`), distinct from "no config present". The diff is the freshness signal — a clean diff means live already matches what a fresh scan would generate.

## Scan Lifecycle & Manual Runs

Each run writes a `scan_runs` row: `running` → `complete` (all scopes swept) or `partial` (at least one scope skipped, or the run was reaped after a crash). A failing scope never fails the run — it lands in the run's `skips` list with the error string, and every other scope still gets scanned. The overlap guard skips a tick entirely if a run is still `running`.

Trigger a scan without waiting for the interval:

```bash
docker compose exec app python -c "
from tagmanager.config import get_settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.providers.aws_provider import AwsProvider
from tagmanager.providers.azure_provider import AzureProvider
from tagmanager.providers.gcp_provider import GcpProvider
from tagmanager.scanner import run_scan
from tagmanager.serve import _scopes_loader
engine = get_engine(get_settings().db_url); create_all(engine)
maker = session_factory(engine)
providers = {'aws': AwsProvider(), 'azure': AzureProvider(), 'gcp': GcpProvider()}
run = run_scan(maker(), providers, _scopes_loader(maker)())
print(run.status, run.resources_seen, run.violation_count, run.skips)
"
```

(Safe alongside the scheduler only because both live in the same single replica; don't script this concurrently from multiple places.)

## Monitoring

- **Liveness:** `GET /api/health` → `{"status": "ok"}`. Always open, even with OIDC on — safe for load-balancer checks.
- **Scan health:** `GET /api/scans` — newest first. Watch for: no new runs (scheduler dead or interval misconfigured), `partial` status (check `skips` for the failing scope + error), `violation_count` trends.
- **Logs:** structured to stdout (`docker compose logs -f app`). Normal cadence: `starting tagmanager...` → `tagmanager up...` at boot, then per-scan `scanning <cloud> scope <id>...` and `scan complete... N resource(s), N violation(s), N skip(s)`. `skipping scope <id> (<error>)...` warnings are the per-scope failures.

## Incident Response

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| App won't boot, `unrecognized auth_mode` in logs | typo in `TAGMANAGER_AUTH_MODE` | set to `none` or `oidc`; fail-closed is intentional |
| No scans ever run | scheduler waits one full interval after boot | wait, lower `TAGMANAGER_SCAN_INTERVAL_MINUTES`, or trigger a manual run |
| Every tick logs `scan already running — skipping this tick...` | a `running` row is stuck (crash mid-scan without a restart since) | restart the app — boot reaper marks stale `running` rows `partial`; or update the row's status by hand |
| Run status `partial`, scope in `skips` | bad credentials, missing permission, unreachable cloud API, or scope's cloud has no provider | read the error string in `skips`; fix creds/permissions for that scope — other scopes were still scanned |
| AWS scope skipped with access denied | assume-role env var missing or role not assumable | check `TAGMANAGER_AWS_ROLE_<account_id>` spelling matches `scope_id` exactly |
| Everyone logged out after each deploy | `TAGMANAGER_SESSION_SECRET` unset (random per boot) | set it to a stable secret |
| OIDC redirect loop / callback error | issuer URL wrong or client misconfigured at the IdP | verify `TAGMANAGER_OIDC_ISSUER` serves `/.well-known/openid-configuration`; confirm redirect URI `https://<host>/auth/callback` is registered |
| Violations page looks stale | violations are scoped to the latest run by default | `?all=1` on `/api/violations` or the UI for full history; check `/api/scans` for when the last run actually finished |
| DB gone after container restart | SQLite inside an unmounted container FS | use Postgres or mount a volume; the data was not recoverable — re-scan repopulates the catalog |

## Backup & Restore

- **Postgres:** `docker compose exec db pg_dump -U tagmanager tagmanager > tagmanager.sql`; restore with `psql`. The `pgdata` volume persists across `docker compose down` (without `-v`).
- **SQLite:** copy the `tagmanager.db` file while the app is stopped.
- **What's actually precious:** `rules` and `scopes` (your configuration). The resource catalog and violations are re-derivable — one full scan rebuilds them. Back up config religiously; treat scan data as cache.

## Known Limits (sub-project 1)

- Single replica only — no horizontal scaling (scheduler + reaper assumption).
- Read-only UI — scopes and rules managed via SQL.
- Scanner is read-only against clouds — no tag remediation/write-back yet (GCP write shim lands in sub-project 2).
- No per-scope scan scheduling — one global interval.

More to come...
