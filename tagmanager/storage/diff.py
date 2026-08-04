"""
Purpose: Dry-run diff core — normalize and SET-diff two collections of S3
config rules (live vs what a scan run would generate), keyed by rule ID.
Pure and AWS-free: no boto3, no network, so the risky logic (what an apply
would DROP) is exhaustively unit-testable. S3's PutBucket* REPLACES a
bucket's entire config, so this is a whole-config set diff, never a line
diff — a live rule whose ID we don't generate would be dropped by an apply.
Author(s): John Reed
"""

from dataclasses import dataclass, field

# Constants

# Result buckets, in the order the CLI renders them.
STATUS_ADD = "would-add"
STATUS_REMOVE = "would-remove"
STATUS_CHANGE = "would-change"
STATUS_UNCHANGED = "unchanged"


@dataclass
class FetchResult:
    """
    Outcome of reading one live config subresource for a bucket.

    :ivar rules: the live rules (lifecycle) or configs (tiering); [] when
        none are present.
    :ivar present: whether a live config exists (False on a 404 / empty).
    :ivar unknown: True when the read was DENIED (403) — we cannot tell
        drift; never conflated with present=False.
    """

    rules: list = field(default_factory=list)
    present: bool = True
    unknown: bool = False


@dataclass
class RuleSetDiff:
    """One config kind's diff for one bucket, classified by rule ID."""

    would_add: list = field(default_factory=list)      # generated rules
    would_remove: list = field(default_factory=list)   # live rules
    would_change: list = field(default_factory=list)   # (generated, live)
    unchanged: list = field(default_factory=list)      # generated rules

    def has_changes(self):
        """True when an apply would add, drop, or rewrite any rule."""
        return bool(self.would_add or self.would_remove or self.would_change)


@dataclass
class BucketDiff:
    """Lifecycle + intelligent-tiering diff for one bucket."""

    bucket: str
    lifecycle: RuleSetDiff = None
    tiering: RuleSetDiff = None
    unknown_lifecycle: bool = False
    no_live_lifecycle: bool = False
    unknown_tiering: bool = False
    no_live_tiering: bool = False

    def has_changes(self):
        """True when either config kind would change under an apply."""
        return ((self.lifecycle is not None and self.lifecycle.has_changes())
                or (self.tiering is not None and self.tiering.has_changes()))


@dataclass
class ConfigDiff:
    """The whole dry-run diff — one BucketDiff per generated-for bucket."""

    buckets: list = field(default_factory=list)

    def has_changes(self):
        """True when any bucket would change under an apply."""
        return any(bucket.has_changes() for bucket in self.buckets)


def _effective_prefix(rule):
    """
    The canonical prefix of a rule, whichever shape AWS echoed it in.

    AWS may express a bare-prefix rule as rule-level ``Prefix`` (no
    ``Filter``), a collapsed ``Filter.Prefix``, or a full
    ``Filter.And.Prefix`` (what we generate). Whole-bucket rules appear as
    an absent filter, ``{}``, or ``Prefix: ""`` — all canonicalize to "".
    """
    prefix = rule.get("Prefix")
    if prefix is None:
        flt = rule.get("Filter") or {}
        prefix = flt.get("Prefix")
        if prefix is None:
            prefix = (flt.get("And") or {}).get("Prefix")
    return prefix or ""


def _object_size_gt(rule):
    """The rule's ObjectSizeGreaterThan floor, or None — either filter shape."""
    flt = rule.get("Filter") or {}
    size = flt.get("ObjectSizeGreaterThan")
    if size is None:
        size = (flt.get("And") or {}).get("ObjectSizeGreaterThan")
    return size


