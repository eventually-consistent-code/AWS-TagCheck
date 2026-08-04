"""
Purpose: End-to-end tests for --dry-run-diff — a saved run's generated
config diffed against a stubbed live provider (would-add + would-remove +
would-change all present), the loud drop-warning, the S3-only guard, and
the service-level backend guard.
Author(s): John Reed
"""

import datetime

import pytest

from tagmanager.storage import cli, services
from tagmanager.storage.base import StorageObject
from tagmanager.storage.diff import FetchResult
from tagmanager.storage.pricing import BYTES_PER_GB

NOW = datetime.datetime(2026, 8, 4, tzinfo=datetime.timezone.utc)
GEN_RULE_ID = "tagmanager-archive-age-out"


class _Provider:
    """Scans one old object, then serves stubbed live config for the diff."""

    backend_name = "s3"

    def __init__(self, live_lifecycle=None, live_tiering=None):
        self._live_lifecycle = live_lifecycle or FetchResult(present=False)
        self._live_tiering = live_tiering or FetchResult(present=False)

    def list_objects(self, container, prefix=""):
        yield StorageObject(backend="s3", container=container,
                            key="archive/old", size_bytes=BYTES_PER_GB,
                            last_modified=NOW - datetime.timedelta(days=500),
                            storage_class="STANDARD")

    def capabilities(self):
        raise NotImplementedError

    def fetch_lifecycle(self, bucket):
        return self._live_lifecycle

    def fetch_tiering(self, bucket):
        return self._live_tiering


def _seed_run(tmp_path, monkeypatch):
    """Scan once so a completed s3 run with a stale prefix is saved."""
    monkeypatch.setenv("TAGMANAGER_DB_URL", f"sqlite:///{tmp_path / 's.db'}")
    rc = cli.main(["--bucket", "bkt", "--prefix-depth", "1"],
                  provider=_Provider())
    assert rc == 0


def test_dry_run_diff_shows_add_remove_change(tmp_path, monkeypatch, capsys):
    """A live config with a foreign rule + a drifted copy of our rule
    yields would-add (ours is new vs the foreign one)… actually: our rule
    IS present but changed, plus a foreign rule that would be dropped."""
    _seed_run(tmp_path, monkeypatch)
    # live has OUR rule (different body -> change) and a foreign rule (drop).
    live = FetchResult(present=True, rules=[
        {"ID": GEN_RULE_ID, "Status": "Enabled",
         "Filter": {"And": {"Prefix": "archive/",
                            "ObjectSizeGreaterThan": 131072}},
         "Transitions": [{"Days": 9999, "StorageClass": "GLACIER"}]},
        {"ID": "customer-hand-rule", "Status": "Enabled",
         "Prefix": "invoices/",
         "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}]},
    ])
    rc = cli.main(["--dry-run-diff"],
                  provider=_Provider(live_lifecycle=live))
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run diff (read-only)" in out
    assert "~ CHANGE" in out and GEN_RULE_ID in out
    assert "- REMOVE" in out and "customer-hand-rule" in out
    assert "would DROP it" in out          # the loud drop-warning
    assert "nothing was written" in out


def test_dry_run_diff_no_live_config_is_all_add(tmp_path, monkeypatch,
                                                capsys):
    _seed_run(tmp_path, monkeypatch)
    rc = cli.main(["--dry-run-diff"], provider=_Provider())
    out = capsys.readouterr().out
    assert rc == 0
    assert "no live config" in out
    assert "+ ADD" in out and GEN_RULE_ID in out


def test_dry_run_diff_unknown_on_403(tmp_path, monkeypatch, capsys):
    _seed_run(tmp_path, monkeypatch)
    denied = FetchResult(present=False, unknown=True)
    rc = cli.main(["--dry-run-diff"],
                  provider=_Provider(live_lifecycle=denied))
    out = capsys.readouterr().out
    assert rc == 0
    assert "no permission" in out


def test_dry_run_diff_s3_only_guard(tmp_path, monkeypatch, caplog):
    """A non-S3 backend is refused before any DB / provider work."""
    monkeypatch.setenv("TAGMANAGER_DB_URL", f"sqlite:///{tmp_path / 's.db'}")
    rc = cli.main(["--dry-run-diff", "--backend", "azure"])
    assert rc == 4
    assert "s3 only" in caplog.text.lower()


def test_dry_run_diff_no_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGMANAGER_DB_URL", f"sqlite:///{tmp_path / 's.db'}")
    rc = cli.main(["--dry-run-diff"], provider=_Provider())
    assert rc == 4  # no saved run


def test_service_backend_guard():
    """services.dry_run_diff refuses a non-S3 run (belt-and-suspenders)."""
    from types import SimpleNamespace  # pylint: disable=import-outside-toplevel
    run = SimpleNamespace(backend="gcs", id=1, age_band_days=[90, 365])
    with pytest.raises(services.StorageServiceError):
        services.dry_run_diff(session=None, run=run, provider=_Provider())
