"""
Purpose: Service-layer tests — options/CLI default equivalence, typed
errors where the CLI maps exit 4, the scan service end-to-end without any
CLI, and per-object hook cancellation.
Author(s): John Reed
"""

import datetime

import pytest

from tagmanager.config import Settings
from tagmanager.storage import cli, services
from tagmanager.storage.base import StorageObject
from tagmanager.storage.pricing import BYTES_PER_GB

NOW = datetime.datetime.now(datetime.timezone.utc)

# ScanOptions field -> parse_args attribute carrying the same default.
OPTION_TO_FLAG = {
    "backend": "backend",
    "account_url": "account_url",
    "prefix": "prefix",
    "rollup_owners": "rollup_owners",
    "emit_delete_dir": "emit_delete_manifests",
    "emit_batch_copy_dir": "emit_batch_copy",
    "emit_move_plan_dir": "emit_move_plan",
}


class _Provider:
    backend_name = "s3"

    def __init__(self, objs=None):
        self._objs = objs

    def list_objects(self, container, prefix=""):
        if self._objs is not None:
            yield from self._objs
            return
        yield StorageObject(backend="s3", container=container,
                            key="logs/old.log", size_bytes=8 * BYTES_PER_GB,
                            last_modified=NOW - datetime.timedelta(days=500))
        yield StorageObject(backend="s3", container=container,
                            key="logs/new.log", size_bytes=BYTES_PER_GB,
                            last_modified=NOW)

    def capabilities(self):
        raise NotImplementedError


def _maker(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'svc.db'}")
    return services.open_storage_session_maker()


def test_scan_options_defaults_mirror_cli_flags():
    """Every shared field's default equals the CLI flag default."""
    args = cli.parse_args([])
    opts = services.ScanOptions()
    for field_name, flag_name in OPTION_TO_FLAG.items():
        assert getattr(opts, field_name) == getattr(args, flag_name), \
            f"{field_name} default drifted from --{flag_name}"


def test_run_storage_scan_persists_and_reports(tmp_path, monkeypatch):
    """Scan service returns run id, builder totals, and no emitters."""
    maker = _maker(tmp_path, monkeypatch)
    result = services.run_storage_scan(
        maker, services.ScanOptions(buckets=("bkt",)), provider=_Provider())

    assert result.run_id == 1
    assert result.builder.objects_seen == 2
    assert not result.cancelled
    assert result.emitter_reports == []

    session = maker()
    run = session.get(__import__("tagmanager.models.tables",
                                 fromlist=["StorageScanRun"]).StorageScanRun,
                      result.run_id)
    assert run.status == "complete"
    assert run.objects_seen == 2


def test_on_object_hook_counts_and_cancels(tmp_path, monkeypatch):
    """The per-object hook sees running counts; raising ScanCancelled
    stops the walk and the run persists as cancelled."""
    maker = _maker(tmp_path, monkeypatch)
    seen = []

    def hook(count):
        seen.append(count)
        if count >= 1:
            raise services.ScanCancelled()

    result = services.run_storage_scan(
        maker, services.ScanOptions(buckets=("bkt",), on_object=hook),
        provider=_Provider())

    assert result.cancelled
    assert seen == [1]
    session = maker()
    from tagmanager.models.tables import StorageScanRun  # pylint: disable=import-outside-toplevel
    run = session.get(StorageScanRun, result.run_id)
    assert run.status == "cancelled"


def test_make_provider_errors_are_typed():
    """Azure without account_url raises the typed service error."""
    with pytest.raises(services.StorageServiceError, match="account-url"):
        services.make_provider("azure")


def test_analyze_projections_rejects_bad_map(tmp_path, monkeypatch):
    """Invalid age-out override raises typed error (CLI maps to exit 4)."""
    maker = _maker(tmp_path, monkeypatch)
    services.run_storage_scan(maker, services.ScanOptions(buckets=("bkt",)),
                              provider=_Provider())
    session = maker()
    from tagmanager.storage.store import latest_complete_run  # pylint: disable=import-outside-toplevel
    run = latest_complete_run(session, backend="s3")

    with pytest.raises(services.StorageServiceError, match="BOGUS"):
        services.analyze_projections(session, run,
                                     age_out_map_raw="90=BOGUS")
    projections = services.analyze_projections(session, run)
    assert {p.option for p in projections} == {
        "delete", "age-out", "intelligent-tiering", "archive"}


def test_emit_lifecycle_service_raises_when_empty(tmp_path, monkeypatch):
    """Fresh-only run -> typed error, not a broken directory."""
    maker = _maker(tmp_path, monkeypatch)
    fresh = [StorageObject(backend="s3", container="bkt", key="hot/x",
                           size_bytes=1024, last_modified=NOW)]
    services.run_storage_scan(maker, services.ScanOptions(buckets=("bkt",)),
                              provider=_Provider(objs=fresh))
    session = maker()
    from tagmanager.storage.store import latest_complete_run  # pylint: disable=import-outside-toplevel
    run = latest_complete_run(session, backend="s3")

    with pytest.raises(services.StorageServiceError, match="no lifecycle"):
        services.emit_lifecycle_artifacts(session, run, tmp_path / "life")


def test_recommend_structure_service_persists(tmp_path, monkeypatch):
    """Recommendations persist on the run row via the service."""
    maker = _maker(tmp_path, monkeypatch)
    services.run_storage_scan(maker, services.ScanOptions(buckets=("bkt",)),
                              provider=_Provider())
    session = maker()
    from tagmanager.storage.store import latest_complete_run  # pylint: disable=import-outside-toplevel
    run = latest_complete_run(session, backend="s3")

    result = services.recommend_structure(session, run)
    assert result.recs and result.recs[0].kind == "date-split"
    assert not result.truncated
    assert run.structure_recs[0]["kind"] == "date-split"


def test_schema_guard_raises_typed(tmp_path, monkeypatch):
    """Stale dev DB raises SchemaOutOfDate from the maker factory."""
    import sqlite3  # pylint: disable=import-outside-toplevel
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE storage_prefix_stats (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE storage_scan_runs (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    monkeypatch.setenv("TAGMANAGER_DB_URL", f"sqlite:///{db}")

    with pytest.raises(services.SchemaOutOfDate):
        services.open_storage_session_maker(Settings())
