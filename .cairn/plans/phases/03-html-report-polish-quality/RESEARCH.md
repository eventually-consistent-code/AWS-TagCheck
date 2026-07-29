# Phase 3 RESEARCH — HTML report, polish & quality

**Depth:** standard  
**Scope:** REQ-06 (#6), REQ-07 (#3), REQ-08 (#7)  
**Out of scope:** multi-resource types, notifications, Jenkins/Apache publish (external)

## Inputs (post phase 2)

- Violation rows: `{region, instance_id, name, tag_key, tag_value, issue}`
- `region_skips` for logging only
- `HTML_FILE = "index.html"` constant; file gitignored
- Runtime deps: boto3 only; no PrettyTable; no tests yet
- Lint: `static_analysis.sh` uses legacy `pep8` and excludes old `./aws` venv name

## HTML approach

**Recommend stdlib** (`html.escape` + tables). No PrettyTable/`PTable`.

- Pure `render_html_report(...)` → string
- `write_html_report(path, html)` from `main()` only after successful scan
- Write on both clean (exit 0) and dirty (exit 1) runs — not on guard exits 2/3/4

## Report structure

1. Header: title, date, summary counts  
2. Guidance section (generic remediation; optional URL env)  
3. Per-region sections **only** when that region has ≥1 violation  
4. Clean run: header + guidance + “all tags clean” banner  
5. Optional compact list of skipped regions (no empty tables)

## Tests (pytest)

`tests/` covering evaluate tags, load_canonical, guards, scan skip, HTML grouping/escape. Mock AWS; no live account in default suite.

## Lint

`pep8` → `pycodestyle`; ignore `.venv`; target `aws.py` + `aws_tag_check.py`; pylint + pycodestyle green.

## Risks

- Jenkins: HTML write must not change exit-code meaning  
- Escape all dynamic tag/name values  
- Do not write HTML if guards fail early  
