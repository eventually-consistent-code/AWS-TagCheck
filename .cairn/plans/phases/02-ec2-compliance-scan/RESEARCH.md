# Phase 2 RESEARCH — EC2 tag compliance scan

**Depth:** standard  
**Scope:** REQ-05 / #8 — multi-region Environment + Product check vs `canonical.json`  
**Out of scope:** HTML / PrettyTable (phase 3), multi-resource types, lint suite endgame

## Inputs (post phase 1)

- `aws.py`: session, guards, `ec2_client`, `list_ec2_regions` (`AllRegions=False`), `check_data`, exit codes 0–4
- `aws_tag_check.py`: guards + region smoke; `BAD_REGIONS`, `CON_FILE`, `HTML_FILE`
- `canonical.json`: case-sensitive `Environment` / `Product` lists

## describe_instances

- Use `client.get_paginator("describe_instances")` — page → Reservations → Instances
- Tags: `[{Key, Value}]` or missing → normalize with `tags_to_dict`
- Never filter on `tag-key` for Environment/Product (would hide missing tags)
- Prefer excluding only `terminated` (or include pending/running/stopping/stopped)

## Violation shape (phase 3-ready)

Per-tag rows:

| Field | Notes |
|-------|--------|
| `region` | |
| `instance_id` | |
| `name` | Name tag or `(no name)` |
| `tag_key` | `Environment` or `Product` |
| `tag_value` | observed or legacy sentinel for missing |
| `issue` | `missing` \| `invalid` |

Missing sentinels: `"missing environment"` / `"missing product"` (legacy display parity).

## Regions

- Primary: `list_ec2_regions` / `AllRegions=False`
- Safety net: still filter `BAD_REGIONS`
- Per-region `ClientError` (Unauthorized, OptInRequired, …): **skip + warn**, continue; do not use exit 1 for skips

## Exit codes

- `0` — scan complete, zero violations
- `1` — any tag violation row
- `2`–`4` — unchanged guards / config (canonical load fail → 4)

## Module split

- `aws.py`: `iter_instances`, `tags_to_dict`, pure evaluate helpers, existing surface
- `aws_tag_check.py`: `load_canonical`, region loop, aggregation, `main()`, exit

## Risks

- Jenkins: document exit 1 vs 2–4
- Silent under-scan if many regions skipped — log skip summary
- Case sensitivity of canonical values — do not normalize
