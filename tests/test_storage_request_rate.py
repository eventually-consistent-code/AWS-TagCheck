"""
Purpose: Tests for per-prefix request-rate estimation and the fan-out
recommendation — op counting, the minimum-window guard, source merge,
persistence, and the highest-precedence prefix-fanout kind.
Author(s): John Reed
"""

import datetime
from types import SimpleNamespace

from tagmanager.storage import services
from tagmanager.storage.base import StorageObject
from tagmanager.storage.pricing import BYTES_PER_GB
from tagmanager.storage.request_rate import (DEFAULT_MIN_WINDOW_SECONDS,
                                             estimate_rates, fold_rates)
from tagmanager.storage.structure import (FANOUT_CEILING_FRACTION,
                                          READ_CEILING_RPS,
                                          build_recommendations)

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)
BANDS = [90, 365]


def _ev(key, offset_s, optype="read", bucket="bkt"):
    return (bucket, key, NOW + datetime.timedelta(seconds=offset_s), optype)


def test_fold_and_estimate_rates():
    """Ops fold per prefix; rates = count / observed window."""
    # 7200 reads across a 2-hour window under logs/ -> 1.0 read/s
    events = [_ev("logs/f", i, "read") for i in range(0, 7201, 1)]
    events += [_ev("logs/f", i, "write") for i in range(0, 3601, 1)]
    stats = fold_rates(events, prefix_depth=1)
    rates = estimate_rates(stats, min_window_seconds=60)
    r = rates["bkt/logs"]
    assert abs(r["read_rps"] - 1.0) < 0.01
    assert abs(r["write_rps"] - 0.5) < 0.01
    assert r["window_s"] == 7200.0
    assert r["sample_ops"] == 7201 + 3601


def test_min_window_guard_suppresses_short_samples():
    """A window below the guard yields no rate for that prefix."""
    events = [_ev("hot/x", 0), _ev("hot/x", 30)]  # 30s window
    stats = fold_rates(events, prefix_depth=1)
    assert estimate_rates(stats, min_window_seconds=3600) == {}
    # default guard is an hour
    assert DEFAULT_MIN_WINDOW_SECONDS == 3600


def test_build_access_report_merges_rate_counts(tmp_path):
    """Access-log + CloudTrail op counts sum into one rate map."""
    import gzip  # pylint: disable=import-outside-toplevel
    import json  # pylint: disable=import-outside-toplevel
    # CloudTrail: 3601 reads over 1h under data/
    recs = [{"eventSource": "s3.amazonaws.com", "eventName": "GetObject",
             "eventTime": (NOW + datetime.timedelta(seconds=i)).strftime(
                 "%Y-%m-%dT%H:%M:%SZ"),
             "requestParameters": {"bucketName": "b", "key": "data/x"}}
            for i in range(0, 3601, 1)]
    ct = tmp_path / "t.json.gz"
    ct.write_bytes(gzip.compress(json.dumps({"Records": recs}).encode()))

    report = services.build_access_report(cloudtrail_paths=[str(ct)],
                                          prefix_depth=1)
    assert "b/data" in report.rates
    assert abs(report.rates["b/data"]["read_rps"] - 1.0) < 0.01


def _stat(prefix="logs", band=">365d", total_bytes=10 * BYTES_PER_GB):
    return SimpleNamespace(container="bkt", prefix=prefix,
                           storage_class="STANDARD", age_band=band,
                           object_count=10, total_bytes=total_bytes,
                           small_object_count=0, small_object_bytes=0,
                           owner="", data_type="")


def _hot_rate(read_frac):
    return {"read_rps": read_frac * READ_CEILING_RPS, "write_rps": 0,
            "window_s": 7200, "sample_ops": 99999}


def test_fanout_fires_past_the_fraction():
    """A prefix over the ceiling fraction gets prefix-fanout."""
    stats = [_stat(band=">365d")]  # would be straight-lifecycle
    rates = {"bkt/logs": _hot_rate(FANOUT_CEILING_FRACTION + 0.05)}
    recs, _ = build_recommendations(stats, BANDS, request_rates=rates)
    assert recs[0].kind == "prefix-fanout"
    assert "503 Slow Down" in recs[0].rationale


def test_fanout_silent_below_the_fraction():
    """Below the trigger, the lifecycle rec stands."""
    stats = [_stat(band=">365d")]
    rates = {"bkt/logs": _hot_rate(FANOUT_CEILING_FRACTION - 0.05)}
    recs, _ = build_recommendations(stats, BANDS, request_rates=rates)
    assert recs[0].kind == "straight-lifecycle"


def test_fanout_beats_every_lifecycle_kind():
    """Even a compact-first prefix yields fan-out when hot (highest
    precedence)."""
    stats = [_stat(band=">365d")]
    stats[0].small_object_count = 9  # would be compact-first
    stats[0].object_count = 10
    rates = {"bkt/logs": _hot_rate(0.9)}
    recs, _ = build_recommendations(stats, BANDS, request_rates=rates)
    assert recs[0].kind == "prefix-fanout"


def test_note_splits_on_rates_recorded():
    """The fan-out note retires when rates are present; churn note stays."""
    stats = [_stat(band=">365d")]
    _, notes_without = build_recommendations(stats, BANDS)
    assert any("request-rate fan-out" in n for n in notes_without)
    _, notes_with = build_recommendations(
        stats, BANDS, request_rates={"bkt/logs": _hot_rate(0.9)})
    assert not any("request-rate fan-out" in n for n in notes_with)
    assert any("churn" in n for n in notes_with)


def test_cli_persists_request_rates(tmp_path, monkeypatch):
    """A scan with --access-logs persists a request_rates map on the run."""
    monkeypatch.setenv("TAGMANAGER_DB_URL", f"sqlite:///{tmp_path / 's.db'}")
    # 7200 GET reads over 2h under archive/
    lines = []
    for i in range(0, 7200, 1):
        stamp = (NOW + datetime.timedelta(seconds=i)).strftime(
            "%d/%b/%Y:%H:%M:%S +0000")
        lines.append(f"o bkt [{stamp}] ip req id REST.GET.OBJECT "
                     f"archive/f{i % 3} \"GET / HTTP/1.1\" 200 - 1 1 1 1 "
                     "\"-\" \"c\" - t= v c a h T - -")
    log = tmp_path / "access.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    from tagmanager.models.tables import StorageScanRun  # pylint: disable=import-outside-toplevel

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="archive/f0", size_bytes=BYTES_PER_GB,
                                last_modified=NOW - datetime.timedelta(days=500))

        def capabilities(self):
            raise NotImplementedError

    from tagmanager.storage import cli  # pylint: disable=import-outside-toplevel
    rc = cli.main(["--bucket", "bkt", "--prefix-depth", "1",
                   "--access-logs", str(log)], provider=_Provider())
    assert rc == 0

    maker = services.open_storage_session_maker()
    session = maker()
    run = session.query(StorageScanRun).one()
    assert "bkt/archive" in run.request_rates
    assert run.request_rates["bkt/archive"]["read_rps"] > 0
