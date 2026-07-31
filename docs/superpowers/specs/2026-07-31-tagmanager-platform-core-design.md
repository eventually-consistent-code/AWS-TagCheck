# TagManager Platform Core — Design Spec

Date: 2026-07-31
Status: Approved (brainstorm 2026-07-30/31, John Reed)
Scope: Sub-project 1 of the TagManager evolution roadmap

## Vision (where the whole project is going)

Evolve TagManager from a single-account AWS EC2 tag-compliance CLI into a
lightweight, multi-cloud tag governance platform: AWS, Azure, and Google
Cloud behind one consistent web UI, leveraging each cloud's native
inventory/tagging APIs under the hood, with an AI analysis layer that
recommends tags for asset management and compliance (GDPR, NIST, PCI, SOX).

Inspirations mapped to pillars:
- Databricks Unity Catalog → tag-driven governance, ABAC posture, cost tracking
- Alex Solutions → ML-assisted tagging (business context → assets)
- LSEG Intelligent Tagging → NLP over unstructured content (S3/Blob/GCS)

## Roadmap (decomposition — each row is its own spec → plan → build)

| # | sub-project | ships |
|---|---|---|
| 1 | **Platform core (this spec)** | container app, 3-cloud read plugins, Postgres catalog, OIDC auth, read-only web UI |
| 2 | Remediation | review queue, direct tag apply (AWS/Azure + GCP shim), change-set export, audit trail |
| 3 | AI layer | model-provider interface (API-key or local model), all seven analyzers (below) |
| 4 | Governance + cost | per-framework policy packs, cost rollups by tag, ABAC posture report |

Sub-project 3 may leapfrog 2 if AI recommendations are wanted before the
apply path; change-set export covers the gap.

### The seven AI analyzers (locked scope for sub-project 3)

1. Compliance classification — sample unstructured data, detect PII/PHI/card
   data, recommend `data-classification` / `compliance-scope` / retention tags
2. Contradiction detection — tags claim X, contents prove Y (public bucket
   containing PII, non-prod DB receiving prod-shaped data)
3. Untagged-resource inference — owner/product/environment from names,
   attachments, network neighbors, IaC repos
4. Tag hygiene — synonym sprawl detection, canonical merge proposals
5. Natural-language catalog queries — English → structured catalog query
6. Policy drafting — compliance framework section → required-tag ruleset
7. Digest narratives — scheduled plain-language "what changed / what's risky"

All seven consume the catalog this spec builds and emit into the review
queue sub-project 2 builds. Model access is via a provider interface with
two day-one implementations: hosted API key (Anthropic / OpenAI / Bedrock /
Azure OpenAI / Vertex) and a local OpenAI-compatible endpoint (Ollama/vLLM)
for data-residency-constrained clients. Analyzers sample and redact (first
N KB, DLP-masked) — whole objects never leave the environment. Native
classifiers (Macie, Microsoft Purview, GCP Sensitive Data Protection) can
feed the model as evidence where enabled.

## Decisions of record

- Web UI is **view + fix** (fix lands in sub-project 2); day-one UI is read-only
- **All taggable resources**, not just EC2 — native bulk inventory APIs per cloud
- **All three clouds day one** (read side); GCP write is shimmed later and
  capability-flagged
- Both write paths in sub-project 2: direct apply and change-set export,
  routed by allowlist
- **Container deployment** (multi-cloud portability beat the earlier
  serverless-on-AWS choice)
- **OIDC** auth against any IdP; named users for audit
- **Multi-account/subscription/project from day one**
- Postgres (SQLite in dev) — managed Postgres exists natively on all three clouds
- Repo renames `AWS-TagManager` → `TagManager` with sub-project 1's first release

## Architecture

One container: FastAPI serves both the JSON API and a server-rendered UI
(Jinja2 + htmx — no Node build chain). SQLAlchemy over Postgres (SQLite for
dev). APScheduler runs scans in-process. One Dockerfile + docker-compose for
dev; deploys unchanged to ECS/Fargate, Azure Container Apps, or Cloud Run.

