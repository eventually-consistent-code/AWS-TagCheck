# Phase 2: cost analysis engine — Context

## Locked decisions

- **Pricing source: checked-in normalized snapshot + optional no-auth
  refresh** from the AWS Price List Bulk per-region files (public, verified
  credential-free). Credentialed pricing APIs (GetProducts) are out —
  permanently. Snapshot schema is multi-cloud from day one
  (provider / region / storage_class / tier_ranges / $/GB-mo / fees /
  constraints / as_of_date); Azure Retail Prices + GCP Billing Catalog map
  into it in phase 4.
- **Snapshot ships us-east-1**; region is a first-class schema dimension
  (São Paulo runs +76% over us-east-1 — not a rounding error). More regions
  arrive via the refresh tool, not hand-editing.
- **Savings math models the real mechanics, not $/GB deltas**: transition
  request fees with break-even months, minimum storage durations (30/90/180d),
  128 KiB minimum billable size for IA/Glacier, ~40 KB/object Glacier
  metadata overhead, Intelligent-Tiering monitoring fee. Small-object-heavy
  prefixes where archiving LOSES money must be flagged, not averaged away.
- **RollupBuilder grows small-object tracking** (count below 128 KiB per
  cell) so the adjustments use real counts. StoragePrefixStat gains the
  additive column; dev sqlite DBs are throwaway — recreate, no migration
  framework this milestone.
- **Outputs are estimates from list pricing**, labeled as such — this is
  not a bill. Cost Explorer integration is out of scope.
- **Tiered pricing is account-aggregate, never per-cell** (plan-checker
  blocker): the Standard 50/500 TB ladder computes once over the run's
  aggregate bytes; cells get the aggregate-derived effective/marginal rate.
- **Band→class mapping keys on day VALUES from the run's `age_band_days`**,
  not band labels — bands are user-configurable, so a hardcoded label map
  would silently break on custom thresholds. Default map overridable via CLI.
- **Intelligent-Tiering projections exclude sub-128 KiB objects on both
  sides** (AWS neither monitors nor auto-tiers them); archive overhead is
  split-billed (8 KB Standard + 32 KB Glacier rate); retrieval caveats
  attach to every option that has one, including IA age-out.
