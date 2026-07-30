---
scope: review-feat-csv-gold-s3
verdict: findings
created: 2026-07-30
---
# Audit: review-feat-csv-gold-s3

## finding — important
CSV fetch/parse runs after the scan — bad input wastes the full region sweep
issue: 10

aws_tag_check.py:main — build_gold_list() is called after scan_all_regions(). Scenario: run with --csv pointing at a missing file or unreadable s3:// key → every region is scanned (minutes of API calls), then SystemExit(EXIT_CONFIG) fires before write_html_report — scan wasted, no report. Fix: fetch/parse the CSV before the scan (fail fast), merge after.

## finding — important
S3 failure paths untested
issue: 11

upload_artifacts() returning False on ClientError, and main()'s clean-scan-with-failed-upload → EXIT_CONFIG contract, have no tests. tests/test_s3_and_singlepass.py covers happy paths only.

## finding — minor
Empty CSV tag_value overwrites AWS value with empty string

aws.py:_parse_csv_rows keeps rows with empty value; merge_tag_maps then prefers the CSV "" over a real AWS value (conflict entry is emitted, so it is reviewable). Decide: skip empty values or treat as explicit clear.

## finding — minor
Report S3 key and report header compute date.today() separately

aws_tag_check.py — render_html_report and upload_artifacts each call datetime.date.today(); a run crossing midnight gets a key dated differently from the header. Compute once in main and pass down.

## finding — minor
conflicts.json path hardcoded while --gold-output is configurable

build_gold_list writes conflicts.json to CWD unconditionally when --write-gold is set; asymmetric with --gold-output.

## finding — minor
.mcp.json committed with machine-absolute path

.mcp.json points at /Users/jsreed/repos/cairn2/server/dist/index.js — breaks other checkouts, leaks local username. Consider gitignoring or a relative/npx invocation. No secrets in diff.

## finding — minor
Axes clarity: no findings; security: no findings beyond .mcp.json note

clarity — clean. security — HTML escapes via html.escape, JSON via json.dump, no injection surface, no credentials in diff. correctness beyond issue 10 — clean. Recorded so silence ≠ unchecked.
