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
MIXED_TYPE_MIN_SHARE = 0.20
MAX_PERSISTED_RECS = 50
TOP_OWNERS_SHOWN = 3
TOP_TYPES_SHOWN = 3

REQUEST_RATE_NOTE = (
    "request-rate fan-out and churn/expiry advice: out of scope — scans "
    "carry no request or write telemetry")
NO_TYPES_NOTE = (
    "data-type grouping: available only when the scan used --rollup-types")


@dataclass
class Recommendation:
    """One per-prefix layout recommendation."""

    kind: str
    container: str
    prefix: str
    rationale: str
    monthly_cost_at_stake: float = 0.0
    top_owners: list = field(default_factory=list)
    top_types: list = field(default_factory=list)


@dataclass
class _PrefixSignals:  # pylint: disable=too-many-instance-attributes
    """Aggregated signals for one (container, prefix)."""

    total_bytes: int = 0
    cold_bytes: int = 0
    fresh_bytes: int = 0
    fresh_count: int = 0
    object_count: int = 0
    cold_object_count: int = 0
    small_object_count: int = 0
    classes: set = field(default_factory=set)
    band_bytes: dict = field(default_factory=dict)
    owner_bytes: dict = field(default_factory=dict)
    type_bytes: dict = field(default_factory=dict)
    cold_type_bytes: dict = field(default_factory=dict)
    fresh_band_label: str = ""


def out_of_scope_notes(types_recorded):
    """
    The out-of-scope honesty notes for a run.

    The data-type note retires when the scan actually recorded types
    (--rollup-types) — the gap closed — and otherwise says how to get it.

    :param types_recorded: whether any cell carried a data type
    :returns: list of note strings
    """
    notes = [REQUEST_RATE_NOTE]
    if not types_recorded:
        notes.insert(0, NO_TYPES_NOTE)
    return notes


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
        sig.fresh_band_label = fresh_label
        sig.total_bytes += stat.total_bytes
        sig.object_count += stat.object_count
        sig.classes.add(stat.storage_class)
        sig.band_bytes[stat.age_band] = (
            sig.band_bytes.get(stat.age_band, 0) + stat.total_bytes)
        owner = getattr(stat, "owner", "") or ""
        if owner:
            sig.owner_bytes[owner] = (
                sig.owner_bytes.get(owner, 0) + stat.total_bytes)
        data_type = getattr(stat, "data_type", "") or ""
        if data_type:
            sig.type_bytes[data_type] = (
                sig.type_bytes.get(data_type, 0) + stat.total_bytes)
        if stat.age_band == fresh_label:
            sig.fresh_bytes += stat.total_bytes
            sig.fresh_count += stat.object_count
        else:
            sig.cold_bytes += stat.total_bytes
            sig.cold_object_count += stat.object_count
            sig.small_object_count += stat.small_object_count
            if data_type:
                sig.cold_type_bytes[data_type] = (
                    sig.cold_type_bytes.get(data_type, 0) + stat.total_bytes)
    return signals


