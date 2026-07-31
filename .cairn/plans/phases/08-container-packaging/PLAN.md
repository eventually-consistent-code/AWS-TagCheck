---
issues: [45]
---
# Phase 8: container packaging — Plan

Goal: `docker compose up` is the whole TagManager web app — all backends,
persistent artifacts, healthchecked — and the CLI ships first-class in the
same image. Easily installed, easily moved.

No research fan-out: the packaging surface was inventoried directly
(Dockerfile, docker-compose.yml, pyproject scripts, /api/health,
docs/runbook) — a known task with no material unknowns, so no RESEARCH.md.

## Tasks

### Issue #45 — container packaging, CLI preserved

1. `pyproject.toml`: add `[project.optional-dependencies] storage`
   (azure-storage-blob>=12.19, google-cloud-storage>=2.14) so the image
   can install all storage backends; `config.py` artifact_dir default
   → `/data/artifacts` is env-overridable already (no code change —
   compose sets TAGMANAGER_ARTIFACT_DIR). Confirm the three console
   scripts are intact.
2. `Dockerfile`: install `.[storage]`; create an unprivileged user and a
   `/data` tree (artifacts + sqlite) owned by it, run as that user;
   `ENV TAGMANAGER_ARTIFACT_DIR=/data/artifacts`; add a stdlib-urllib
   `HEALTHCHECK` against `http://localhost:8080/api/health`; keep
   `CMD ["tagmanager-serve"]`. `.dockerignore` already excludes the
   noise.
3. `docker-compose.yml`: app-service `healthcheck` (python urllib one-
   liner, no curl), a named `artifacts` volume at `/data`, and a
   commented env-passthrough block for cloud creds (AWS_*, AZURE_*,
   GOOGLE_APPLICATION_CREDENTIALS + a mounted-key-file comment,
   TAGMANAGER_AWS_ROLE_*); keep Postgres as the compose default.
   `TAGMANAGER_ARTIFACT_DIR=/data/artifacts` on the app service.
4. Docs: README quick-start updated (compose = full multi-cloud web app;
   storage scan/analyze/download from the browser); `docs/runbook.md`
   gains a storage section — configure targets, credential passthrough,
   artifact volume backup, and the CLI-in-image recipe
   (`docker compose exec app tagmanager-storage-scan --help`); note CLI
   parity on bare `pip install .`. No AWS- brand regressions
   (grep gate holds).

## Notes

- One task, four files + docs — packaging, not code. The Python suite
  (212 tests) stays green untouched; verify drives the real artifacts:
  `docker build` succeeds, the image runs, `/api/health` answers, and
  `tagmanager-storage-scan --help` works inside the container (skipped
  with a stated reason only if Docker is unavailable in the verify
  environment).
- Milestone-closing phase for the web-app arc: after this, `/cairn:ship`
  then the deeper-signals phases (1-5) resume.
