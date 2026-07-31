"""
Purpose: Savings projections — for the stale slice of a scan run, project
what each management option (delete, age-out transitions, intelligent
tiering, archive) would honestly save: transition fees with break-even
months, billable floors from real small-object bytes, split archive
overhead, retrieval caveats. Options that lose money say so.
Author(s): John Reed
"""

from dataclasses import dataclass, field

from tagmanager.storage.pricing import BYTES_PER_GB
from tagmanager.storage.rollup import band_labels

# Constants

# Classes we project transitions FROM; colder classes are left alone.
TRANSITION_SOURCE_CLASSES = ("STANDARD", "INTELLIGENT_TIERING")
DEEP_ARCHIVE_MIN_THRESHOLD_DAYS = 365


@dataclass
class OptionProjection:
    """One management option's projected outcome over the stale slice."""

    option: str
    monthly_savings: float = 0.0
    annual_savings: float = 0.0
    one_time_cost: float = 0.0
    break_even_months: float = None
    not_recommended: bool = False
    caveats: list = field(default_factory=list)


def default_band_targets(age_band_days):
    """
    Map stale band labels to lifecycle target classes, keyed on DAY VALUES.

    Bands past the first threshold go to Standard-IA; the last band goes to
    Glacier Flexible. Labels come from the run's own thresholds, so custom
    --age-bands keep working.

    :param age_band_days: the run's ascending day thresholds
    :returns: dict of band label -> target storage class
    """
    labels = band_labels(age_band_days)
    targets = {}
    for label in labels[1:-1]:
        targets[label] = "STANDARD_IA"
    targets[labels[-1]] = "GLACIER"
    return targets


def _stale_cells(stats, age_band_days):
    """Cells past the first age threshold, transition-eligible classes only."""
    fresh_label = band_labels(age_band_days)[0]
    return [stat for stat in stats
            if stat.age_band != fresh_label
            and stat.storage_class in TRANSITION_SOURCE_CLASSES]


def _current_monthly(cells, rates):
    """Current monthly cost of the given cells at the run's effective rates."""
    return sum(cell.total_bytes / BYTES_PER_GB * rates[cell.storage_class]
               for cell in cells)


def _billable_bytes(cell, floor_bytes):
    """Bytes billed after a move into a class with a per-object floor."""
    if not floor_bytes:
        return cell.total_bytes
    return (cell.total_bytes - cell.small_object_bytes
            + cell.small_object_count * floor_bytes)


def _finalize(proj):
    """Fill annual/break-even/sign fields from the monthly numbers."""
    proj.annual_savings = proj.monthly_savings * 12
    if proj.monthly_savings > 0 and proj.one_time_cost > 0:
        proj.break_even_months = proj.one_time_cost / proj.monthly_savings
    if proj.monthly_savings <= 0:
        proj.not_recommended = True
        proj.break_even_months = None
        proj.caveats.append("costs more than it saves at current mix")
    return proj


def project_delete(cells, rates):
    """
    Full-deletion projection: every stale byte stops costing money.

    :param cells: stale cells
    :param rates: class -> effective $/GB-mo
    :returns: OptionProjection
    """
    proj = OptionProjection(
        option="delete",
        monthly_savings=_current_monthly(cells, rates),
        caveats=["irreversible — data is gone"],
    )
    return _finalize(proj)


def project_age_out(cells, rates, pricing, age_band_days):
    """
    Age-out transition projection with billable floors and break-even.

    :param cells: stale cells
    :param rates: class -> effective $/GB-mo
    :param pricing: PricingTable
    :param age_band_days: the run's thresholds (drives the target map)
    :returns: OptionProjection
    """
    targets = default_band_targets(age_band_days)
    proj = OptionProjection(option="age-out")
    durations = set()
    for cell in cells:
        target = targets.get(cell.age_band)
        if target is None:
            continue
        current = cell.total_bytes / BYTES_PER_GB * rates[cell.storage_class]
        floor = pricing.min_billable_bytes(target)
        new_cost = (_billable_bytes(cell, floor) / BYTES_PER_GB
                    * pricing.flat_rate(target))
        proj.monthly_savings += current - new_cost
        proj.one_time_cost += pricing.transition_fee(target, cell.object_count)
        durations.add(pricing.min_duration_days(target))
        retrieval = pricing.retrieval_per_gb(target)
        if retrieval:
            caveat = f"{target} retrieval ${retrieval}/GB"
            if caveat not in proj.caveats:
                proj.caveats.append(caveat)

    if durations:
        proj.caveats.append(
            f"minimum storage duration {max(durations)}d after transition")
    return _finalize(proj)


