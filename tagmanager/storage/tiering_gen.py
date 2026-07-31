"""
Purpose: Intelligent-Tiering config generator — per-prefix archive-tier
opt-in configs from a scan run's stale rollups, minimums validated. Only
objects already IN the INTELLIGENT_TIERING class are affected; APPLY.md
says so, because that surprise wastes people's afternoons.
Author(s): John Reed
"""

import re

from tagmanager.storage.rollup import band_labels

# Constants

ARCHIVE_ACCESS_MIN_DAYS = 90
DEEP_ARCHIVE_ACCESS_MIN_DAYS = 180
ACCESS_TIER_MAX_DAYS = 730
MAX_CONFIGS_PER_BUCKET = 1000

TIERING_APPLY_NOTE = ("Intelligent-Tiering configs only affect objects "
                      "ALREADY in the INTELLIGENT_TIERING storage class — "
                      "objects land there at upload or via a lifecycle "
                      "transition, not via this config.")

# Classes whose stale prefixes benefit from an archive-tier opt-in.
ELIGIBLE_CLASSES = ("STANDARD", "INTELLIGENT_TIERING")


class TieringValidationError(ValueError):
    """Raised when a generated tiering config violates S3 constraints."""


def _config_id(prefix):
    """Readable, S3-legal config Id from a prefix."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", prefix or "root").strip("-")
    return f"tagmanager-{slug}-archive-tiers"


def build_tiering_configs(stats, age_band_days, archive_days=None,
                          deep_archive_days=None):
    """
    One Intelligent-Tiering config per stale eligible prefix, per bucket.

    :param stats: StoragePrefixStat rows (one run)
    :param age_band_days: run thresholds (drives staleness)
    :param archive_days: ARCHIVE_ACCESS days (default 90)
    :param deep_archive_days: DEEP_ARCHIVE_ACCESS days (default 180)
    :returns: (configs: {bucket: [config, ...]}, skips: [reasons])
    """
    archive_days = ARCHIVE_ACCESS_MIN_DAYS if archive_days is None else archive_days
    deep_archive_days = (DEEP_ARCHIVE_ACCESS_MIN_DAYS
                         if deep_archive_days is None else deep_archive_days)
    tierings = [
        {"Days": archive_days, "AccessTier": "ARCHIVE_ACCESS"},
        {"Days": deep_archive_days, "AccessTier": "DEEP_ARCHIVE_ACCESS"},
    ]

    fresh_label = band_labels(age_band_days)[0]
    configs = {}
    skips = []
    seen = set()
    for stat in stats:
        if stat.age_band == fresh_label:
            continue
        key = (stat.container, stat.prefix)
        if key in seen:
            continue
        seen.add(key)
        if stat.storage_class not in ELIGIBLE_CLASSES:
            skips.append(f"{stat.container}/{stat.prefix}: "
                         f"{stat.storage_class} gains nothing from "
                         "archive-tier opt-in")
            continue
        config = {
            "Id": _config_id(stat.prefix),
            "Status": "Enabled",
            "Filter": {"Prefix": f"{stat.prefix}/" if stat.prefix else ""},
            "Tierings": [dict(tier) for tier in tierings],
        }
        configs.setdefault(stat.container, []).append(config)

    for bucket, bucket_configs in configs.items():
        validate_tiering_configs(bucket, bucket_configs)
    return configs, skips


def validate_tiering_configs(bucket, configs):
    """
    Enforce Intelligent-Tiering constraints. Raises on violation.

    :param bucket: bucket name (messages)
    :param configs: list of config dicts for the bucket
    :raises TieringValidationError: any violated constraint
    """
    if len(configs) > MAX_CONFIGS_PER_BUCKET:
        raise TieringValidationError(
            f"{bucket}: {len(configs)} configs exceeds the per-bucket "
            f"limit of {MAX_CONFIGS_PER_BUCKET}")
    minimums = {"ARCHIVE_ACCESS": ARCHIVE_ACCESS_MIN_DAYS,
                "DEEP_ARCHIVE_ACCESS": DEEP_ARCHIVE_ACCESS_MIN_DAYS}
    for config in configs:
        for tier in config["Tierings"]:
            minimum = minimums[tier["AccessTier"]]
            if not minimum <= tier["Days"] <= ACCESS_TIER_MAX_DAYS:
                raise TieringValidationError(
                    f"{bucket}/{config['Id']}: {tier['AccessTier']} at "
                    f"{tier['Days']}d outside [{minimum}, "
                    f"{ACCESS_TIER_MAX_DAYS}]")
