---
issues: [8]
depth: standard
---
# Phase 2: EC2 compliance scan — Plan

## Goal

After phase 1 guards, scan EC2 instances across accessible regions, compare
Environment and Product tags to `canonical.json`, collect structured
noncompliance rows, and exit `0` (clean) or `1` (any violation). No HTML.

## Produces

- Paginated EC2 instance enumeration helpers
- Canonical load + pure tag evaluation
- Multi-region scan with skip-on-region-error
- In-memory `violations` list (phase 3 HTML input shape)
- Exit code `1` when any violation

## Consumes

- Phase 1: session, STS/account guards, `list_ec2_regions`, `check_data`, exit codes
- `canonical.json`
- AWS read permissions for `ec2:DescribeInstances` / `DescribeRegions`

## Tasks

### T1 — Canonical load + pure comparison (REQ-05 → #8)

1. Add `load_canonical(path)` (in `aws_tag_check.py` or thin helper): `json.load`,
   require `Environment` and `Product` as lists; fail → LOG + `EXIT_CONFIG`.
2. Add pure evaluation (prefer `aws.py`): given tag map + canonical lists →
   list of `{tag_key, tag_value, issue}` for Environment/Product only.
3. Missing → sentinel + `issue=missing`; invalid → actual value + `issue=invalid`.

**Done when:** unit-testable without AWS; good tags empty; missing/invalid produce rows.

### T2 — Paginated instance helpers (`aws.py`)

1. `tags_to_dict(instance)` — `Tags` → `{Key: Value}` (empty if absent).
2. `iter_instances(session, region, filters=None)` — paginator
   `describe_instances`, yield instance dicts; default filter excludes
   `terminated` only.
3. Export via `__all__`.

**Done when:** paginator-only path; no single-shot unbounded `describe_instances`.

### T3 — Per-region scan

1. `scan_region(session, region, canonical)` → list of full violation dicts
   (`region`, `instance_id`, `name`, `tag_key`, `tag_value`, `issue`).
2. On `ClientError`: log warning, return empty violations for that region and
   a skip record (or raise a typed signal the orchestrator handles — either
   way main must not die).
3. Chatty status: `scanning {region}...` / `{region} Complete...`.

**Done when:** stubbed/mocked region returns expected rows; denied region does
not abort the process.

### T4 — Multi-region orchestration in `main()`

1. After guards: load canonical → `list_ec2_regions` → filter `BAD_REGIONS`.
2. Scan every region; aggregate `violations` and region skips.
3. Summary LOG: regions attempted, skips, violation count (and optional
   instance-touch count).
4. **No** HTML / PrettyTable / `open(HTML_FILE)`.

**Done when:** end-to-end path is scan-only; import still pure (read-only
canonical).

### T5 — Exit codes + README

1. `sys.exit(EXIT_TAG_VIOLATIONS if violations else EXIT_OK)`.
2. README: phase 2 scan behavior; exit `1` = tag violations; HTML still phase 3.
3. Update module docstrings / phase-1 “smoke only” comments.

**Done when:** clean tags → 0; any bad/missing tag → 1; guards still 2/3/4.

### T6 — Hygiene acceptance

1. Grep: no PrettyTable, no `index.html` write, no secrets, no legacy boto.
2. Live or stubbed run: multi-region scan completes; skip handling works.
3. Ready for phase 3 to consume the violation row shape.

**Done when:** checklist green; `/cairn:verify 2` ready after work.

## Order / dependencies

```
T1 → T2 → T3 → T4 → T5 → T6
```

Sequential (single issue #8 owns the full scan slice).

## Verification preview

- Violation matrix: missing / invalid / both tags / clean
- Exit 0 vs 1
- Region skip does not become exit 1
- No HTML side effects
