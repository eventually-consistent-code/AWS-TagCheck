"""
Purpose: Structure recommendation engine — read a scan run's rollup cells
and say how the storage SHOULD be laid out: date-split cold-heavy active
prefixes, straight lifecycle rules for dead ones, compaction before any
tiering of small-object swarms, hot/cold zone splits for mixed prefixes.
Grounded in lifecycle-rules-are-prefix-scoped; no ML, just thresholds.
Author(s): John Reed
"""

from dataclasses import dataclass, field

from tagmanager.storage.cost import aggregate_class_bytes
from tagmanager.storage.pricing import BYTES_PER_GB
from tagmanager.storage.rollup import band_labels

# Constants — the dials, named so they're arguable.

COLD_SHARE_THRESHOLD = 0.70
SMALL_OBJECT_SHARE_THRESHOLD = 0.50
MIXED_BAND_MIN_SHARE = 0.20
MAX_PERSISTED_RECS = 50
TOP_OWNERS_SHOWN = 3

OUT_OF_SCOPE_NOTES = [
    "data-type grouping: out of scope — rollups carry no content-type",
    "request-rate fan-out and churn/expiry advice: out of scope — scans "
    "carry no request or write telemetry",
]


@dataclass
class Recommendation:
    """One per-prefix layout recommendation."""

    kind: str
    container: str
    prefix: str
    rationale: str
    monthly_cost_at_stake: float = 0.0
    top_owners: list = field(default_factory=list)


@dataclass
class _PrefixSignals:  # pylint: disable=too-many-instance-attributes
    """Aggregated signals for one (container, prefix)."""

    total_bytes: int = 0
    cold_bytes: int = 0
    fresh_bytes: int = 0
    object_count: int = 0
    cold_object_count: int = 0
    small_object_count: int = 0
    classes: set = field(default_factory=set)
    band_bytes: dict = field(default_factory=dict)
    owner_bytes: dict = field(default_factory=dict)


def _collect_signals(stats, fresh_label):
    """
    Fold stat rows into per-(container, prefix) signal blocks.

    :param stats: StoragePrefixStat rows
    :param fresh_label: the first band's label
    :returns: dict of (container, prefix) -> _PrefixSignals
    """
    signals = {}
    for stat in stats:
        sig = signals.setdefault((stat.container, stat.prefix),
                                 _PrefixSignals())
        sig.total_bytes += stat.total_bytes
        sig.object_count += stat.object_count
        sig.classes.add(stat.storage_class)
        sig.band_bytes[stat.age_band] = (
            sig.band_bytes.get(stat.age_band, 0) + stat.total_bytes)
        owner = getattr(stat, "owner", "") or ""
        if owner:
            sig.owner_bytes[owner] = (
                sig.owner_bytes.get(owner, 0) + stat.total_bytes)
        if stat.age_band == fresh_label:
            sig.fresh_bytes += stat.total_bytes
        else:
            sig.cold_bytes += stat.total_bytes
            sig.cold_object_count += stat.object_count
            sig.small_object_count += stat.small_object_count
    return signals


def _cold_rate(sig, rates):
    """Blended $/GB-mo across the prefix's classes (crude, attribution only)."""
    if not rates:
        return 0.0
    class_rates = [rates.get(sclass) for sclass in sig.classes
                   if rates.get(sclass) is not None]
    if not class_rates:
        return 0.0
    return sum(class_rates) / len(class_rates)


