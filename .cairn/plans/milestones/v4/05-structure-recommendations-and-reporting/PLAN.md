---
issues: [29, 30]
depth: deep
---
# Phase 5: structure recommendations and reporting — Plan

Goal: close the milestone — tell the user how their storage SHOULD be laid
out (grounded recommendations with move plans), and put everything the
milestone computes on one report surface.

Plan-checker pass applied 2026-07-31: artifacts-metadata mechanism created
(was a blocker — nothing records emit metadata today), S3 owner fetch
(was silently empty), always-5-tuple cell key, per-prefix rec keying,
schema-guard coverage for every new column, rec size cap, move-plan run
semantics, rewrite collision handling, data-type grouping declared out.

## Tasks

### Issue #29 — structure recommendation engine

1. Owner + artifacts plumbing (foundations first):
   - Cell key becomes ALWAYS 5 elements — (container, prefix, class,
     band, owner) with owner "" when --rollup-owners is off. Explicitly
     update every unpacker: `band_totals` (rollup.py), `persist_rollups`
     (store.py), `write_csv` (cli.py). Additive `owner` column on
     StoragePrefixStat.
   - S3 owner actually fetched: `FetchOwner=True` on the paginator,
     `Owner.DisplayName or ID` mapped. Azure/GCS record "" — stated in
     --help and PROPOSAL.md, not hidden.
   - Additive `artifacts` JSON column on StorageScanRun; every _emit_* /
     emitter-report path in cli.py appends {kind, dir, counts} to the
     run row — the report's artifacts index reads this, never the
     filesystem.
   - `schema_current` extended to cover owner + artifacts (+
     structure_recs from task 3); roundtrip tests per column.
2. `tagmanager/storage/structure.py` — per-prefix signal extraction
   (cold-bytes share, fresh-ACTIVITY presence — bands are access-aware,
   rationale says "fresh activity", small-object count share, class mix,
   bimodality measured on band SHARES) and the four rule kinds from
   CONTEXT, each with rationale + cold-$ at stake (priced when the
   backend has a snapshot). Recommendations are KEYED PER PREFIX; owner
   slices aggregate into attribution ("top owners: ...") only — one
   prefix never yields two recommendations. Owner read defensively
   (getattr default ""). Data-type grouping is OUT (no content-type in
   rollups) and the output says so. Unit tests per rule +
   compact-first-beats-transition precedence + duplicate-prefix guard.
3. CLI `--recommend-structure` (report-only): console table + optional
   `--structure-csv`; `--emit-structure DIR` writes PROPOSAL.md
   (per-recommendation suggested layout + apply guidance + azure/gcs
   owner caveat + access-aware caveat). Recommendations persist on the
   run row as `structure_recs` JSON, capped at top-N by $ at stake
   (named constant, truncation noted in the JSON and output).
4. `--emit-move-plan DIR` (scan mode): MoveManifestEmitter constructed
   BEFORE the walk from the latest COMPLETE run's persisted recs (the
   in-progress run is still "running" — semantics stated in code
   comment). old-key,new-key CSV per flagged prefix: date-split injects
   year/month from last-modified at stream time; zone-split prefixes
   cold/. Idempotence: keys already matching the target layout are
   skipped; APPLY.md warns on target-prefix overlap and copy+delete
   semantics. Refusal when the latest run carries no recs points at
   --recommend-structure. Tests: rewrite correctness, collision skip,
   two-pass flow incl. the fresh-run-after-move-scan refusal.

### Issue #30 — report integration

5. `tagmanager/storage/html_report.py` — standalone storage report
   (stdlib, html.escape on every dynamic value, classic report's visual
   family): age distribution, cost by band/class, per-option savings
   (break-even + caveats + NOT RECOMMENDED), structure recommendations,
   artifacts index (from the run's `artifacts` JSON), age-basis label +
   estimate disclaimer. CLI `--html-report PATH` in report-only mode,
   composing the same data objects the printers use. Tests mirror
   test_html_report.py (escaping, empty-run message, section presence,
   artifacts index from recorded metadata).
6. Web UI `/storage` page: ui_router-pattern route + storage.html —
   latest run summary (backend, bands, bytes, access-aware label), top
   cost cells (owner slices aggregated per prefix), recommendations
   table; nav link in base.html. The route catches missing-column
   OperationalError from stale dev DBs and renders a "storage schema
   out of date — delete dev DB and re-scan" notice instead of a 500.
   Tests: latest-run scoping, renders with zero storage runs, stale-
   schema notice.

## Notes

- Task order 1 → 6 strictly; task 1 is the plumbing every later task
  reads.
- REQ-11 coverage: access frequency = access-aware bands (phase 4);
  principal = opt-in owner dimension; data type = declared out of scope
  this milestone (no content-type signal in rollups).