def _iso(value):
    """A datetime to a stable string for comparison, or None."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _transition_key(tran):
    """
    A comparable projection of one Transition (Days OR Date — never crash).

    Keeps the Date axis: a live Date-based transition has no Days and must
    read as DIFFERENT from a generated Days rule, not raise.
    """
    return {"days": tran.get("Days"), "date": _iso(tran.get("Date")),
            "storage_class": tran.get("StorageClass")}


def normalize_lifecycle_rule(rule):
    """
    Project a lifecycle rule onto the keys our generator emits, canonical.

    Compares Status, effective prefix + object-size floor, sorted
    Transitions, and Expiration (Days/Date only) — live-only extras
    (NoncurrentVersion*, AbortIncompleteMultipartUpload,
    ExpiredObjectDeleteMarker) are dropped so they never read as changed.

    :param rule: a raw lifecycle rule dict (live or generated)
    :returns: a hashable-by-equality normalized dict
    """
    expiration = rule.get("Expiration")
    return {
        "status": rule.get("Status"),
        "prefix": _effective_prefix(rule),
        "object_size_gt": _object_size_gt(rule),
        "transitions": sorted(
            (_transition_key(t) for t in rule.get("Transitions", [])),
            key=lambda t: (t["days"] if t["days"] is not None else -1,
                           t["storage_class"] or "")),
        "expiration": ({"days": expiration.get("Days"),
                        "date": _iso(expiration.get("Date"))}
                       if expiration else None),
    }


def normalize_tiering_config(config):
    """
    Project an intelligent-tiering config onto the generator-emitted keys.

    Compares Status, effective prefix, and sorted Tierings — the IT filter
    carries no object-size axis.

    :param config: a raw IT config dict (live or generated)
    :returns: a normalized dict
    """
    return {
        "status": config.get("Status"),
        "prefix": _effective_prefix(config),
        "tierings": sorted(
            ({"days": t.get("Days"), "tier": t.get("AccessTier")}
             for t in config.get("Tierings", [])),
            key=lambda t: (t["days"] if t["days"] is not None else -1,
                           t["tier"] or "")),
    }


def diff_rule_set(generated, live, id_key, normalize):
    """
    Set-diff two rule collections by ID into add / remove / change / same.

    A generated rule whose ID is absent live WOULD BE ADDED; a live rule
    whose ID we don't generate WOULD BE DROPPED by an apply (PutBucket*
    replaces the whole config); a shared ID whose normalized body differs
    WOULD BE REWRITTEN.

    :param generated: list of rule dicts we would apply
    :param live: list of live rule dicts
    :param id_key: the identity field ("ID" for lifecycle, "Id" for IT)
    :param normalize: the per-kind normalizer
    :returns: RuleSetDiff
    """
    gen_by_id = {rule[id_key]: rule for rule in generated}
    live_by_id = {rule[id_key]: rule for rule in live}
    diff = RuleSetDiff()
    for rid, grule in gen_by_id.items():
        lrule = live_by_id.get(rid)
        if lrule is None:
            diff.would_add.append(grule)
        elif normalize(grule) != normalize(lrule):
            diff.would_change.append((grule, lrule))
        else:
            diff.unchanged.append(grule)
    for rid, lrule in live_by_id.items():
        if rid not in gen_by_id:
            diff.would_remove.append(lrule)
    return diff


def diff_bucket(bucket, generated_lifecycle, live_lifecycle,
                generated_tiering, live_tiering):
    """
    Build the BucketDiff for one bucket from generated + live fetch results.

    :param bucket: bucket name
    :param generated_lifecycle: list of generated lifecycle rules
    :param live_lifecycle: FetchResult for live lifecycle
    :param generated_tiering: list of generated IT configs
    :param live_tiering: FetchResult for live IT
    :returns: BucketDiff
    """
    result = BucketDiff(bucket=bucket)
    if live_lifecycle.unknown:
        result.unknown_lifecycle = True
    else:
        result.no_live_lifecycle = not live_lifecycle.present
        result.lifecycle = diff_rule_set(
            generated_lifecycle, live_lifecycle.rules, "ID",
            normalize_lifecycle_rule)
    if live_tiering.unknown:
        result.unknown_tiering = True
    else:
        result.no_live_tiering = not live_tiering.present
        result.tiering = diff_rule_set(
            generated_tiering, live_tiering.rules, "Id",
            normalize_tiering_config)
    return result
