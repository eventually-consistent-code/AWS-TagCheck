# Phase 2: EC2 compliance scan — Context

## Locked decisions

- **Scope:** Multi-region EC2 **Environment** and **Product** tag compliance vs `canonical.json` only. No HTML, PrettyTable, or `index.html` writes (phase 3).
- **Spine:** After phase 1 guards → load canonical → list/filter regions → scan all → log summary → exit `0` or `1`.
- **Pagination:** EC2 instances via `get_paginator("describe_instances")` only (no unbounded single call).
- **Tags:** Normalize `Tags` to a dict; keys/values case-sensitive (no lowercasing).
- **Violation grain:** **Per-tag rows** — one row per bad Environment or Product (both can fire on one instance).
- **Missing vs invalid:**
  - Key absent → `issue=missing`, `tag_value` = `"missing environment"` or `"missing product"` (legacy-friendly sentinels).
  - Key present, not in canonical → `issue=invalid`, `tag_value` = actual string (including empty string).
  - Compliant → no row.
- **Name display:** Use `Name` tag when present; else `"(no name)"`.
- **Instance states:** Scan all states **except** `terminated` (API filter). Include stopped/pending/etc.
- **Regions:** `list_ec2_regions` then exclude `BAD_REGIONS`. Keep `BAD_REGIONS` as belt-and-suspenders.
- **Region errors:** On `ClientError` (UnauthorizedOperation, AccessDenied, OptInRequired, etc.) **skip region**, `LOG.warning`, record skip, continue. Do **not** map skips to exit 1. If all regions skip, still exit `0` if no violations (log a loud summary of skips).
- **Exit codes:** `EXIT_TAG_VIOLATIONS` (1) iff `len(violations) > 0`; else `EXIT_OK` (0). Canonical missing/malformed → `EXIT_CONFIG` (4). Guards unchanged (2/3/4).
- **Canonical path:** CWD-relative `CON_FILE` (`canonical.json`); require keys `Environment` and `Product` as lists.
- **Module split:** Low-level EC2 iteration + pure tag evaluation in `aws.py`; load/scan orchestration + `main()` in `aws_tag_check.py`.
- **Style:** John Reed voice — Purpose/Author, `LOG`, chatty lowercase status with trailing `...`.

## Precedence

On conflict, this CONTEXT + PLAN win over tracker issue text — update issues if they drift.

## Out of scope (this phase)

- HTML report generation and empty-region polish (phase 3)
- Automated test suite / lint green as REQ-08 (phase 3) — light manual/unit checks during work are fine
- Multi-resource types, notifications, multi-account allowlists
