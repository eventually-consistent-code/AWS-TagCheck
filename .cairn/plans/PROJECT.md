# AWS-TagCheck

## Vision

Modernize the legacy EC2 tag compliance checker (boto → boto3, Python 3, tests,
credential/account guards, report polish) while keeping the door open for
broader multi-resource coverage later. Milestone 1 ships a solid **EC2-only**
path with an **HTML report** — expand coverage in a follow-on milestone.

Today the tool pulls EC2 instance tags, compares them to a canonical
Environment/Product list, and writes an HTML deviation report (historically
published via Jenkins → Apache). We keep that purpose; we raise the floor on
runtime, safety, and maintainability.

Collaboration: **vibe** (cairn drives; human steers).

## Requirements

- REQ-01: Python 3 packaging and entrypoint — runnable module/CLI, modern deps
- REQ-02: Replace legacy `boto` with `boto3` for EC2 region/instance enumeration
- REQ-03: Credential validation — clear pass/fail when AWS credentials are missing or invalid
- REQ-04: Account guard — refuse to run (or hard-warn) when the active AWS account is not the expected account
- REQ-05: EC2 tag compliance scan — Environment and Product tags checked against `canonical.json` across regions (respect known inaccessible regions)
- REQ-06: HTML report — write deviation tables to `index.html` (or equivalent), dated, with guidance for remediating tags
- REQ-07: Report polish — suppress table headers/sections when a region has no bad data; refresh stale hard-coded contact/Confluence copy
- REQ-08: Tests and lint green — automated tests for core comparison/guards; pylint/pep8 (or project lint) clean on the new code path
