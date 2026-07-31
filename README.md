# TagManager

Multi-cloud tag compliance — scan AWS, Azure, and GCP, catch the tags that are missing or wrong, and see it all in one place.

Author(s): John Reed, Nick Bitzer

## What is TagManager?

Ever tried to figure out who owns a mystery EC2 instance at 2am, only to find its tags are empty — or worse, wrong? That's the problem TagManager exists to solve. Cloud tags are how you answer "what is this, who owns it, and what environment is it in" — but tags only work if they're actually there, and actually consistent. TagManager scans your cloud accounts on a schedule, compares every resource's tags against your canonical rules (allowed keys and values), and surfaces every deviation so you can fix drift before it bites you...

It started life as an AWS EC2 tag checker (that CLI still works — see the [Technical Reference](docs/technical-reference.md)) and has grown into a platform: one container that inventories AWS, Azure, and GCP into a single catalog, evaluates your tagging rules, and serves a read-only web dashboard plus a JSON API.

## Capabilities

- **Multi-cloud inventory** — bulk-reads resources and tags from AWS (Resource Groups Tagging API), Azure (Resource Graph), and GCP (Cloud Asset Inventory) into one normalized catalog. GCP labels normalize to tags, so the rules don't care which cloud a resource lives in.
- **Rules engine** — required-tag rules with allowed values, stored in the database, with optional per-cloud / per-resource-type scoping. Seeds itself from your existing `canonical.json` on first boot.
- **Scheduled scans** — an in-process scheduler sweeps every configured account / subscription / project on an interval (default hourly), with an overlap guard so runs never stack up. One failing scope is recorded as a skip, never a failed run — your other clouds still get scanned.
- **Web dashboard** — read-only UI (server-rendered, htmx) for browsing resources, violations, and scan history with cloud / type / tag filters.
- **JSON API** — `/api/resources`, `/api/violations`, `/api/scans`, `/api/health` for scripting and integration.
- **OIDC auth** — plug in any OpenID Connect identity provider, or run wide open in dev mode. Unrecognized auth config fails closed, not open.
- **Classic AWS CLI** — the original `aws-tag-manager` EC2 scanner still ships: HTML violation reports, CSV gold-list merge, S3 publishing, CI-friendly exit codes.
- **Storage age & cost analysis** — scan S3 buckets into age-band rollups (last-modified vs your thresholds), price what stale data costs monthly, and project per-option savings (delete / age-out rules / intelligent tiering / archive) with break-even months and small-object honesty built in.

## How it can be used

- **Compliance dashboard** — run the container, point your team at the UI, and make tag drift visible instead of tribal knowledge.
- **Scheduled enforcement reporting** — let the scanner sweep every hour and pull `/api/violations` into whatever alerting or ticketing you already have.
- **CI gate** — the classic CLI exits nonzero on violations, so a pipeline stage can fail a deploy when tags are out of policy.
- **Tag inventory API** — query the catalog (`/api/resources?tag_key=Product&tag_value=Core`) to answer "what do we have, where, and how is it tagged" across all three clouds.

## Quick start

The whole thing — multi-cloud tag compliance **and** storage lifecycle
optimization, web UI plus scheduled scans, all backends — in one command:

```bash
docker compose up
```

Then open http://localhost:8080. The dashboard is up, the database is
seeded from `canonical.json`, the tag scanner runs hourly, and the
**Storage** pages let you configure scan targets, launch and watch scans,
read cost/savings/recommendations, and download generated artifacts as a
zip. The image bundles every storage backend (S3, Azure Blob, GCS,
local/SMB); pass cloud credentials through the environment (see the
commented block in `docker-compose.yml` and the [Runbook](docs/runbook.md)).
Generated artifacts persist on the `artifacts` volume.

The CLI ships in the same image — same tool, no web server needed:

```bash
docker compose exec app tagmanager-storage-scan --bucket my-lake --age-bands 90,365
docker compose exec app tagmanager-storage-scan --cost-report --project-savings
```

Classic AWS CLI:

```bash
source virtShell.sh
export AWS_TAGMANAGER_EXPECTED_ACCOUNT=123456789012
./aws_tag_manager.py
```

Storage age & cost scan (S3, Azure Blob, GCS, or local/SMB via `--backend`):

```bash
python -m tagmanager.storage.cli --bucket my-data-lake --age-bands 90,365
python -m tagmanager.storage.cli --cost-report --project-savings --recommend-structure
python -m tagmanager.storage.cli --emit-lifecycle out/ --html-report storage.html
```

Scan once, then everything else works off the saved run — cost report,
per-option savings, structure recommendations, generated artifacts
(lifecycle configs, tiering configs, delete/batch-copy/move manifests via
the `--emit-*` flags), and the one-page HTML report. The web UI gets a
`/storage` page too. All figures are list-price estimates (refresh
snapshots with `python -m tagmanager.storage.pricing_refresh`).

## Documentation

| Page | What's in it |
|------|--------------|
| [Technical Reference](docs/technical-reference.md) | CLI usage, CSV gold-list merge and S3 publishing, exit codes, full configuration reference, dev setup (tests + lint) |
| [Runbook](docs/runbook.md) | Operating the platform: deploy, credentials per cloud, adding scan scopes, managing rules, monitoring, incident response, backup/restore |
| [Platform Core Design Spec](docs/superpowers/specs/2026-07-31-tagmanager-platform-core-design.md) | Why the platform is shaped the way it is — multi-cloud evolution, sub-project 1 |
| [Platform Core Implementation Plan](docs/superpowers/plans/2026-07-31-platform-core.md) | The 13-task TDD plan the platform was built from |

More to come...
