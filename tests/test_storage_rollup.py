"""
Purpose: Tests for the storage rollup engine — age banding, prefix
truncation, streaming aggregates, bounded samples, and persistence.
Author(s): John Reed
"""

import datetime

import pytest

from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import StoragePrefixStat, StorageScanRun
from tagmanager.storage.base import StorageObject
from tagmanager.storage.rollup import (RollupBuilder, band_labels,
                                       classify_age, prefix_at_depth)
from tagmanager.storage.store import latest_complete_run, persist_rollups

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)


def _obj(key, days_old, size=100, container="bkt", storage_class="STANDARD"):
    """Build a StorageObject aged `days_old` days before NOW."""
    return StorageObject(
        backend="s3",
        container=container,
        key=key,
        size_bytes=size,
        last_modified=NOW - datetime.timedelta(days=days_old),
        storage_class=storage_class,
    )


def test_band_labels_default():
    """Two thresholds make three labeled bands."""
    assert band_labels([90, 365]) == ["<90d", "90-365d", ">365d"]


def test_band_labels_reject_unsorted():
    """Descending thresholds are a config error."""
    with pytest.raises(ValueError):
        band_labels([365, 90])


def test_classify_age_bands():
    """Ages fall into the expected band on each side of the thresholds."""
    bands = [90, 365]
    assert classify_age(NOW - datetime.timedelta(days=10), NOW, bands) == "<90d"
    assert classify_age(NOW - datetime.timedelta(days=200), NOW, bands) == "90-365d"
    assert classify_age(NOW - datetime.timedelta(days=400), NOW, bands) == ">365d"


def test_prefix_at_depth():
    """Prefixes truncate to depth; rootless keys roll up to empty."""
    assert prefix_at_depth("logs/2024/06/app.log", 2) == "logs/2024"
    assert prefix_at_depth("logs/app.log", 2) == "logs"
    assert prefix_at_depth("app.log", 2) == ""


def test_builder_aggregates_cells():
    """Objects land in distinct (prefix, class, band) cells with sums."""
    builder = RollupBuilder(age_band_days=[90, 365], now=NOW)
    builder.add(_obj("logs/2024/a.log", days_old=10, size=50))
    builder.add(_obj("logs/2024/b.log", days_old=20, size=70))
    builder.add(_obj("logs/2019/c.log", days_old=400, size=30, storage_class="GLACIER"))

    cells = builder.rollups()
    fresh = cells[("bkt", "logs/2024", "STANDARD", "<90d")]
    assert fresh.object_count == 2
    assert fresh.total_bytes == 120

    cold = cells[("bkt", "logs/2019", "GLACIER", ">365d")]
    assert cold.object_count == 1
    assert cold.oldest_last_modified == NOW - datetime.timedelta(days=400)

    assert builder.objects_seen == 3
    assert builder.bytes_seen == 150


def test_builder_samples_stay_bounded():
    """Top-N heaps keep the true largest and oldest, capped at sample_size."""
    builder = RollupBuilder(age_band_days=[90], sample_size=3, now=NOW)
    for i in range(50):
        builder.add(_obj(f"data/f{i}", days_old=i + 1, size=(i + 1) * 10))

    largest = builder.largest_objects()
    assert len(largest) == 3
    assert [o.size_bytes for o in largest] == [500, 490, 480]

    oldest = builder.oldest_objects()
    assert len(oldest) == 3
    assert [o.key for o in oldest] == ["data/f49", "data/f48", "data/f47"]


def test_builder_band_totals():
    """Band totals sum across containers and prefixes."""
    builder = RollupBuilder(age_band_days=[90], now=NOW)
    builder.add(_obj("a/x", days_old=5, size=10))
    builder.add(_obj("b/y", days_old=6, size=20, container="other"))
    builder.add(_obj("c/z", days_old=500, size=40))

    totals = builder.band_totals()
    assert totals["<90d"].object_count == 2
    assert totals["<90d"].total_bytes == 30
    assert totals[">90d"].total_bytes == 40


def test_persist_rollups_roundtrip():
    """Rollups land as one complete run plus stat rows; latest-run query finds it."""
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    session = session_factory(engine)()

    builder = RollupBuilder(age_band_days=[90, 365], now=NOW)
    builder.add(_obj("logs/2024/a.log", days_old=10, size=50))
    builder.add(_obj("logs/2019/c.log", days_old=400, size=30))

    run = persist_rollups(session, builder, backend="s3")
    session.commit()

    assert run.status == "complete"
    assert run.objects_seen == 2
    assert run.bytes_seen == 80
    assert run.age_band_days == [90, 365]

    stats = session.query(StoragePrefixStat).filter_by(scan_run_id=run.id).all()
    assert len(stats) == 2
    assert latest_complete_run(session, backend="s3").id == run.id


def test_persist_rollups_partial_on_skips():
    """A scan with skipped containers records status partial."""
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    session = session_factory(engine)()

    builder = RollupBuilder(age_band_days=[90], now=NOW)
    builder.add(_obj("a/x", days_old=5))

    run = persist_rollups(session, builder, backend="s3",
                          skips=[{"container": "denied", "error": "AccessDenied"}])
    session.commit()

    assert run.status == "partial"
    assert session.query(StorageScanRun).count() == 1
    assert run.skips[0]["container"] == "denied"
