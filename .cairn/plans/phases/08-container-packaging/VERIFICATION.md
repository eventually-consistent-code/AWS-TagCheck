# Phase 8: container packaging — Verification

Verified: 2026-07-31

## Goal-backward check

Phase promise: `docker compose up` is the whole TagManager web app — all
backends, persistent artifacts, healthchecked — with the CLI first-class
in the same image.

Docker was available, so the promise was exercised LITERALLY, not
statically:

- **`docker compose up -d --build`** brought up Postgres 16 + the app;
  the app reached `healthy` (its own HEALTHCHECK) in ~4 s after the DB
  healthcheck gated it.
- **Postgres-backed, not sqlite**: `docker compose exec app` reported
  `db_url` scheme `postgresql+psycopg` — the composed app runs on the
  real database.
- **Every storage web surface serves 200** over the mapped port
  (`/api/health` → `{"status":"ok"}`, `/storage/targets`,
  `/storage/jobs`, `/storage/cost`, `/api/scans`).
- **Artifact dir writable** on the `/data` volume from inside the
  composed app; **all three console scripts** (`tagmanager-serve`,
  `tagmanager-storage-scan`, `aws-tag-manager`) present and runnable in
  the image; **runs non-root** (`whoami` = tagmanager) — from the
  work-phase `docker run` proof.
- **`docker compose config` validates**; **`.[storage]` extra** makes
  the azure/gcs storage modules importable (checked in the venv too).
- **Compose teardown keeps the volume** (`down` without `-v`); the
  `-v` path was exercised on the throwaway override stack.

## Honest note — a red herring, run to ground

The first compose run's host-side probe hit HTTP 404 on `/api/health`
while the container's OWN healthcheck reported `healthy` — a
contradiction. Rather than assume an app bug, checked host port 8080:
a stray unrelated host Python process (PID 59827) was squatting on it,
so the host probe was reaching that, not the container. Re-published the
app on a clean port (8099) → `/api/health` 200 and all storage pages 200.
The 404 was purely a verify-host port collision; zero phase-8 defect.

## Gates

- Tests: 212 passed, 0 failed — packaging-only phase, no Python behavior
  change, suite untouched (the parity principle: this phase adds no
  behavior to assert).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flag on 45 normalizes with
  this file. Open issues in phase: none. TDD frontmatter: none.
- Ledger: issue 45 with commit range (a937d46..baa9efc).
- Brand grep gate: clean on all live surfaces incl. the new
  Dockerfile/compose/docs.

## Result

PASS — verified against a live `docker compose up`.

## Deviations

- Cloud-backend storage scans through the container were not driven with
  real credentials (none available in the verify environment); the
  passthrough is env-only and documented, and the fs backend proved the
  full trigger→scan→artifact path live in phase 7.
