"""
Purpose: Tests for savings projections — billable floors from real
small-object bytes, INT small-object exclusion, archive-loses-money sign
logic, break-even math, and the --project-savings CLI end-to-end.
Author(s): John Reed
"""

import csv
import datetime
from types import SimpleNamespace

import pytest

from tagmanager.storage import cli
from tagmanager.storage.base import StorageObject
from tagmanager.storage.pricing import BYTES_PER_GB, load_pricing
from tagmanager.storage.projections import (default_band_targets,
                                            project_options)

BANDS = [90, 365]
KIB = 1024
FLOOR = 128 * KIB


def _cell(band="90-365d", sclass="STANDARD", count=1, total_bytes=BYTES_PER_GB,
          small_count=0, small_bytes=0, prefix="p"):
    """Duck-typed StoragePrefixStat row."""
    return SimpleNamespace(container="bkt", prefix=prefix,
                           storage_class=sclass, age_band=band,
                           object_count=count, total_bytes=total_bytes,
                           small_object_count=small_count,
                           small_object_bytes=small_bytes)


def _by_option(projections):
    return {proj.option: proj for proj in projections}


def test_default_band_targets_key_on_day_values():
    """Custom thresholds still map: middle bands -> IA, last -> Glacier."""
    assert default_band_targets([30, 180, 700]) == {
        "30-180d": "STANDARD_IA", "180-700d": "STANDARD_IA",
        ">700d": "GLACIER"}


def test_delete_saves_full_stale_cost():
    """Delete option equals the stale slice's current monthly cost."""
    pricing = load_pricing()
    cells = [_cell(total_bytes=100 * BYTES_PER_GB),
             _cell(band="<90d", prefix="fresh", total_bytes=999 * BYTES_PER_GB)]
    delete = _by_option(project_options(cells, pricing, BANDS))["delete"]

    assert delete.monthly_savings == pytest.approx(100 * 0.023)
    assert delete.annual_savings == pytest.approx(100 * 0.023 * 12)
    assert not delete.not_recommended


def test_age_out_billable_floor_from_real_bytes():
    """Checker finding 2: N tiny objects bill N x 128 KiB in IA — computed
    from stored small-object bytes, not an average guess."""
    pricing = load_pricing()
    n = 1000
    cells = [_cell(count=n, total_bytes=n * 4 * KIB,
                   small_count=n, small_bytes=n * 4 * KIB)]
    age_out = _by_option(project_options(cells, pricing, BANDS))["age-out"]

    current = (n * 4 * KIB) / BYTES_PER_GB * 0.023
    new_cost = (n * FLOOR) / BYTES_PER_GB * 0.0125
    assert age_out.monthly_savings == pytest.approx(current - new_cost)


def test_intelligent_tiering_excludes_small_objects_both_sides():
    """Checker finding 6: sub-128 KiB objects appear in neither the fee nor
    the savings."""
    pricing = load_pricing()
    big, small = 10 * BYTES_PER_GB, 1000 * 4 * KIB
    cells = [_cell(count=1000 + 10, total_bytes=big + small,
                   small_count=1000, small_bytes=small)]
    int_proj = _by_option(project_options(cells, pricing, BANDS))[
        "intelligent-tiering"]

    eligible_gb = big / BYTES_PER_GB
    expected = (eligible_gb * 0.023
                - (eligible_gb * 0.0125 + pricing.monitoring_fee(10)))
    assert int_proj.monthly_savings == pytest.approx(expected)


def test_archive_loses_money_on_tiny_objects():
    """Checker finding 10: millions of tiny objects -> overhead swamps the
    rate delta; option flags not_recommended, no break-even division."""
    pricing = load_pricing()
    n = 1_000_000
    cells = [_cell(band=">365d", count=n, total_bytes=n * 1 * KIB,
                   small_count=n, small_bytes=n * 1 * KIB)]
    archive = _by_option(project_options(cells, pricing, BANDS))["archive"]

    assert archive.monthly_savings < 0
    assert archive.not_recommended
    assert archive.break_even_months is None
    assert any("costs more" in caveat for caveat in archive.caveats)


def test_age_out_break_even_months():
    """Break-even = one-time transition fees / monthly savings."""
    pricing = load_pricing()
    cells = [_cell(count=100_000, total_bytes=100 * BYTES_PER_GB)]
    age_out = _by_option(project_options(cells, pricing, BANDS))["age-out"]

    fees = pricing.transition_fee("STANDARD_IA", 100_000)
    assert fees == pytest.approx(1.0)
    assert age_out.break_even_months == pytest.approx(
        fees / age_out.monthly_savings)
    assert any("retrieval" in caveat for caveat in age_out.caveats)


