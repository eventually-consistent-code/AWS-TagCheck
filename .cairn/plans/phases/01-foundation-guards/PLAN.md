---
issues: []
---
# Phase 1: Foundation & guards — Plan

Goal: Add interactive CSV import to build a merged “gold” tag list (CSV + live AWS), with conflict flagging and an interactive CLI review. Then lay groundwork for S3 scanning and a tagging lexicon.

Acceptance criteria
- CLI accepts --csv <file> and parses/validates rows
- Merge algorithm produces a gold list combining CSV and AWS tags and flags conflicts (shows both values)
- Interactive review prompts let user accept/override/skip conflicts and persist the final gold list in-memory and optionally to disk
- Tests cover CSV parsing, merge/conflict logic, and the interactive flow (mocked)

Planned tasks
1. CSV import (adding-csv-import) — Add CLI flag, CSV parser, validation, in-memory tag model, and unit tests
2. Merge & conflict detection (merging-csv-aws-tags) — Implement merge strategy, store conflict records, and provide programmatic interfaces for review
3. Interactive conflict review (interactive-conflict-review) — CLI interactive flow to present conflicts and accept user resolutions
4. Persist/preview gold list — option to write gold-list.json and preview in terminal or HTML
5. S3 baseline (scanning-s3-buckets) — enumerate buckets, collect tags & object metadata, detect loose/unclassified data; output samples for lexicon authors
6. Tagging lexicon (creating-tagging-lexicon) — Author lexicon doc, mappings, and examples
7. S3 classification (classifying-s3-data) — Implement simple classifier and suggestions based on lexicon
8. Integrate into report (extending-html-report) — Add gold list and S3 sections to index.html
9. Tests & docs (adding-tests-for-csv-and-s3, updating-docs-and-plans) — pytest coverage and README/PLAN updates

Implementation notes
- Reuse aws.py helpers for AWS interactions; extend with S3 listing/tagging helpers
- CSV format: columns: resource_id, tag_key, tag_value; support per-resource multiple tags and optional header row
- Merge semantics: merge AWS and CSV tag maps per resource; when values differ, create a conflict entry with both CSV and AWS values
- Interactive CLI: use prompts (input()) and a non-tty fallback to a summary 'conflicts.json' for offline review
- Persistence: gold-list.json schema: { resource_id: { tag_key: tag_value, ... }, conflicts: [ {resource_id, tag_key, aws_value, csv_value} ] }

Risks & mitigations
- Large CSVs: stream-parse rows and support a --limit/test-mode; warn on huge inputs
- Permissions: S3 scans require ListBucket/ GetBucketTagging; document required IAM actions

Milestones & timeline
- Week 1: CSV import, merge logic, unit tests
- Week 2: Interactive review UI, persist gold list, update report
- Week 3: S3 scan baseline and lexicon drafting

References
- canonical.json (repo root) — canonical Environment/Product lists
- aws.py — existing AWS helpers to extend

<!-- tasks; frontmatter 'issues' lists the tracker ids this plan advances -->
