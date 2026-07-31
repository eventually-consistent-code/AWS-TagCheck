# Phase 7: storage web app — Verification

Verified: 2026-07-31

## Goal-backward check

Phase promise: the optimizer runs from a browser — configure targets,
launch and watch scans, read the analysis, download the artifacts —
under the TagManager brand.

Live end-to-end exercise on the REAL APScheduler (not the test fake) and
a real filesystem walk: created an fs target through the web form,
triggered a scan from the button, watched the progress fragment until
the HX-Trigger done header fired (job executed on the scheduler's
storage-executor thread), saw the finished job on the jobs page,
confirmed the fs cost page's honest no-pricing message, generated
report + structure artifacts from the run page, downloaded both zips
and verified contents (storage-report.html, PROPOSAL.md), and swept
rendered pages for old-brand strings — none.

Locked decisions honored: phase-6 rails only (services + jobs, no new
frameworks), researched progress pattern verbatim (2s poll, done
trigger, honest cancel notice), run-derived artifact kinds only with
key-level manifests stated as CLI-side, auth inherited from the global
middleware, errors as page messages (unknown kind, download-before-
generate, overlap, schedulerless deployments — all tested), rebrand
boundary exactly as drawn (alias + module filename kept, env vars
untouched as API surface, branding-pinned title assertions updated
in-commit with behavior untouched).

## Gates

- Tests: 212 passed, 0 failed (10 new this phase).
- Lint: `./static_analysis.sh` exit 0.
- `plan_drift`: transient closed-unverified flags on 43/44/47 normalize
  with this file. Open issues in phase: none. TDD frontmatter: none.
- Ledger: three issues with commit ranges (454caef..860a46b,
  860a46b..0aadb4b, 0aadb4b..df32a6f).
- Rebrand grep gate re-confirmed at verification: zero live-surface
  old-name hits outside archives and the compatibility alias.

## Result

PASS.

## Deviations

- Cloud-backend web scans (s3/azure/gcs) verified through the service
  layer's existing mock coverage; the live exercise used fs — the one
  backend fully drivable without credentials. Same code path from the
  trigger down (jobs → run_storage_scan → provider).
- The run.html download link derives its kind from the recorded entry's
  prefix ("structure-proposal" → "structure") — cosmetic coupling noted
  for phase-8 polish if it ever grows more kinds.