Repo layout:

    tagmanager/
      app/          # FastAPI routers, auth middleware, Jinja templates
      providers/    # base.py interface + aws.py, azure.py, gcp.py
      rules/        # compliance engine (rulesets → violations)
      models/       # SQLAlchemy tables
      scheduler.py
    aws_tag_manager.py   # survives as standalone CLI scanner mode

Existing `aws.py` scan/evaluate logic ports into `providers/aws.py`; the
CLI keeps working throughout the transition.

## Provider interface

`list_resources(scope) → Iterator[NormalizedResource]`

NormalizedResource: `{cloud, scope_id, region, type, resource_id, name, tags{}}`
(Azure tags and GCP labels normalize into the same map.)

| cloud | inventory call | cross-org access |
|---|---|---|
| AWS | Resource Groups Tagging API `get_resources`, per account | assume-role per account |
| Azure | one Resource Graph KQL query per tenant | service principal at management-group scope |
| GCP | Cloud Asset Inventory at org scope | service account with org-level viewer |

Each provider declares capability flags (`supports_direct_write`, per-type
granularity). Write methods (`apply_tags`, `export_changeset`) are defined
on the interface now, implemented in sub-project 2 — the GCP write shim
(per-service label APIs behind the same method, export-only where no API
exists) slots in there without interface change. Sub-project 3's analyzers
inject suggested tags through the same normalized model.

## Rules engine

canonical.json becomes DB-stored rulesets, seeded from the existing file on
first migration. A ruleset: required tag keys + allowed values, scoped by
cloud / scope_id / resource type. Evaluation is pure functions (the current
`evaluate_required_tags` generalized). Each scan writes findings to a
`violations` table.

## Data model (tables)

- `resources` — current normalized state, upserted per scan
- `scan_runs` — one row per scheduled run: scopes covered, skips, counts, timing
- `violations` — findings per scan, linked to resource + rule
- `rulesets` / `rules` — the compliance rules
- `scopes` — configured accounts/subscriptions/projects + credentials refs
- `users` handled by OIDC claims; roles (`viewer`/`operator`/`admin`) stored locally

Credential material itself lives in env vars / cloud secret managers —
never in the database.

## Data flow

APScheduler fires per scope → provider `list_resources` → normalized upsert
into `resources` + `scan_runs` row → rules engine writes `violations` →
UI/API read only from Postgres. Scan history is retained (drift detection
and digest narratives consume it later).

## Web UI (read-only, day one)

- Dashboard: compliance % by cloud / scope / rule, scan freshness, skips
- Resource browser: filter by cloud, scope, type, tag key/value, violation state
- Violation list: the current HTML report, live and filterable
- Login via OIDC; `viewer` role required for everything

## Error handling

- Scope-level isolation: one failing account/subscription/project records a
  skip on the scan run and the run continues — same philosophy as today's
  region skips. UI badges partial scans.
- Cloud API throttling: exponential backoff with jitter, per-provider.
- API errors: RFC 7807 problem-JSON.
- Scheduler overlap guard: a scope never has two concurrent scans.
- Single app replica assumed in sub-project 1 (in-process scheduler); a
  DB-level scan lock replaces this assumption if the app is ever scaled
  horizontally.

## Testing

- TDD throughout (existing project discipline)
- Provider tests against stub clients with recorded API-response fixtures
  per cloud (the existing mock.Mock pattern, scaled)
- Rules engine: pure unit tests
- API + auth: FastAPI TestClient
- One docker-compose smoke test: seed SQLite, run a stubbed scan, assert
  dashboard renders
- Existing GitHub Actions pytest workflow extends to the new layout

## Carried forward from today's tool

- CSV gold-list + conflicts model becomes the seed of sub-project 2's
  review queue; schema designed so existing `gold-list.json` imports cleanly
- Canonical lists seed the first ruleset
- Exit-code discipline moves to scan_run status + API health semantics
