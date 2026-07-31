---
type: reference
provenanceFiles: [tagmanager/storage/pricing_refresh.py, tagmanager/storage/data/s3_pricing.json]
provenanceCommits: [9b1f7e8, 9b1f7e8]
created: 2026-07-31
confidence: medium
---
Cloud pricing source pattern (verified live, milestone 4): public no-credential bulk price files exist for all three clouds — AWS Price List per-region JSON (~471 KB, stable URLs at pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/<region>/index.json), Azure Retail Prices API, GCP Billing Catalog. Pattern: checked-in normalized snapshot (deterministic tests, offline use, price drift lands as reviewable git diffs) + optional refresh tool over the public files; credentialed pricing APIs (GetProducts) buy nothing — SigV4, throttled, double-encoded JSON. Snapshots carry as_of_date and honesty flags (GCS monthly derived from hourly ×730; Azure Cold soft-confirmed). fs backend has no pricing — outputs say so, never zero.
