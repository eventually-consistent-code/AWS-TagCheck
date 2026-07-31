# Phase 2: cost analysis engine — Research

Researched: 2026-07-31 (deep fan-out: local AWS docs, live pricing feeds,
data-source strategy with live Bulk-API verification)

## Pricing data source — decision-grade finding

- **AWS Price List Bulk API is public, no credentials** — verified live with
  bare curl. Per-region S3 offer file ~471 KB
  (`https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/us-east-1/index.json`),
  full offer 12.5 MB, regenerated frequently (last-modified 3 days before
  research). Parse: `products` (SKU → attributes incl. storageClass) joined
  to `terms.OnDemand` → priceDimensions (beginRange/endRange/pricePerUnit).
- **GetProducts API buys nothing**: SigV4 credentials, region-locked
  endpoints, 100-item pagination, 5 req/s throttle, double-encoded JSON.
- **Prior art**: Infracost ships a normalized price store refreshed weekly
  from vendor files; Komiser's live-SDK approach shows the failure mode
  (missing/incorrect calcs). Azure Retail Prices API and GCP Billing
  Catalog are also public/no-auth — the normalized-snapshot schema extends
  to phase 4 clouds symmetrically.
- **Recommendation adopted**: checked-in snapshot (deterministic tests,
  offline use, price changes diffable in git) + optional refresh from the
  public bulk URLs.

## us-east-1 numbers (July 2026, cross-confirmed: awsstatic pricing feed +
## Price List offer file agreed on every overlapping value)

- Storage $/GB-mo: Standard 0.023/0.022/0.021 (0–50 TB / –500 TB / 500+ TB);
  Standard-IA 0.0125; One Zone-IA 0.010; Glacier Instant 0.004; Glacier
  Flexible 0.0036; Deep Archive 0.00099; Express One Zone 0.11.
  Intelligent-Tiering: FA = Standard tiers, IA 0.0125, Archive Instant
  0.004, Archive 0.0036, Deep Archive 0.00099.
- Intelligent-Tiering monitoring: **$0.0025 / 1,000 objects / month**.
- Lifecycle transition requests per 1,000 by destination: IA/OZ-IA/INT
  $0.01; Glacier Instant $0.02; Glacier Flexible $0.03; Deep Archive $0.05.
- Retrieval $/GB (standard speed): Glacier Instant 0.03; Glacier Flexible
  0.01 (bulk free); Deep Archive 0.02 (bulk 0.0025); IA classes 0.01.
- Requests per 1,000 (Standard): PUT $0.005, GET $0.0004.
- Regional variation is real: us-east-1 = eu-west-1 = $0.023 but Frankfurt
  +7%, Tokyo +9%, São Paulo +76% — region is a schema dimension, snapshot
  ships us-east-1 first.
- One caveat: standalone Deep Archive storage SKU was absent from the
  regional offer file (INT Deep-Archive-Access tier carries 0.00099 there);
  0.00099 corroborated by secondary sources — re-check at refresh-tool time.

## Savings-math constraints (savings ≠ $/GB delta)

Local docs mirror was overview-only; these are the standard documented
mechanics, encode as class metadata and re-confirm against live docs when
the refresh tool lands:

- Minimum storage durations: IA/OZ-IA 30d; Glacier Instant + Flexible 90d;
  Deep Archive 180d (early delete bills the remainder).
- Minimum billable object size 128 KiB for IA and Glacier classes — small
  objects save far less than the rate delta implies.
- Glacier per-object overhead ~8 KB Standard-billed + ~32 KB
  Glacier-billed metadata — archiving millions of tiny objects can COST
  money; the engine must surface this, not hide it.
- Transitions are a one-way waterfall (no lifecycle transition back up);
  transition request fees amortize against monthly savings — break-even
  months is the honest output.
- Intelligent-Tiering: 4 tiers (FA/IA auto, two archive tiers opt-in), no
  retrieval fee on auto tiers; monitoring fee makes it a loser for
  small-object-heavy prefixes.

## Gaps carried forward

- Rollup cells don't track small-object counts — phase-2 task extends
  RollupBuilder so the 128 KiB adjustments use real counts, not averages.
- Azure/GCS pricing enters the same snapshot schema in phase 4.
