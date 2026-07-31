# Phase 8: container packaging — Context

## Locked decisions

- **The image bundles ALL storage backends** via a new
  `[project.optional-dependencies] storage` extra (azure-storage-blob,
  google-cloud-storage); the Dockerfile installs `.[storage]`. The
  phase-4 "base install is boto3-only" decision stands for bare `pip
  install` — but the CONTAINER is the everything-works web app, so
  azure/gcs storage scans work out of the box. The base providers'
  azure-identity/azure-mgmt/google-cloud-asset deps are already in the
  core list.
- **Credentials pass by environment only** — no secrets baked into the
  image, no key files mounted by default. AWS/Azure/GCS SDKs already
  read the environment (AWS_*, AZURE_*, GOOGLE_APPLICATION_CREDENTIALS,
  TAGMANAGER_AWS_ROLE_*); compose passes them through from the host.
  The GCS/AWS file-credential path (a mounted service-account JSON or
  ~/.aws) is a documented compose comment, not the default.
- **Artifacts persist on a named volume** mounted at a path
  `TAGMANAGER_ARTIFACT_DIR` points to (default in-image `/data/
  artifacts`); generated lifecycle/tiering/report/proposal files survive
  container restarts and are retrievable via the web download or a
  volume mount. Dev sqlite likewise lands on a data volume so a restart
  keeps scans (compose default stays Postgres; the sqlite path is the
  bare-`docker run` story).
- **Healthcheck hits `/api/health`** (already returns `{"status":
  "ok"}`) with Python stdlib (urllib) — no curl in the slim image. App
  service gains its own healthcheck alongside the existing db one.
- **CLI is first-class in the image**: all three console scripts
  (`tagmanager-serve`, `tagmanager-storage-scan`, `aws-tag-manager`)
  install into the image; `docker compose exec app
  tagmanager-storage-scan ...` is a documented, tested-at-verify path.
  Parity on bare installs (`pip install .` → same scripts) documented in
  README/runbook.
- **Non-root runtime** — the image adds an unprivileged user and runs as
  it; the artifact/data dir is owned by that user. Security hygiene, not
  a feature.
- **No app-code changes beyond the artifact-dir default** — packaging is
  Dockerfile/compose/pyproject/docs; the 212-test suite is untouched
  (this phase adds no Python behavior).
