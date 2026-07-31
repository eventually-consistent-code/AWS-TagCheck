"""
Purpose: Savings projections — for the stale slice of a scan run, project
what each management option (delete, age-out transitions, intelligent
tiering, archive) would honestly save: marginal-rate savings, transition
fees with break-even months, billable floors from real small-object bytes,
split archive overhead on EVERY Glacier-bound move, retrieval caveats.
Options that lose money say so; options with nothing to act on say that too.
Author(s): John Reed
"""

from dataclasses import dataclass, field

from tagmanager.storage.cost import aggregate_class_bytes
from tagmanager.storage.pricing import BYTES_PER_GB
from tagmanager.storage.rollup import band_labels

# Constants

# Classes we project transitions FROM; colder classes are left alone.
TRANSITION_SOURCE_CLASSES = ("STANDARD", "INTELLIGENT_TIERING")
# AWS supports lifecycle transitions out of Intelligent-Tiering only into
# these destinations — never Standard-IA.
INT_ALLOWED_TARGETS = ("ONEZONE_IA", "GLACIER_IR", "GLACIER", "DEEP_ARCHIVE")
# Destinations that carry the split per-object metadata overhead.
ARCHIVE_CLASSES = ("GLACIER", "DEEP_ARCHIVE")
DEEP_ARCHIVE_MIN_THRESHOLD_DAYS = 365
SIZE_FILTER_CAVEAT = ("AWS default lifecycle excludes objects <128 KiB from "
                      "transitions — generated rules must set "
                      "ObjectSizeGreaterThan explicitly")


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


def default_band_targets(age_band_days, overrides=None):
    """
    Map stale band labels to lifecycle target classes, keyed on DAY VALUES.

    Bands past the first threshold go to Standard-IA; the last band goes to
    Glacier Flexible. Overrides are keyed on the threshold day value (the
    band's lower bound), so custom --age-bands keep working.

    :param age_band_days: the run's ascending day thresholds
    :param overrides: optional dict of threshold day (int) -> storage class
    :returns: dict of band label -> target storage class
    """
    labels = band_labels(age_band_days)
    targets = {}
    for label in labels[1:-1]:
        targets[label] = "STANDARD_IA"
    targets[labels[-1]] = "GLACIER"

    for day, sclass in (overrides or {}).items():
        try:
            index = list(age_band_days).index(day)
        except ValueError as err:
            raise ValueError(
                f"--age-out-map day {day} is not one of the run's "
                f"thresholds {list(age_band_days)}") from err
        targets[labels[index + 1]] = sclass
    return targets


def _stale_cells(stats, age_band_days, pricing):
    """Every priced cell past the first age threshold — all classes."""
    fresh_label = band_labels(age_band_days)[0]
    return [stat for stat in stats
            if stat.age_band != fresh_label
            and pricing.known_class(stat.storage_class)]


def _marginal_rates(stats, stale, pricing):
    """
    Per-class $/GB-mo actually saved when the stale bytes leave the class.

    Removing bytes comes off the TOP of the tier ladder, so the savings
    rate is marginal — tiered(agg) minus tiered(agg - stale) over the
    stale volume — not the blended effective rate.

    :param stats: all cells of the run
    :param stale: the stale subset
    :param pricing: PricingTable
    :returns: dict of storage class -> marginal $/GB-mo
    """
    agg = aggregate_class_bytes(stats, pricing)
    stale_bytes = {}
    for cell in stale:
        stale_bytes[cell.storage_class] = (
            stale_bytes.get(cell.storage_class, 0) + cell.total_bytes)

    rates = {}
    for sclass, agg_bytes in agg.items():
        removed = stale_bytes.get(sclass, 0)
        if removed <= 0:
            rates[sclass] = pricing.effective_rate(sclass, agg_bytes)
            continue
        saved = (pricing.tiered_monthly_cost(sclass, agg_bytes)
                 - pricing.tiered_monthly_cost(sclass, agg_bytes - removed))
        rates[sclass] = saved / (removed / BYTES_PER_GB)
    return rates


def _billable_bytes(cell, floor_bytes):
    """Bytes billed after a move into a class with a per-object floor."""
    if not floor_bytes:
        return cell.total_bytes
    return (cell.total_bytes - cell.small_object_bytes
            + cell.small_object_count * floor_bytes)


def _transition_new_cost(cell, target, pricing):
    """
    Monthly cost of one cell after transitioning to target — billable
    floor applied, and the split per-object metadata overhead added on
    every Glacier-bound move (~8 KiB at the Standard rate, ~32 KiB at the
    archive rate). The overhead is a property of the destination, not of
    which option proposed the move.

    :param cell: rollup cell
    :param target: destination storage class
    :param pricing: PricingTable
    :returns: monthly USD (float)
    """
    floor = pricing.min_billable_bytes(target)
    cost = (_billable_bytes(cell, floor) / BYTES_PER_GB
            * pricing.flat_rate(target))
    if target in ARCHIVE_CLASSES:
        std_overhead, arch_overhead = pricing.archive_overhead()
        cost += cell.object_count * (
            arch_overhead / BYTES_PER_GB * pricing.flat_rate(target)
            + std_overhead / BYTES_PER_GB * pricing.flat_rate("STANDARD"))
    return cost


def _finalize(proj):
    """Fill annual/break-even/sign fields from the monthly numbers."""
    if proj.monthly_savings == 0 and proj.one_time_cost == 0:
        proj.caveats = ["no eligible stale data"]
        return proj
    proj.annual_savings = proj.monthly_savings * 12
    if proj.monthly_savings > 0 and proj.one_time_cost > 0:
        proj.break_even_months = proj.one_time_cost / proj.monthly_savings
    if proj.monthly_savings <= 0:
        proj.not_recommended = True
        proj.break_even_months = None
        proj.caveats.append("costs more than it saves at current mix")
    return proj


