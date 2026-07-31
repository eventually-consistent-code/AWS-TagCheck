"""
Purpose: Pricing tables for storage cost math — loads the checked-in
normalized snapshot and answers rate questions. Tiered classes (Standard's
50/500 TB ladder) are priced over ACCOUNT-AGGREGATE bytes; callers derive an
effective rate and allocate it to cells — never restart the ladder per cell.
Author(s): John Reed
"""

import json
import pathlib

# Constants

BYTES_PER_GB = 1024 ** 3
DATA_DIR = pathlib.Path(__file__).parent / "data"


class UnknownStorageClass(KeyError):
    """Raised when a storage class has no entry in the pricing snapshot."""


class PricingTable:
    """Rate lookups for one provider+region pricing snapshot."""

    def __init__(self, snapshot):
        """
        :param snapshot: parsed pricing snapshot dict
        """
        self.snapshot = snapshot
        self.provider = snapshot["provider"]
        self.region = snapshot["region"]
        self.as_of_date = snapshot["as_of_date"]
        self._classes = snapshot["classes"]

    def _class_entry(self, storage_class):
        """Fetch a class entry or raise UnknownStorageClass."""
        try:
            return self._classes[storage_class]
        except KeyError as err:
            raise UnknownStorageClass(storage_class) from err

    def known_class(self, storage_class):
        """
        Whether the snapshot prices this storage class.

        :param storage_class: API storage class string
        :returns: bool
        """
        return storage_class in self._classes

    def tiered_monthly_cost(self, storage_class, aggregate_bytes):
        """
        Monthly storage cost for the class over ACCOUNT-AGGREGATE bytes.

        Walks the tier ladder once across the aggregate — the only correct
        way to apply Standard's 50/500 TB breaks.

        :param storage_class: API storage class string
        :param aggregate_bytes: total bytes in this class across the run
        :returns: monthly USD cost (float)
        """
        entry = self._class_entry(storage_class)
        gbs = aggregate_bytes / BYTES_PER_GB

        if "tier_ranges_gb" not in entry:
            return gbs * entry["rate_per_gb_month"]

        cost = 0.0
        for lower, upper, rate in entry["tier_ranges_gb"]:
            if gbs <= lower:
                break
            span = (gbs - lower) if upper is None else min(gbs, upper) - lower
            cost += span * rate
        return cost

    def effective_rate(self, storage_class, aggregate_bytes):
        """
        Aggregate-derived $/GB-month for allocating cost to cells.

        :param storage_class: API storage class string
        :param aggregate_bytes: total bytes in this class across the run
        :returns: USD per GB-month (float)
        """
        if aggregate_bytes <= 0:
            entry = self._class_entry(storage_class)
            if "tier_ranges_gb" in entry:
                return entry["tier_ranges_gb"][0][2]
            return entry["rate_per_gb_month"]
        cost = self.tiered_monthly_cost(storage_class, aggregate_bytes)
        return cost / (aggregate_bytes / BYTES_PER_GB)

    def flat_rate(self, storage_class):
        """
        Non-tiered $/GB-month for a class (first-tier rate when tiered).

        :param storage_class: API storage class string
        :returns: USD per GB-month (float)
        """
        return self.effective_rate(storage_class, 0)

    def min_duration_days(self, storage_class):
        """Minimum billed storage duration in days for the class."""
        return self._class_entry(storage_class)["min_duration_days"]

    def min_billable_bytes(self, storage_class):
        """Per-object billable floor in bytes (0 = none) for the class."""
        return self._class_entry(storage_class)["min_billable_bytes"]

    def retrieval_per_gb(self, storage_class):
        """Standard-speed retrieval cost per GB for the class."""
        return self._class_entry(storage_class)["retrieval_per_gb"]

    def transition_fee(self, dest_class, object_count):
        """
        One-time lifecycle transition cost into dest_class.

        :param dest_class: destination storage class
        :param object_count: objects transitioning
        :returns: USD (float)
        """
        per_1000 = self._class_entry(dest_class)["transition_in_per_1000"]
        if per_1000 is None:
            return 0.0
        return object_count / 1000.0 * per_1000

    def monitoring_fee(self, object_count):
        """
        Intelligent-Tiering monthly monitoring cost for object_count objects.

        :param object_count: monitored objects (sub-floor objects excluded
            by the caller — AWS neither monitors nor tiers them)
        :returns: USD per month (float)
        """
        per_1000 = self.snapshot["intelligent_tiering"][
            "monitoring_per_1000_objects_month"]
        return object_count / 1000.0 * per_1000

    def intelligent_tiering_rate(self, tier):
        """$/GB-month for a named Intelligent-Tiering access tier."""
        return self.snapshot["intelligent_tiering"]["tier_rates"][tier]

    def archive_overhead(self):
        """
        Split per-object archive overhead.

        :returns: (standard_billed_bytes, archive_billed_bytes)
        """
        over = self.snapshot["archive_overhead"]
        return over["standard_billed_bytes"], over["archive_billed_bytes"]


def load_pricing(provider="s3", region="us-east-1"):
    """
    Load the checked-in pricing snapshot for a provider+region.

    :param provider: backend name
    :param region: region the snapshot was captured for
    :returns: PricingTable
    :raises FileNotFoundError: no snapshot shipped for that combination
    """
    path = DATA_DIR / f"{provider}_pricing.json"
    with open(path, encoding="utf-8") as handle:
        snapshot = json.load(handle)
    if snapshot["region"] != region:
        raise FileNotFoundError(
            f"snapshot at {path} covers {snapshot['region']}, not {region} — "
            "run pricing_refresh for that region")
    return PricingTable(snapshot)