def project_intelligent_tiering(cells, rates, pricing):
    """
    Intelligent-Tiering projection — sub-floor objects excluded from BOTH
    the monitoring fee and the savings (AWS neither monitors nor tiers them).

    :param cells: stale cells
    :param rates: class -> effective $/GB-mo
    :param pricing: PricingTable
    :returns: OptionProjection
    """
    floor = pricing.snapshot["intelligent_tiering"]["small_object_floor_bytes"]
    ia_rate = pricing.intelligent_tiering_rate("infrequent_access")
    proj = OptionProjection(
        option="intelligent-tiering",
        caveats=["stale data assumed to settle in the infrequent tier",
                 f"objects <{floor // 1024} KiB stay at their current rate"])
    for cell in cells:
        if cell.storage_class != "STANDARD":
            continue
        rate = rates[cell.storage_class]
        eligible_bytes = cell.total_bytes - cell.small_object_bytes
        eligible_count = cell.object_count - cell.small_object_count
        current = eligible_bytes / BYTES_PER_GB * rate
        new_cost = (eligible_bytes / BYTES_PER_GB * ia_rate
                    + pricing.monitoring_fee(eligible_count))
        proj.monthly_savings += current - new_cost
        proj.one_time_cost += pricing.transition_fee(
            "INTELLIGENT_TIERING", eligible_count)
    return _finalize(proj)


def project_archive(cells, rates, pricing, age_band_days):
    """
    Archive projection — Glacier Flexible, Deep Archive for the oldest band
    when thresholds reach a year; split per-object overhead priced at each
    side's rate.

    :param cells: stale cells
    :param rates: class -> effective $/GB-mo
    :param pricing: PricingTable
    :param age_band_days: the run's thresholds
    :returns: OptionProjection
    """
    labels = band_labels(age_band_days)
    deep_ok = age_band_days[-1] >= DEEP_ARCHIVE_MIN_THRESHOLD_DAYS
    proj = OptionProjection(option="archive")
    durations = set()
    for cell in cells:
        target = ("DEEP_ARCHIVE" if deep_ok and cell.age_band == labels[-1]
                  else "GLACIER")
        current = cell.total_bytes / BYTES_PER_GB * rates[cell.storage_class]
        proj.monthly_savings += current - _archive_new_cost(cell, target, pricing)
        proj.one_time_cost += pricing.transition_fee(target, cell.object_count)
        durations.add(pricing.min_duration_days(target))
        caveat = (f"{target} retrieval "
                  f"${pricing.retrieval_per_gb(target)}/GB before use")
        if caveat not in proj.caveats:
            proj.caveats.append(caveat)

    if durations:
        proj.caveats.append(
            f"minimum storage duration {max(durations)}d after transition")
    overhead_kib = sum(pricing.archive_overhead()) // 1024
    proj.caveats.append("per-object metadata overhead included "
                        f"({overhead_kib} KiB/object)")
    return _finalize(proj)


def _archive_new_cost(cell, target, pricing):
    """
    Monthly cost of one cell after archiving, split overhead included —
    ~8 KiB billed at the Standard rate, ~32 KiB at the archive rate,
    per object.

    :param cell: rollup cell
    :param target: archive storage class
    :param pricing: PricingTable
    :returns: monthly USD (float)
    """
    std_overhead, arch_overhead = pricing.archive_overhead()
    overhead = cell.object_count * (
        arch_overhead / BYTES_PER_GB * pricing.flat_rate(target)
        + std_overhead / BYTES_PER_GB * pricing.flat_rate("STANDARD"))
    return cell.total_bytes / BYTES_PER_GB * pricing.flat_rate(target) + overhead


def project_options(stats, pricing, age_band_days):
    """
    Run every projector over one scan run's stats.

    :param stats: StoragePrefixStat rows for the run
    :param pricing: PricingTable
    :param age_band_days: the run's thresholds
    :returns: list of OptionProjection (delete, age-out, INT, archive)
    """
    stats = list(stats)

    class_bytes = {}
    for stat in stats:
        if pricing.known_class(stat.storage_class):
            class_bytes[stat.storage_class] = (
                class_bytes.get(stat.storage_class, 0) + stat.total_bytes)
    rates = {sclass: pricing.effective_rate(sclass, agg)
             for sclass, agg in class_bytes.items()}

    cells = _stale_cells(stats, age_band_days)
    return [
        project_delete(cells, rates),
        project_age_out(cells, rates, pricing, age_band_days),
        project_intelligent_tiering(cells, rates, pricing),
        project_archive(cells, rates, pricing, age_band_days),
    ]
