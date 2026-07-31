---
issues: [21, 22]
depth: deep
---
# Phase 2: cost analysis engine — Plan

Goal: price what old data costs to keep, then project honest savings per
management option — transition fees, minimum durations, small-object
penalties included — on top of phase 1's rollups.

Plan-checker pass applied 2026-07-31: aggregate-level tier math (was a
per-cell correctness blocker), small-object bytes tracking, report-only CLI
mode, schema guard, INT small-object exclusion, day-keyed band mapping,
split Glacier overhead, per-option retrieval caveats.

## Tasks

### Issue #21 — pricing maps + stale-data cost report

1. `tagmanager/storage/pricing.py` + `tagmanager/storage/data/s3_pricing.json`
   — normalized snapshot (provider/region/storage_class/tier_ranges/
   $/GB-mo, monitoring + transition + retrieval + request fees, min
   duration days, **per-class** min billable bytes (IA classes + Glacier
   Instant only), **split** per-object archive overhead (8 KB
   Standard-billed + 32 KB Glacier-billed), as_of_date) loaded into a
   `PricingTable`. Tiered-rate math takes **aggregate bytes only**:
   `tiered_monthly_cost(class, aggregate_bytes)` + `effective_rate()` /
   `marginal_rate()` — the 50/500 TB ladder is account-level; per-cell
   costs use the aggregate-derived rate, never a restarted ladder.
   Tests: tier boundaries AND an aggregation test (many cells summing past
   50 TB == account-tiered total).
2. `tagmanager/storage/pricing_refresh.py` — regenerate the snapshot from
   the public Bulk per-region file (SKU→terms→priceDimensions flatten);
   `python -m tagmanager.storage.pricing_refresh --region us-east-1`.
   Network optional; parser tested against a checked-in fixture excerpt.
   Re-confirm the Deep Archive standalone SKU caveat here.
3. Cost report + report-only CLI path: `tagmanager/storage/cost.py`
   computes current monthly $ by container/prefix/class/age band + grand
   totals from a persisted run. `store.py` gains `stats_for_run(session,
   run_id)`. CLI splits modes: scan mode (`--bucket` required) vs
   `--cost-report` reading `latest_complete_run` — no forced rescan;
   `--bucket` only required when scanning. Console table + CSV; output
   labeled "estimate, list pricing, us-east-1".

### Issue #22 — savings projections per option

4. Small-object tracking through the whole pipe: `RollupStat` +
   `RollupBuilder.add` gain `small_object_count` AND `small_object_bytes`
   (< 128 KiB per cell); `StoragePrefixStat` columns, `persist_rollups`,
   `write_csv` header, and the roundtrip test all updated. Startup schema
   guard: PRAGMA table_info check on `storage_prefix_stats` → clean exit
   ("schema changed — delete dev DB and re-scan") instead of a late
   OperationalError; no migration framework (per CONTEXT).
5. `tagmanager/storage/projections.py` — per-option projector over stale
   cells: **delete** (full savings), **age-out** (band→class transitions:
   billable-floor math from real small-object bytes, one-time transition
   fees → break-even months, IA retrieval caveat), **intelligent tiering**
   (sub-128 KiB objects excluded from BOTH the monitoring fee and the
   savings — AWS neither charges nor tiers them), **archive** (Glacier
   Flexible / Deep Archive with split overhead priced at each class's
   rate + retrieval caveat). Band→class mapping derives from the run's
   `age_band_days` VALUES (default: ≥ first threshold → Standard-IA,
   ≥ last threshold → Glacier Flexible; Deep Archive offered when last
   threshold ≥ 365d), overridable via CLI. Options that lose money per
   cell → `not_recommended`, negative/zero savings never divide into
   break-even.
6. CLI `--project-savings`: options table (option × monthly/annual savings
   × break-even × caveats) console + CSV. Tests: billable-floor (N×4 KiB
   → N×128 KiB billable in IA), archive-loses-money synthetic cell
   asserting `not_recommended` and sign logic, end-to-end CLI run over a
   mixed rollup. Update README usage.

## Notes

- Task order = dependency order; 4 lands before 5.
- Break-even months = one-time transition fees / monthly savings — the
  headline honesty metric for age-out and archive options.
