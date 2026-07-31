"""
Purpose: Streaming age-band rollups — fold an object stream into per-prefix
aggregates (count / bytes / oldest) plus bounded top-N largest and oldest
samples, without ever holding the full listing in memory.
Author(s): John Reed
"""

import datetime
import heapq
from dataclasses import dataclass


# Constants

DEFAULT_AGE_BAND_DAYS = [90, 365]
DEFAULT_PREFIX_DEPTH = 2
DEFAULT_SAMPLE_SIZE = 10
SMALL_OBJECT_FLOOR_BYTES = 131072


def band_labels(age_band_days):
    """
    Build human-readable band labels from day thresholds.

    [90, 365] -> ["<90d", "90-365d", ">365d"]

    :param age_band_days: ascending list of day thresholds
    :returns: list of band label strings, len(thresholds) + 1
    """
    if not age_band_days or sorted(age_band_days) != list(age_band_days):
        raise ValueError("age_band_days must be a non-empty ascending list")

    labels = [f"<{age_band_days[0]}d"]
    for lower, upper in zip(age_band_days, age_band_days[1:]):
        labels.append(f"{lower}-{upper}d")
    labels.append(f">{age_band_days[-1]}d")
    return labels


def classify_age(last_modified, now, age_band_days):
    """
    Place an object's last-modified time into an age band.

    :param last_modified: timezone-aware datetime of last modification
    :param now: timezone-aware datetime to measure age against
    :param age_band_days: ascending list of day thresholds
    :returns: band label string from band_labels()
    """
    labels = band_labels(age_band_days)
    age_days = (now - last_modified).total_seconds() / 86400.0

    for i, threshold in enumerate(age_band_days):
        if age_days < threshold:
            return labels[i]
    return labels[-1]


def prefix_at_depth(key, depth, delimiter="/"):
    """
    Truncate an object key's directory path to the first `depth` segments.

    "logs/2024/06/app.log" at depth 2 -> "logs/2024"; a key with no
    delimiter rolls up to "" (container root).

    :param key: object key
    :param depth: number of leading path segments to keep
    :param delimiter: path separator (default "/")
    :returns: prefix string
    """
    parts = key.split(delimiter)[:-1]
    return delimiter.join(parts[:depth])


@dataclass
class RollupStat:
    """Aggregate for one (container, prefix, storage_class, age_band) cell."""

    object_count: int = 0
    total_bytes: int = 0
    oldest_last_modified: datetime.datetime = None
    small_object_count: int = 0
    small_object_bytes: int = 0


class RollupBuilder:  # pylint: disable=too-many-instance-attributes
    """
    Fold StorageObjects into aggregates one at a time.

    Memory stays O(distinct rollup cells + sample size), never O(objects).
    """

    def __init__(self, age_band_days=None, prefix_depth=DEFAULT_PREFIX_DEPTH,
                 sample_size=DEFAULT_SAMPLE_SIZE, now=None,
                 rollup_owners=False):
        """
        :param age_band_days: ascending day thresholds (default [90, 365])
        :param prefix_depth: path segments to roll prefixes up to
        :param sample_size: how many largest/oldest objects to keep
        :param now: timezone-aware "now" for age math (default: UTC now)
        :param rollup_owners: key cells by object owner too (cardinality
            cost — every distinct owner splits a prefix's cells)
        """
        self.age_band_days = list(age_band_days or DEFAULT_AGE_BAND_DAYS)
        self.prefix_depth = prefix_depth
        self.sample_size = sample_size
        self.now = now or datetime.datetime.now(datetime.timezone.utc)
        self.rollup_owners = rollup_owners

        self.objects_seen = 0
        self.bytes_seen = 0
        self.access_aware_count = 0
        self._cells = {}
        self._largest = []
        self._oldest = []
        self._seq = 0

    @property
    def access_aware(self):
        """Whether any folded object carried a last-accessed timestamp."""
        return self.access_aware_count > 0

    def add(self, obj):
        """
        Fold one StorageObject into the rollups and samples.

        Age basis is the NEWEST of last-modified and last-accessed — a
        read-hot, never-edited object stays in the fresh band.

        :param obj: StorageObject
        """
        effective = obj.last_modified
        if obj.last_accessed is not None:
            self.access_aware_count += 1
            effective = max(effective, obj.last_accessed)
        band = classify_age(effective, self.now, self.age_band_days)
        prefix = prefix_at_depth(obj.key, self.prefix_depth)
        # Key is ALWAYS 5 elements — owner is "" when the dimension is
        # off, so every unpacker sees one stable shape.
        owner = obj.owner if self.rollup_owners else ""
        cell_key = (obj.container, prefix, obj.storage_class, band, owner)

        stat = self._cells.setdefault(cell_key, RollupStat())
        stat.object_count += 1
        stat.total_bytes += obj.size_bytes
        if obj.size_bytes < SMALL_OBJECT_FLOOR_BYTES:
            stat.small_object_count += 1
            stat.small_object_bytes += obj.size_bytes
        if (stat.oldest_last_modified is None
                or obj.last_modified < stat.oldest_last_modified):
            stat.oldest_last_modified = obj.last_modified

        self.objects_seen += 1
        self.bytes_seen += obj.size_bytes
        self._seq += 1

        # Bounded samples: min-heap on size keeps the N largest; min-heap on
        # negated timestamp keeps the N oldest (root = newest kept, evicted).
        largest_entry = (obj.size_bytes, self._seq, obj)
        oldest_entry = (-obj.last_modified.timestamp(), self._seq, obj)

        if len(self._largest) < self.sample_size:
            heapq.heappush(self._largest, largest_entry)
        else:
            heapq.heappushpop(self._largest, largest_entry)

        if len(self._oldest) < self.sample_size:
            heapq.heappush(self._oldest, oldest_entry)
        else:
            heapq.heappushpop(self._oldest, oldest_entry)

    def rollups(self):
        """
        All aggregate cells built so far.

        :returns: dict of (container, prefix, storage_class, band) -> RollupStat
        """
        return dict(self._cells)

    def largest_objects(self):
        """
        The largest objects seen, biggest first.

        :returns: list of StorageObject
        """
        return [entry[2] for entry in
                sorted(self._largest, key=lambda e: -e[0])]

    def oldest_objects(self):
        """
        The oldest objects seen, oldest first.

        :returns: list of StorageObject
        """
        return [entry[2] for entry in
                sorted(self._oldest, key=lambda e: -e[0])]

    def band_totals(self):
        """
        Totals per age band across every container and prefix.

        :returns: dict of band label -> RollupStat
        """
        totals = {}
        for (_, _, _, band, _), stat in self._cells.items():
            agg = totals.setdefault(band, RollupStat())
            agg.object_count += stat.object_count
            agg.total_bytes += stat.total_bytes
            if (agg.oldest_last_modified is None
                    or (stat.oldest_last_modified is not None
                        and stat.oldest_last_modified < agg.oldest_last_modified)):
                agg.oldest_last_modified = stat.oldest_last_modified
        return totals
