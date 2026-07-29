# AWS-TagCheck

## Vision

Modernize the legacy EC2 tag compliance checker (boto → boto3, Python 3, tests,
credential/account guards, report polish) while keeping the door open for
broader multi-resource coverage later. Milestone 1 ships a solid **EC2-only**
path with an **HTML report** — expand coverage in a follow-on milestone.

The tool enumerates EC2 instances across allowed regions, compares their
Environment and Product tags to a canonical list (canonical.json), and
emits a dated HTML deviation report (index.html) with remediation guidance
and links to canonical sources.

Collaboration: **vibe** (cairn drives; human steers).

## Requirements

- REQ-01: Packaging & entrypoint — installable console script and runnable module
- REQ-02: Use `boto3` for region and instance enumeration with paginators
- REQ-03: Credential validation — fail fast with clear messages on missing/invalid AWS credentials
- REQ-04: Account guard — refuse to run when the AWS account does not match AWS_TAGCHECK_EXPECTED_ACCOUNT
- REQ-05: EC2 tag compliance scan — Environment and Product tags checked against `canonical.json` across regions; canonical lists are case-sensitive
- REQ-06: HTML report — produce `index.html` (dated) with per-region tables and guidance, hide empty regions
- REQ-07: Report polish — remove empty headers, include optional guidance URL from AWS_TAGCHECK_GUIDANCE_URL
- REQ-08: Tests & lint — pytest coverage for core logic and linters passing on modified files

## Project files

- canonical.json — authoritative Environment/Product lists (repo root)
- index.html — generated report (output)
- .cairn/ — project plans, roadmap, and continuity artifacts

## Notes

- Exit codes: 0=OK, 1=violations, 2=credential failure, 3=account mismatch, 4=config error
- Tag checks remain case-sensitive to match existing canonical lists
