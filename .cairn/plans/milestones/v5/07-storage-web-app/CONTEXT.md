# Phase 7: storage web app — Context

## Locked decisions

- **Everything rides the phase-6 rails**: routes live in the ui_router
  pattern under /storage/*, sync handlers, services called directly,
  jobs submitted via jobs.submit_scan against app.state's scheduler.
  No new frameworks, no JS build step — Jinja2 + the vendored htmx.
- **Progress UX is the researched pattern verbatim**: fragment endpoint
  polled with hx-trigger="every 2s"; on terminal job states the server
  sends HX-Trigger: done and the outer swap replaces the row — poller
  dies with the job. Cancel is a POST that flips cancel_requested;
  the UI says "cancelling at next batch boundary", honest about the
  cooperative semantics.
- **Web artifacts are run-derived kinds only** (lifecycle configs,
  tiering configs, structure proposal, HTML report) generated
  server-side into `settings.artifact_dir/run-<id>/<kind>/` and zipped
  on download via BytesIO + StreamingResponse. Scan-time key-level
  manifests (delete/batch-copy/move plans) are NOT web-triggerable this
  phase — jobs run without emit dirs; the pages say so and point at the
  CLI. New Settings field `artifact_dir` (default "artifacts").
- **Auth is inherited, not reimplemented**: the existing global OIDC
  middleware gates every new route; zero per-route auth code. Overlap
  refusals and service errors surface as visible page messages, never
  500s.
- **Rebrand boundary (issue #47)**: the PRODUCT is TagManager on every
  user surface — UI, report titles, README/docs, pyproject metadata,
  CLI help/banners, Dockerfile labels. The `aws-tag-manager` console
  entry point stays as a compatibility alias and the
  `aws_tag_manager.py` module keeps its filename (code identity, not
  brand). Historical artifacts (milestone archives, trace archives,
  docs/superpowers specs) stay untouched. Branding-pinned test
  assertions (report titles) update deliberately — the phase-6 parity
  gate froze BEHAVIOR; titles are brand, and the change is confined to
  title/name strings.
- **Insights pages are read-only views over services** on the latest
  run per backend (selector), each carrying the age-basis label and
  estimate disclaimer; recommend_structure's persist-on-read is
  idempotent and acceptable.