def _dominant_cold_type(sig):
    """The largest-by-bytes cold data type, or '' when none recorded."""
    if not sig.cold_type_bytes:
        return ""
    return max(sig.cold_type_bytes.items(), key=lambda kv: kv[1])[0]


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

    dominant = _dominant_cold_type(sig)
    type_hint = f" (mostly {dominant})" if dominant else ""

    if (sig.cold_object_count
            and sig.small_object_count / sig.cold_object_count
            > SMALL_OBJECT_SHARE_THRESHOLD):
        return ("compact-first",
                f"{sig.small_object_count} of {sig.cold_object_count} cold "
                f"objects{type_hint} are under 128 KiB — compact/tar before "
                "ANY tiering; transition floors and per-object overhead make "
                "tiering tiny objects cost money")

    fresh_present = sig.fresh_bytes > 0 or sig.fresh_count > 0
    if cold_share > COLD_SHARE_THRESHOLD and fresh_present:
        return ("date-split",
                f"{cold_share:.0%} of bytes are cold but fresh "
                f"{activity_word} continue — split into date partitions "
                "(prefix/year/month/) so a prefix-scoped lifecycle rule can "
                "age out old partitions without touching the hot tail")

    if cold_share >= 1.0 and not fresh_present:
        return ("straight-lifecycle",
                "prefix is entirely cold with no fresh "
                f"{activity_word} — no reorg needed, apply a lifecycle "
                "rule directly (--emit-lifecycle)")

    # Strongly bimodal: meaningful bytes at BOTH temperature extremes —
    # the fresh band and the coldest band each past the share bar.
    fresh_share = sig.fresh_bytes / sig.total_bytes
    coldest_share = (max((size / sig.total_bytes
                          for band, size in sig.band_bytes.items()
                          if band != sig.fresh_band_label), default=0)
                     if sig.total_bytes else 0)
    bimodal = (fresh_share >= MIXED_BAND_MIN_SHARE
               and coldest_share >= MIXED_BAND_MIN_SHARE)
    if len(sig.classes) > 1 or bimodal:
        reason = (f"classes: {', '.join(sorted(sig.classes))}"
                  if len(sig.classes) > 1 else
                  f"{fresh_share:.0%} fresh alongside {coldest_share:.0%} "
                  "cold")
        return ("zone-split",
                f"prefix mixes ages/classes at one level ({reason}{type_hint})"
                " — split into hot/cold zones so each zone carries exactly "
                "one lifecycle rule; rules are prefix-scoped and cannot "
                "treat a mix")

    # type-split — LAST in precedence: nothing stronger fired.
    return _type_split(sig)


def _type_split(sig):
    """
    type-split when the prefix holds ≥2 data types each with a meaningful
    share — the residual niche after age/class splits don't apply.

    :param sig: _PrefixSignals
    :returns: (kind, rationale) or None
    """
    typed = {t: b for t, b in sig.type_bytes.items() if t}
    if len(typed) < 2 or not sig.total_bytes:
        return None
    big = [t for t, b in typed.items()
           if b / sig.total_bytes >= MIXED_TYPE_MIN_SHARE]
    if len(big) < 2:
        return None
    shares = ", ".join(f"{t} {typed[t] / sig.total_bytes:.0%}"
                       for t in sorted(big, key=lambda t: -typed[t]))
    return ("type-split",
            f"prefix mixes data types at one level ({shares}) — split by "
            "type (prefix/<type>/) so each type gets its own lifecycle "
            "policy and access controls")


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


def _build_one_rec(container, prefix, sig, access_aware, rates):
    """
    One Recommendation for a prefix's signals, or None when nothing fires.

    :returns: Recommendation or None
    """
    picked = _recommend_for_prefix(sig, access_aware)
    if picked is None:
        return None
    kind, rationale = picked
    owners = sorted(sig.owner_bytes.items(), key=lambda kv: -kv[1])
    types = sorted(sig.type_bytes.items(), key=lambda kv: -kv[1])
    return Recommendation(
        kind=kind, container=container, prefix=prefix, rationale=rationale,
        monthly_cost_at_stake=(sig.cold_bytes / BYTES_PER_GB
                               * _cold_rate(sig, rates)),
        top_owners=[owner for owner, _ in owners[:TOP_OWNERS_SHOWN]],
        top_types=[t for t, _ in types[:TOP_TYPES_SHOWN]])


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
    types_recorded = any(getattr(stat, "data_type", "") for stat in stats)

    recs = []
    for (container, prefix), sig in signals.items():
        rec = _build_one_rec(container, prefix, sig, access_aware, rates)
        if rec is not None:
            recs.append(rec)

    recs.sort(key=lambda rec: -rec.monthly_cost_at_stake)
    return recs, out_of_scope_notes(types_recorded)


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
        "top_types": rec.top_types,
    } for rec in recs[:MAX_PERSISTED_RECS]]
    if len(recs) > MAX_PERSISTED_RECS:
        payload.append({"kind": "truncated",
                        "note": f"{len(recs) - MAX_PERSISTED_RECS} more "
                                "recommendations not persisted"})
    return payload