def _recommend_for_prefix(sig, access_aware):
    """
    Pick at most ONE recommendation kind for a prefix's signals.

    Precedence: compact-first beats any transition advice (tiering tiny
    objects loses money), then date-split / straight-lifecycle by
    activity, then zone-split for mixes.

    :param sig: _PrefixSignals
    :param access_aware: whether the run's ages include read activity
    :returns: (kind, rationale) or None
    """
    if sig.total_bytes == 0 or sig.cold_bytes == 0:
        return None
    cold_share = sig.cold_bytes / sig.total_bytes
    activity_word = "activity" if access_aware else "writes"

    if (sig.cold_object_count
            and sig.small_object_count / sig.cold_object_count
            > SMALL_OBJECT_SHARE_THRESHOLD):
        return ("compact-first",
                f"{sig.small_object_count} of {sig.cold_object_count} cold "
                "objects are under 128 KiB — compact/tar before ANY tiering; "
                "transition floors and per-object overhead make tiering "
                "tiny objects cost money")

    if cold_share > COLD_SHARE_THRESHOLD and sig.fresh_bytes > 0:
        return ("date-split",
                f"{cold_share:.0%} of bytes are cold but fresh "
                f"{activity_word} continue — split into date partitions "
                "(prefix/year/month/) so a prefix-scoped lifecycle rule can "
                "age out old partitions without touching the hot tail")

    if cold_share >= 1.0:
        return ("straight-lifecycle",
                "prefix is entirely cold with no fresh "
                f"{activity_word} — no reorg needed, apply a lifecycle "
                "rule directly (--emit-lifecycle)")

    significant_bands = [band for band, size in sig.band_bytes.items()
                         if sig.total_bytes
                         and size / sig.total_bytes >= MIXED_BAND_MIN_SHARE]
    if len(sig.classes) > 1 or len(significant_bands) >= 3:
        return ("zone-split",
                "prefix mixes storage classes/ages at one level "
                f"(classes: {', '.join(sorted(sig.classes))}) — split into "
                "hot/cold zones so each zone carries exactly one lifecycle "
                "rule; rules are prefix-scoped and cannot treat a mix")

    return None


def _effective_rates(stats, pricing):
    """
    Class -> effective $/GB-mo for $-at-stake attribution; {} sans pricing.

    :param stats: StoragePrefixStat rows
    :param pricing: PricingTable or None
    :returns: dict
    """
    if pricing is None:
        return {}
    return {sclass: pricing.effective_rate(sclass, size)
            for sclass, size in aggregate_class_bytes(stats, pricing).items()}


def build_recommendations(stats, age_band_days, pricing=None,
                          access_aware=False):
    """
    Recommendations for one run, keyed per prefix, priciest first.

    Owner slices aggregate into attribution (top_owners) — one prefix
    never yields two recommendations.

    :param stats: StoragePrefixStat rows
    :param age_band_days: run thresholds
    :param pricing: optional PricingTable for $-at-stake attribution
    :param access_aware: run-level access-aware flag
    :returns: (recommendations list, notes list)
    """
    fresh_label = band_labels(age_band_days)[0]
    signals = _collect_signals(stats, fresh_label)
    rates = _effective_rates(stats, pricing)

    recs = []
    for (container, prefix), sig in signals.items():
        picked = _recommend_for_prefix(sig, access_aware)
        if picked is None:
            continue
        kind, rationale = picked
        owners = sorted(sig.owner_bytes.items(), key=lambda kv: -kv[1])
        recs.append(Recommendation(
            kind=kind,
            container=container,
            prefix=prefix,
            rationale=rationale,
            monthly_cost_at_stake=(sig.cold_bytes / BYTES_PER_GB
                                   * _cold_rate(sig, rates)),
            top_owners=[owner for owner, _ in owners[:TOP_OWNERS_SHOWN]],
        ))

    recs.sort(key=lambda rec: -rec.monthly_cost_at_stake)
    return recs, list(OUT_OF_SCOPE_NOTES)


def recs_to_json(recs):
    """
    Serializable form for the run row, capped at MAX_PERSISTED_RECS.

    :param recs: Recommendation list (already sorted priciest-first)
    :returns: list of dicts; a truncation marker ends the list when capped
    """
    payload = [{
        "kind": rec.kind, "container": rec.container, "prefix": rec.prefix,
        "rationale": rec.rationale,
        "monthly_cost_at_stake": round(rec.monthly_cost_at_stake, 6),
        "top_owners": rec.top_owners,
    } for rec in recs[:MAX_PERSISTED_RECS]]
    if len(recs) > MAX_PERSISTED_RECS:
        payload.append({"kind": "truncated",
                        "note": f"{len(recs) - MAX_PERSISTED_RECS} more "
                                "recommendations not persisted"})
    return payload
