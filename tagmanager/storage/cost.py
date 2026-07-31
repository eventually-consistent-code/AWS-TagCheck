"""
Purpose: Cost report — price a scan run's rollup cells with the pricing
snapshot. Tiered classes are costed once over the run's aggregate bytes and
allocated to cells at the effective rate, so per-prefix numbers always sum
to the true account-level total.
Author(s): John Reed
"""

from dataclasses import dataclass

from tagmanager.storage.pricing import BYTES_PER_GB


@dataclass
class CostRow:
    """Monthly cost estimate for one rollup cell."""

    container: str
    prefix: str
    storage_class: str
    age_band: str
    object_count: int
    total_bytes: int
    monthly_cost: float


@dataclass
class CostReport:
    """One run's cost estimate: per-cell rows plus rollup totals."""

    rows: list
    total_monthly_cost: float
    band_totals: dict
    unknown_classes: list
    region: str
    as_of_date: str


def build_cost_report(stats, pricing):
    """
    Price every rollup cell of a run.

    :param stats: iterable of StoragePrefixStat (one scan run)
    :param pricing: PricingTable
    :returns: CostReport
    """
    stats = list(stats)

    # Aggregate bytes per class first — tier ladders apply account-wide.
    class_bytes = {}
    unknown = set()
    for stat in stats:
        if not pricing.known_class(stat.storage_class):
            unknown.add(stat.storage_class)
            continue
        class_bytes[stat.storage_class] = (
            class_bytes.get(stat.storage_class, 0) + stat.total_bytes)

    rates = {sclass: pricing.effective_rate(sclass, agg_bytes)
             for sclass, agg_bytes in class_bytes.items()}

    rows = []
    band_totals = {}
    total = 0.0
    for stat in stats:
        if stat.storage_class in unknown:
            continue
        cost = stat.total_bytes / BYTES_PER_GB * rates[stat.storage_class]
        rows.append(CostRow(
            container=stat.container,
            prefix=stat.prefix,
            storage_class=stat.storage_class,
            age_band=stat.age_band,
            object_count=stat.object_count,
            total_bytes=stat.total_bytes,
            monthly_cost=cost,
        ))
        band_totals[stat.age_band] = band_totals.get(stat.age_band, 0.0) + cost
        total += cost

    rows.sort(key=lambda row: -row.monthly_cost)
    return CostReport(
        rows=rows,
        total_monthly_cost=total,
        band_totals=band_totals,
        unknown_classes=sorted(unknown),
        region=pricing.region,
        as_of_date=pricing.as_of_date,
    )
