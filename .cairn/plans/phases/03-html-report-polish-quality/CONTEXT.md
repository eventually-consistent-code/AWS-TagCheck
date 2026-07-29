# Phase 3: HTML report polish & quality — Context

## Locked decisions

- **HTML tech:** stdlib only (`html.escape` + tables). **No** PrettyTable / `PTable`. Runtime deps remain **boto3 only**.
- **Output path:** `HTML_FILE` → `index.html` (CWD-relative), overwrite each successful scan. Still gitignored; Jenkins/Apache publish stays external.
- **When written:** After scan aggregation completes — on both exit `0` (clean) and exit `1` (violations). **Do not** write on guard/config failures (`2`/`3`/`4`).
- **Empty regions (REQ-07):** Emit a region heading + table **only** if that region has ≥1 violation row. Never empty table chrome for clean or skipped regions.
- **Columns:** Instance ID, Name, Tag key, Tag value, Issue (1:1 from violation dict). Escape all dynamic strings.
- **Guidance copy:** Module constants with generic remediation steps. Optional env `AWS_TAGCHECK_GUIDANCE_URL` — if set, add one “more detail” link line; if unset, omit. **No** hard-coded Confluence URLs, people names, or org emails.
- **Region skips:** Optional compact summary in header/footer; not tables; still do not affect exit `1`.
- **Exit codes:** Unchanged (`0`/`1`/`2`/`3`/`4`).
- **Module split:** HTML render/write in `aws_tag_check.py` (pure helpers fine); keep AWS/tag eval in `aws.py`.
- **Tests (REQ-08):** `pytest` under `tests/`; mock AWS; cover tag evaluation, load_canonical, guards, scan skip, HTML grouping/escape. Dev dependency only.
- **Lint (REQ-08):** pylint + **pycodestyle** (not pep8 package); ignore `.venv`; green on `aws.py` + `aws_tag_check.py` (and tests if included). Update `static_analysis.sh` / `tox.ini` / `pylintrc` ignores.
- **Style:** John Reed voice — Purpose/Author, `LOG`, chatty status (`writing html report...` / `html report saved...`).

## Precedence

On conflict, this CONTEXT + PLAN win over tracker issue text — update issues if they drift.

## Out of scope (this phase / milestone)

- Multi-resource types, notifications, multi-account allowlists
- Replacing Jenkins/Apache publish path
- Live AWS required for default unit suite
