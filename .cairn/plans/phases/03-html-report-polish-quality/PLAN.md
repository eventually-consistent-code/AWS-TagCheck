---
issues: [6, 3, 7]
depth: standard
---
# Phase 3: HTML report polish & quality — Plan

## Goal

Turn phase 2 violation rows into a dated `index.html` report with guidance,
omit empty-region chrome, drop stale org hardcodes, and ship pytest + lint
green on the active path.

## Produces

- HTML report writer (stdlib) writing `index.html` after successful scans
- Empty-region suppression + generic/configurable guidance copy
- `tests/` pytest suite (mocked AWS)
- Modernized static analysis (pycodestyle + pylint) green
- README for report path, tests, and lint

## Consumes

- Phase 2 violation list + `region_skips` + exit codes
- `HTML_FILE` / `CON_FILE` constants
- Existing `pylintrc`, `static_analysis.sh`, `tox.ini`

## Tasks

### T1 — HTML report core (REQ-06 → #6)

1. Add pure `render_html_report(violations, *, run_date, summary, guidance_url=None) -> str`.
2. Add `write_html_report(path, html)` (overwrite).
3. Group violations by `region`; build tables (Instance ID, Name, Tag, Value, Issue).
4. Wire into `main()` after scan: write report on clean and dirty exits; log
   `writing html report...` / `html report saved...`.
5. Do **not** write when guards/config fail before scan.

**Done when:** completed scan always produces `index.html`; tables list findings;
date + summary present.

### T2 — Polish empty regions + copy (REQ-07 → #3)

1. Only emit region section/table when that region has ≥1 violation.
2. Clean overall run: header + guidance + “all tags clean” (no empty tables).
3. Module-level guidance constants; optional `AWS_TAGCHECK_GUIDANCE_URL`.
4. Zero Confluence/contact/person hardcodes in report or README ops copy.

**Done when:** multi-region fixture with only one dirty region emits one table;
clean run has no region tables.

### T3 — Pytest suite (REQ-08 → #7)

1. Add `pytest` as optional/dev dependency (`[project.optional-dependencies] dev`
   and/or `requirements-dev.txt`).
2. `tests/`: evaluate_required_tags, check_data, load_canonical, guards
   (stubbed STS/env), scan_region skip, HTML render (grouping, escape, clean).
3. No live AWS in default suite; CI-friendly non-zero on failure.

**Done when:** `pytest` green locally with no credentials.

### T4 — Lint modernize green (REQ-08 → #7)

1. Replace `pep8` with `pycodestyle` in `static_analysis.sh` / `tox.ini`.
2. Exclude `.venv` (drop obsolete `aws` venv exclude or keep only if harmless);
   target `aws.py` + `aws_tag_check.py`.
3. Fix any pylint/pycodestyle findings on the active path.
4. Script exits non-zero on lint failure.

**Done when:** `./static_analysis.sh` (or documented equivalent) is green.

### T5 — Docs / TODO closeout

1. README: HTML written each successful scan; empty-region behavior; guidance URL
   env; how to run `pytest` and static analysis; exit codes unchanged.
2. Strike phase-3 TODOs (empty region headers, HTML report, tests/lint).

**Done when:** README matches behavior; no stale “phase 3 TODO” for shipped items.

## Order / dependencies

```
T1 → T2 → T3 → T4 → T5
```

T1/T2 both touch the report path (#6 then #3). T3/T4 are #7 quality gates.
Waves not used — sequential to avoid thrashing the same HTML module.

## Issue map

| Issue | Tasks |
|-------|--------|
| #6 REQ-06 HTML report | T1, (T5 docs) |
| #3 REQ-07 polish | T2, (T5 docs) |
| #7 REQ-08 tests + lint | T3, T4, (T5 docs) |

## Verification preview

- `index.html` after clean and dirty scans
- No empty region sections
- `pytest` green without AWS
- Lint green
- Exit codes still 0/1/2/3/4
