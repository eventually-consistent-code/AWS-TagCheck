"""
Purpose: Tests for pricing tables (tier ladders, aggregate math), the
snapshot refresh parser, the cost report, and the report-only CLI mode.
Author(s): John Reed
"""

import csv
import datetime
from types import SimpleNamespace

import pytest

from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.storage import cli, pricing_refresh
from tagmanager.storage.base import StorageObject
from tagmanager.storage.cost import build_cost_report
from tagmanager.storage.pricing import (BYTES_PER_GB, UnknownStorageClass,
                                        load_pricing)
from tagmanager.storage.rollup import RollupBuilder
from tagmanager.storage.store import persist_rollups

TB = 1024 * BYTES_PER_GB


def _stat(container="bkt", prefix="p", sclass="STANDARD", band="<90d",
          count=1, total_bytes=BYTES_PER_GB):
    """Duck-typed stand-in for a StoragePrefixStat row."""
    return SimpleNamespace(container=container, prefix=prefix,
                           storage_class=sclass, age_band=band,
                           object_count=count, total_bytes=total_bytes)


def test_tiered_cost_walks_the_ladder():
    """60 TB Standard crosses the 50 TB break: 50*0.023 + 10*0.022 per GB."""
    table = load_pricing()
    cost = table.tiered_monthly_cost("STANDARD", 60 * TB)
    expected = 50 * 1024 * 0.023 + 10 * 1024 * 0.022
    assert cost == pytest.approx(expected)


def test_flat_class_ignores_ladder():
    """Standard-IA is a flat rate regardless of volume."""
    table = load_pricing()
    assert table.tiered_monthly_cost("STANDARD_IA", 100 * TB) == pytest.approx(
        100 * 1024 * 0.0125)


def test_effective_rate_blends_tiers():
    """Effective rate at 60 TB sits strictly between the two tier rates."""
    table = load_pricing()
    rate = table.effective_rate("STANDARD", 60 * TB)
    assert 0.022 < rate < 0.023


def test_unknown_class_raises():
    """Unmapped storage class is an explicit error, not a silent zero."""
    table = load_pricing()
    with pytest.raises(UnknownStorageClass):
        table.tiered_monthly_cost("REDUCED_REDUNDANCY", BYTES_PER_GB)


def test_cost_report_aggregate_equals_tiered_total():
    """Checker finding 1: many cells summing past 50 TB must equal the
    account-tiered total, not a per-cell restarted ladder."""
    table = load_pricing()
    cells = [_stat(prefix=f"p{i}", total_bytes=6 * TB) for i in range(10)]

    report = build_cost_report(cells, table)

    expected = table.tiered_monthly_cost("STANDARD", 60 * TB)
    assert report.total_monthly_cost == pytest.approx(expected)
    naive = 10 * table.tiered_monthly_cost("STANDARD", 6 * TB)
    assert report.total_monthly_cost < naive


def test_cost_report_bands_and_unknown():
    """Band totals split correctly; unknown classes surface, not crash."""
    table = load_pricing()
    cells = [
        _stat(band="<90d", total_bytes=10 * BYTES_PER_GB),
        _stat(prefix="q", band=">365d", sclass="GLACIER",
              total_bytes=100 * BYTES_PER_GB),
        _stat(prefix="r", sclass="MYSTERY_CLASS"),
    ]
    report = build_cost_report(cells, table)

    assert report.band_totals["<90d"] == pytest.approx(10 * 0.023)
    assert report.band_totals[">365d"] == pytest.approx(100 * 0.0036)
    assert report.unknown_classes == ["MYSTERY_CLASS"]
    assert len(report.rows) == 2


def test_refresh_parser_flattens_offer():
    """SKU->terms->priceDimensions join produces sorted rate ladders."""
    offer = {
        "products": {
            "SKU1": {"productFamily": "Storage",
                     "attributes": {"volumeType": "Standard"}},
            "SKU2": {"productFamily": "Storage",
                     "attributes": {"volumeType": "Glacier Deep Archive"}},
            "SKU3": {"productFamily": "API Request",
                     "attributes": {"volumeType": "Standard"}},
        },
        "terms": {"OnDemand": {
            "SKU1": {"T1": {"priceDimensions": {
                "D1": {"beginRange": "51200", "endRange": "512000",
                       "unit": "GB-Mo", "pricePerUnit": {"USD": "0.022"}},
                "D2": {"beginRange": "0", "endRange": "51200",
                       "unit": "GB-Mo", "pricePerUnit": {"USD": "0.023"}},
            }}},
            "SKU2": {"T2": {"priceDimensions": {
                "D3": {"beginRange": "0", "endRange": "Inf",
                       "unit": "GB-Mo", "pricePerUnit": {"USD": "0.00099"}},
            }}},
        }},
    }
    ladders = pricing_refresh.extract_storage_rates(offer)

    assert ladders["STANDARD"] == [[0.0, 51200.0, 0.023],
                                   [51200.0, 512000.0, 0.022]]
    assert ladders["DEEP_ARCHIVE"] == [[0.0, None, 0.00099]]
    assert "API Request" not in str(ladders)


def test_refresh_keeps_missing_classes():
    """A class absent from the bulk file keeps its shipped rate (warn only)."""
    snapshot = {"classes": {
        "DEEP_ARCHIVE": {"rate_per_gb_month": 0.00099},
        "STANDARD": {"tier_ranges_gb": [[0, None, 0.023]]},
    }}
    changes = pricing_refresh.apply_rates(
        snapshot, {"STANDARD": [[0.0, None, 0.025]]})

    assert snapshot["classes"]["DEEP_ARCHIVE"]["rate_per_gb_month"] == 0.00099
    assert snapshot["classes"]["STANDARD"]["rate_per_gb_month"] == 0.025
    assert changes == ["STANDARD: [[0, None, 0.023]] -> 0.025"]


def test_cli_cost_report_without_rescan(tmp_path, monkeypatch, capsys):
    """--cost-report alone prices the latest persisted run — no scan."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    engine = get_engine(f"sqlite:///{tmp_path / 'scan.db'}")
    create_all(engine)
    session = session_factory(engine)()

    builder = RollupBuilder(age_band_days=[90, 365])
    builder.add(StorageObject(
        backend="s3", container="bkt", key="old/dump.tar",
        size_bytes=10 * BYTES_PER_GB,
        last_modified=datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=500)))
    persist_rollups(session, builder, backend="s3")
    session.commit()

    cost_csv = tmp_path / "cost.csv"
    rc = cli.main(["--cost-report", "--cost-csv", str(cost_csv)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "estimate — list pricing" in out
    with open(cost_csv, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["age_band"] == ">365d"
    assert float(rows[0]["monthly_cost_usd"]) == pytest.approx(10 * 0.023)


def test_cli_no_args_is_config_error(tmp_path, monkeypatch):
    """Neither --bucket nor --cost-report -> exit 4."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'x.db'}")
    assert cli.main([]) == 4


def test_cli_cost_report_needs_a_run(tmp_path, monkeypatch):
    """--cost-report with an empty DB -> exit 4 with guidance."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'empty.db'}")
    assert cli.main(["--cost-report"]) == 4
