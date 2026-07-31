"""
Purpose: Cost report — price a scan run's rollup cells with the pricing
snapshot. Tiered classes are costed once over the run's aggregate bytes and
allocated to cells at the effective rate, so per-prefix numbers always sum
to the true account-level total.
Author(s): John Reed
"""

from dataclasses import dataclass

from tagmanager.storage.pricing import BYTES_PER_GB


def aggregate_class_bytes(stats, pricing):
    """
    Total bytes per priced storage class across a run's rows.

    :param stats: iterable of StoragePrefixStat-shaped rows
    :param pricing: PricingTable
    :returns: dict of storage class -> total bytes
    """
    agg = {}
    for stat in stats:
        if pricing.known_class(stat.storage_class):
            agg[stat.storage_class] = (
                agg.get(stat.storage_class, 0) + stat.total_bytes)
    return agg


def _merge_owner_slices(stats):
    """
    Collapse owner-keyed slices to one row per (container, prefix, class,
    band) — the cost report is a location view; owner attribution lives
    in the structure recommendations.

    :param stats: iterable of StoragePrefixStat-shaped rows
    :returns: list of merged duck-typed rows
    """
    merged = {}
    for stat in stats:
        key = (stat.container, stat.prefix, stat.storage_class, stat.age_band)
        row = merged.get(key)
        if row is None:
            merged[key] = _MergedStat(stat)
        else:
            row.object_count += stat.object_count
            row.total_bytes += stat.total_bytes
    return list(merged.values())


class _MergedStat:  # pylint: disable=too-few-public-methods
    """Mutable copy of one stat row for owner-slice merging."""

    def __init__(self, stat):
        self.container = stat.container
        self.prefix = stat.prefix
        self.storage_class = stat.storage_class
        self.age_band = stat.age_band
        self.object_count = stat.object_count
        self.total_bytes = stat.total_bytes


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
    stats = _merge_owner_slices(stats)

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