def test_archive_uses_deep_archive_for_oldest_band():
    """Last band goes Deep Archive when thresholds reach a year."""
    pricing = load_pricing()
    cells = [_cell(band=">365d", count=10, total_bytes=100 * BYTES_PER_GB)]
    archive = _by_option(project_options(cells, pricing, BANDS))["archive"]

    assert any("DEEP_ARCHIVE" in caveat for caveat in archive.caveats)
    assert any("180d" in caveat for caveat in archive.caveats)


def test_age_out_glacier_band_carries_overhead():
    """Verifier blocker: tiny objects aging out into Glacier must show the
    overhead-driven loss — same physics as the archive option."""
    pricing = load_pricing()
    n = 1_000_000
    cells = [_cell(band=">365d", count=n, total_bytes=n * 1 * KIB,
                   small_count=n, small_bytes=n * 1 * KIB)]
    age_out = _by_option(project_options(cells, pricing, BANDS))["age-out"]

    assert age_out.monthly_savings < 0
    assert age_out.not_recommended


def test_age_out_skips_unsupported_int_transition():
    """AWS forbids INT -> Standard-IA; mid-band INT cells are skipped."""
    pricing = load_pricing()
    cells = [_cell(sclass="INTELLIGENT_TIERING", total_bytes=BYTES_PER_GB)]
    age_out = _by_option(project_options(cells, pricing, BANDS))["age-out"]

    assert age_out.monthly_savings == 0
    assert age_out.caveats == ["no eligible stale data"]
    assert not age_out.not_recommended


def test_delete_covers_non_transition_classes():
    """Stale GLACIER data still saves real money when deleted."""
    pricing = load_pricing()
    cells = [_cell(band=">365d", sclass="GLACIER",
                   total_bytes=100 * BYTES_PER_GB)]
    delete = _by_option(project_options(cells, pricing, BANDS))["delete"]

    assert delete.monthly_savings == pytest.approx(100 * 0.0036)
    assert not delete.not_recommended


def test_savings_use_marginal_rate_across_tier_break():
    """Verifier finding 4: removing 1 TB from a 61 TB aggregate saves at
    the 0.022 marginal tier rate, not the blended effective rate."""
    pricing = load_pricing()
    tb = 1024 * BYTES_PER_GB
    cells = [_cell(band="90-365d", total_bytes=1 * tb, prefix="stale"),
             _cell(band="<90d", total_bytes=60 * tb, prefix="fresh")]
    delete = _by_option(project_options(cells, pricing, BANDS))["delete"]

    assert delete.monthly_savings == pytest.approx(1024 * 0.022)


def test_band_target_overrides_keyed_on_days():
    """Override map keys on threshold day values; unknown day raises."""
    assert default_band_targets([90, 365], {365: "DEEP_ARCHIVE"}) == {
        "90-365d": "STANDARD_IA", ">365d": "DEEP_ARCHIVE"}
    with pytest.raises(ValueError):
        default_band_targets([90, 365], {30: "GLACIER"})


def test_empty_run_reports_nothing_to_act_on():
    """No stale data -> calm 'no eligible stale data', never NOT RECOMMENDED."""
    pricing = load_pricing()
    projections = project_options([], pricing, BANDS)
    for proj in projections:
        assert proj.caveats == ["no eligible stale data"]
        assert not proj.not_recommended


def test_cli_age_out_map_flag(tmp_path, monkeypatch):
    """Bad --age-out-map exits 4; good map runs clean."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="old/x", size_bytes=BYTES_PER_GB,
                                last_modified=now - datetime.timedelta(days=100))

        def capabilities(self):
            raise NotImplementedError

    assert cli.main(["--bucket", "b"], provider=_Provider()) == 0
    assert cli.main(["--project-savings",
                     "--age-out-map", "90=GLACIER_IR"]) == 0
    assert cli.main(["--project-savings", "--age-out-map", "banana"]) == 4
    assert cli.main(["--project-savings", "--age-out-map", "7=GLACIER"]) == 4


def test_cli_project_savings_end_to_end(tmp_path, monkeypatch, capsys):
    """Scan a mixed bucket then --project-savings from the saved run."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="big/dump.tar",
                                size_bytes=50 * BYTES_PER_GB,
                                last_modified=now - datetime.timedelta(days=500))
            yield StorageObject(backend="s3", container=container,
                                key="fresh/app.log", size_bytes=1024,
                                last_modified=now)

        def capabilities(self):
            raise NotImplementedError

    rc = cli.main(["--bucket", "bkt"], provider=_Provider())
    assert rc == 0

    savings_csv = tmp_path / "savings.csv"
    rc = cli.main(["--project-savings", "--savings-csv", str(savings_csv)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "savings projections" in out
    with open(savings_csv, encoding="utf-8") as handle:
        rows = {row["option"]: row for row in csv.DictReader(handle)}
    assert set(rows) == {"delete", "age-out", "intelligent-tiering", "archive"}
    assert float(rows["delete"]["monthly_savings_usd"]) > 0
