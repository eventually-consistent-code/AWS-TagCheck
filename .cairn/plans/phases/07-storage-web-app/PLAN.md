---
issues: [43, 44, 47]
---
# Phase 7: storage web app — Plan

Goal: the optimizer runs from a browser — configure targets, launch and
watch scans, read the analysis, download the artifacts — under the
TagManager brand.

No research fan-out: UI patterns (htmx polling, HX-Trigger done, BytesIO
zips) were researched and locked in phase 6; the branding inventory is a
15-file grep already in RESEARCH-adjacent notes below (standard depth,
no material unknowns).

Branding inventory (live surfaces): README.md, docs/technical-reference.md,
docs/runbook.md, pyproject.toml, Dockerfile, static_analysis.sh,
virtShell.sh, aws_tag_manager.py (title strings), .github/
copilot-instructions.md, tests pinning report titles
(test_html_report.py, test_scan_and_canonical.py, test_s3_and_singlepass.py).
Historical: milestone/trace archives, docs/superpowers — untouched.

## Tasks

### Issue #43 — scan control UI

1. Targets CRUD: /storage/targets list + add/edit forms (backend,
   account_url, buckets one-per-line, prefix, age bands, rollup-owner
   toggle, enabled), plain POST-redirect handlers writing StorageTarget
   rows; storage nav gains Targets/Jobs links. Template + route tests in
   the test_ui pattern.
2. Jobs: POST /storage/targets/{id}/scan → jobs.submit_scan against the
   app scheduler (overlap/disabled errors surface as page messages);
   /storage/jobs list (state, target, objects_seen, error, timestamps);
   GET /storage/jobs/{id}/progress fragment polled every 2s, HX-Trigger
   done on terminal states; POST /storage/jobs/{id}/cancel with the
   "cancelling at next batch boundary" notice. App gains scheduler on
   app.state (create_app accepts it; serve passes the built scheduler;
   tests pass a FakeScheduler). Tests: trigger→done via inline fake,
   overlap message, cancel flip, progress fragment terminal header.

### Issue #44 — insights UI + artifact downloads

3. Insights pages over services on the latest run (backend selector):
   /storage/cost (cost report table), /storage/savings (projections with
   NOT RECOMMENDED flags/caveats), /storage/recommendations (kinds,
   rationales, $-at-stake, owners). Age-basis label + estimate
   disclaimer on every page; fs backend shows the no-pricing message.
   Route tests incl. empty-state and fs cases.
4. Artifacts: POST /storage/runs/{id}/artifacts/{kind} for
   kind ∈ lifecycle|tiering|structure|report generating into
   settings.artifact_dir/run-<id>/<kind>/ via the emit services (typed
   errors → page messages); /storage/runs/{id} artifacts index from
   run.artifacts with per-kind download links; GET .../download zipping
   the recorded dir via BytesIO StreamingResponse
   (Content-Disposition attachment). Pages state that key-level
   manifests (delete/batch-copy/move) remain CLI, scan-time. Tests:
   generate→index→download roundtrip (zip opens, files present),
   unknown kind 404-ish message, artifact_dir setting honored.

### Issue #47 — TagManager rebrand

5. Naming sweep across the live inventory above: pyproject name +
   description (project "tagmanager"; keep the aws-tag-manager script
   alias, add a tagmanager-storage-scan entry if absent), classic report
   title → "TagManager — EC2 Tag Compliance", CLI --help/prog strings,
   shell banners, Dockerfile labels, README/docs headings and body
   references, copilot-instructions. Branding-pinned test assertions
   updated in the same commit (titles only — behavior untouched, full
   suite green). Grep gate: no live-surface hits for
   AWS-TagManager/AWS-TagCheck outside archives, the alias, and the
   module filename.

## Notes

- Task order 1 → 5; 1–2 (#43) before 3–4 (#44) because insights pages
  link from the jobs flow; rebrand last so new templates are born with
  the right name and the sweep is one pass.
- The phase-6 parity gate is NOT violated by task 5: behavior assertions
  stay untouched; only title/name strings move, and the diff is
  reviewable as exactly that.