def _add_retrieval_caveat(proj, target, pricing):
    """Append the target's retrieval-cost caveat once."""
    retrieval = pricing.retrieval_per_gb(target)
    if retrieval:
        caveat = f"{target} retrieval ${retrieval}/GB before use"
        if caveat not in proj.caveats:
            proj.caveats.append(caveat)


def project_delete(cells, rates):
    """
    Full-deletion projection: every stale byte stops costing money —
    regardless of storage class.

    :param cells: stale cells (all classes)
    :param rates: class -> marginal $/GB-mo
    :returns: OptionProjection
    """
    proj = OptionProjection(option="delete")
    for cell in cells:
        proj.monthly_savings += (cell.total_bytes / BYTES_PER_GB
                                 * rates[cell.storage_class])
    if proj.monthly_savings:
        proj.caveats.append("irreversible — data is gone")
    return _finalize(proj)


def project_age_out(cells, rates, pricing, age_band_days, band_targets=None):
    """
    Age-out transition projection with billable floors, archive overhead
    on Glacier-bound bands, and break-even months.

    :param cells: stale cells
    :param rates: class -> marginal $/GB-mo
    :param pricing: PricingTable
    :param age_band_days: the run's thresholds (drives the target map)
    :param band_targets: optional day-keyed override map (see
        default_band_targets)
    :returns: OptionProjection
    """
    targets = default_band_targets(age_band_days, overrides=band_targets)
    proj = OptionProjection(option="age-out")
    durations = set()
    for cell in cells:
        if cell.storage_class not in TRANSITION_SOURCE_CLASSES:
            continue
        target = targets.get(cell.age_band)
        if target is None:
            continue
        if (cell.storage_class == "INTELLIGENT_TIERING"
                and target not in INT_ALLOWED_TARGETS):
            continue
        current = cell.total_bytes / BYTES_PER_GB * rates[cell.storage_class]
        proj.monthly_savings += current - _transition_new_cost(
            cell, target, pricing)
        proj.one_time_cost += pricing.transition_fee(target, cell.object_count)
        durations.add(pricing.min_duration_days(target))
        _add_retrieval_caveat(proj, target, pricing)

    if durations:
        proj.caveats.append(
            f"minimum storage duration {max(durations)}d after transition")
        proj.caveats.append(SIZE_FILTER_CAVEAT)
    return _finalize(proj)


def project_intelligent_tiering(cells, rates, pricing):
    """
    Intelligent-Tiering projection — sub-floor objects excluded from BOTH
    the monitoring fee and the savings (AWS neither monitors nor tiers them).

    :param cells: stale cells
    :param rates: class -> marginal $/GB-mo
    :param pricing: PricingTable
    :returns: OptionProjection
    """
    floor = pricing.snapshot["intelligent_tiering"]["small_object_floor_bytes"]
    ia_rate = pricing.intelligent_tiering_rate("infrequent_access")
    proj = OptionProjection(option="intelligent-tiering")
    moved = False
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
        moved = True
    if moved:
        proj.caveats.extend([
            "stale data assumed to settle in the infrequent tier",
            f"objects <{floor // 1024} KiB stay at their current rate"])
    return _finalize(proj)


def project_archive(cells, rates, pricing, age_band_days):
    """
    Archive projection — Glacier Flexible, Deep Archive for the oldest band
    when thresholds reach a year; split per-object overhead priced at each
    side's rate.

    :param cells: stale cells
    :param rates: class -> marginal $/GB-mo
    :param pricing: PricingTable
    :param age_band_days: the run's thresholds
    :returns: OptionProjection
    """
    labels = band_labels(age_band_days)
    deep_ok = age_band_days[-1] >= DEEP_ARCHIVE_MIN_THRESHOLD_DAYS
    proj = OptionProjection(option="archive")
    durations = set()
    for cell in cells:
        if cell.storage_class not in TRANSITION_SOURCE_CLASSES:
            continue
        target = ("DEEP_ARCHIVE" if deep_ok and cell.age_band == labels[-1]
                  else "GLACIER")
        current = cell.total_bytes / BYTES_PER_GB * rates[cell.storage_class]
        proj.monthly_savings += current - _transition_new_cost(
            cell, target, pricing)
        proj.one_time_cost += pricing.transition_fee(target, cell.object_count)
        durations.add(pricing.min_duration_days(target))
        _add_retrieval_caveat(proj, target, pricing)

    if durations:
        proj.caveats.append(
            f"minimum storage duration {max(durations)}d after transition")
        overhead_kib = sum(pricing.archive_overhead()) // 1024
        proj.caveats.append("per-object metadata overhead included "
                            f"({overhead_kib} KiB/object)")
        proj.caveats.append(SIZE_FILTER_CAVEAT)
    return _finalize(proj)


def project_options(stats, pricing, age_band_days, band_targets=None):
    """
    Run every projector over one scan run's stats.

    :param stats: StoragePrefixStat rows for the run
    :param pricing: PricingTable
    :param age_band_days: the run's thresholds
    :param band_targets: optional day-keyed age-out target overrides
    :returns: list of OptionProjection (delete, age-out, INT, archive)
    """
    stats = list(stats)
    cells = _stale_cells(stats, age_band_days, pricing)
    rates = _marginal_rates(stats, cells, pricing)

    return [
        project_delete(cells, rates),
        project_age_out(cells, rates, pricing, age_band_days,
                        band_targets=band_targets),
        project_intelligent_tiering(cells, rates, pricing),
        project_archive(cells, rates, pricing, age_band_days),
    ]
