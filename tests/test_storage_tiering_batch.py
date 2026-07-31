"""
Purpose: Tests for Intelligent-Tiering config generation and batch-copy
manifests — minimum-day validation, URL-encoded keys, the 5 GB skip list,
and both CLI paths.
Author(s): John Reed
"""

import datetime
from types import SimpleNamespace

import pytest

from tagmanager.storage import cli
from tagmanager.storage.base import StorageObject
from tagmanager.storage.manifests import BatchCopyEmitter
from tagmanager.storage.tiering_gen import (TieringValidationError,
                                            build_tiering_configs)

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)
BANDS = [90, 365]
GIB = 1024 ** 3


def _stat(prefix="logs/2019", band=">365d", sclass="STANDARD",
          container="bkt"):
    return SimpleNamespace(container=container, prefix=prefix,
                           storage_class=sclass, age_band=band,
                           object_count=1, total_bytes=1024,
                           small_object_count=0, small_object_bytes=0)


def _obj(key, days_old, size=1024, container="bkt"):
    return StorageObject(backend="s3", container=container, key=key,
                         size_bytes=size,
                         last_modified=NOW - datetime.timedelta(days=days_old))


def test_tiering_config_shape():
    """Stale eligible prefix gets Id/Filter/Tierings with 90/180 defaults."""
    configs, skips = build_tiering_configs([_stat()], BANDS)

    assert not skips
    config = configs["bkt"][0]
    assert config["Filter"] == {"Prefix": "logs/2019/"}
    assert config["Tierings"] == [
        {"Days": 90, "AccessTier": "ARCHIVE_ACCESS"},
        {"Days": 180, "AccessTier": "DEEP_ARCHIVE_ACCESS"}]


def test_tiering_skips_cold_classes():
    """GLACIER prefixes gain nothing — skip with reason."""
    configs, skips = build_tiering_configs([_stat(sclass="GLACIER")], BANDS)
    assert not configs
    assert "gains nothing" in skips[0]


def test_tiering_validates_minimums():
    """ARCHIVE_ACCESS below 90d is a generation error."""
    with pytest.raises(TieringValidationError, match="outside"):
        build_tiering_configs([_stat()], BANDS, archive_days=30)


def test_batch_copy_url_encodes_keys(tmp_path):
    """Commas, spaces, unicode in keys are URL-encoded; slashes survive."""
    emitter = BatchCopyEmitter(tmp_path, stale_after_days=365, now=NOW)
    emitter.offer(_obj("dir/report, final draft ü.pdf", days_old=400))
    summary = emitter.close()

    assert summary["bkt"]["keys"] == 1
    line = (tmp_path / "bkt.batch-copy.csv").read_text(encoding="utf-8")
    assert line == "bkt,dir/report%2C%20final%20draft%20%C3%BC.pdf\n"


def test_batch_copy_skips_large_objects(tmp_path):
    """>5 GB objects land in the sidecar, not the manifest."""
    emitter = BatchCopyEmitter(tmp_path, stale_after_days=365, now=NOW)
    emitter.offer(_obj("big.tar", days_old=400, size=6 * GIB))
    emitter.offer(_obj("small.tar", days_old=400, size=1 * GIB))
    summary = emitter.close()

    assert summary["bkt"] == {"keys": 1, "skipped_large": 1}
    sidecar = (tmp_path / "bkt.batch-copy.skipped.txt").read_text(
        encoding="utf-8")
    assert sidecar.startswith("big.tar\t")
    manifest = (tmp_path / "bkt.batch-copy.csv").read_text(encoding="utf-8")
    assert "big.tar" not in manifest


def test_batch_copy_fresh_objects_ignored(tmp_path):
    """Objects under the threshold produce nothing."""
    emitter = BatchCopyEmitter(tmp_path, stale_after_days=365, now=NOW)
    emitter.offer(_obj("fresh", days_old=10))
    assert emitter.close() == {}


def test_cli_emit_tiering_and_batch_copy(tmp_path, monkeypatch, capsys):
    """Scan emits batch-copy manifests; report mode emits tiering configs."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="logs/2019/dump.tar", size_bytes=GIB,
                                last_modified=now - datetime.timedelta(days=500))

        def capabilities(self):
            raise NotImplementedError

    copy_dir = tmp_path / "copies"
    rc = cli.main(["--bucket", "bkt", "--emit-batch-copy", str(copy_dir)],
                  provider=_Provider())
    assert rc == 0
    assert (copy_dir / "bkt.batch-copy.csv").exists()
    apply_text = (copy_dir / "APPLY.md").read_text(encoding="utf-8")
    assert "create-job" in apply_text
    assert "DEEP_ARCHIVE" in apply_text
    assert "batchoperations.s3.amazonaws.com" in apply_text

    tier_dir = tmp_path / "tiering"
    rc = cli.main(["--emit-tiering", str(tier_dir)])
    assert rc == 0
    tier_apply = (tier_dir / "APPLY.md").read_text(encoding="utf-8")
    assert "put-bucket-intelligent-tiering-configuration" in tier_apply
    assert "ALREADY in the INTELLIGENT_TIERING" in tier_apply

    out = capsys.readouterr().out
    assert "copy candidate" in out
    assert "tiering configs saved" in out

    # Key-level manifests refuse report-only mode.
    assert cli.main(["--emit-batch-copy", str(copy_dir)]) == 4
