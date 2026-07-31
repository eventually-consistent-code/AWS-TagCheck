"""
Purpose: Tests for delete manifests — chunk boundaries, payload shape,
stale predicate, the --delete-after Expiration flavor, and CLI wiring.
Author(s): John Reed
"""

import datetime
import json

from tagmanager.storage import cli
from tagmanager.storage.base import StorageObject
from tagmanager.storage.manifests import DeleteManifestEmitter

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)


def _obj(key, days_old, container="bkt"):
    return StorageObject(backend="s3", container=container, key=key,
                         size_bytes=1024,
                         last_modified=NOW - datetime.timedelta(days=days_old))


def test_emitter_chunks_at_limit(tmp_path):
    """1,500 stale keys split into a 1,000-chunk and a 500-chunk."""
    emitter = DeleteManifestEmitter(tmp_path, stale_after_days=365, now=NOW)
    for i in range(1500):
        emitter.offer(_obj(f"old/f{i}", days_old=400))

    summary = emitter.close()
    assert summary == {"bkt": {"files": 2, "keys": 1500}}

    with open(tmp_path / "bkt.delete-0001.json", encoding="utf-8") as handle:
        chunk = json.load(handle)
    assert len(chunk["Objects"]) == 1000
    assert chunk["Quiet"] is True
    with open(tmp_path / "bkt.delete-0002.json", encoding="utf-8") as handle:
        assert len(json.load(handle)["Objects"]) == 500


def test_emitter_stale_predicate(tmp_path):
    """Only objects at or past the threshold are captured."""
    emitter = DeleteManifestEmitter(tmp_path, stale_after_days=365, now=NOW)
    emitter.offer(_obj("fresh", days_old=10))
    emitter.offer(_obj("mid", days_old=200))
    emitter.offer(_obj("old", days_old=400))

    summary = emitter.close()
    assert summary == {"bkt": {"files": 1, "keys": 1}}
    with open(tmp_path / "bkt.delete-0001.json", encoding="utf-8") as handle:
        assert json.load(handle)["Objects"] == [{"Key": "old"}]


def test_emitter_multi_bucket(tmp_path):
    """Buckets chunk independently."""
    emitter = DeleteManifestEmitter(tmp_path, stale_after_days=90, now=NOW)
    emitter.offer(_obj("a", days_old=100, container="one"))
    emitter.offer(_obj("b", days_old=100, container="two"))

    summary = emitter.close()
    assert set(summary) == {"one", "two"}
    assert (tmp_path / "one.delete-0001.json").exists()
    assert (tmp_path / "two.delete-0001.json").exists()


def test_cli_emit_delete_manifests(tmp_path, monkeypatch, capsys):
    """Scan-mode flag writes chunks + APPLY.md; report-only mode refuses."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="old/dump.tar", size_bytes=1024 ** 3,
                                last_modified=now - datetime.timedelta(days=500))
            yield StorageObject(backend="s3", container=container,
                                key="fresh/app.log", size_bytes=1024,
                                last_modified=now)

        def capabilities(self):
            raise NotImplementedError

    out_dir = tmp_path / "deletes"
    rc = cli.main(["--bucket", "bkt", "--emit-delete-manifests", str(out_dir)],
                  provider=_Provider())
    assert rc == 0

    with open(out_dir / "bkt.delete-0001.json", encoding="utf-8") as handle:
        assert json.load(handle)["Objects"] == [{"Key": "old/dump.tar"}]
    apply_text = (out_dir / "APPLY.md").read_text(encoding="utf-8")
    assert "delete-objects" in apply_text
    assert "delete markers" in apply_text
    assert "delete candidate" in capsys.readouterr().out

    assert cli.main(["--emit-delete-manifests", str(out_dir)]) == 4


def test_cli_delete_after_expiration(tmp_path, monkeypatch):
    """--delete-after adds validated Expiration rules to emitted configs."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="logs/2019/dump.tar",
                                size_bytes=10 * 1024 ** 3,
                                last_modified=now - datetime.timedelta(days=500))

        def capabilities(self):
            raise NotImplementedError

    assert cli.main(["--bucket", "bkt"], provider=_Provider()) == 0

    out_dir = tmp_path / "artifacts"
    rc = cli.main(["--emit-lifecycle", str(out_dir), "--delete-after", "730"])
    assert rc == 0
    with open(out_dir / "bkt.lifecycle.json", encoding="utf-8") as handle:
        rule = json.load(handle)["Rules"][0]
    assert rule["Expiration"] == {"Days": 730}

    # Expiration at/below the last transition is refused by the validator.
    assert cli.main(["--emit-lifecycle", str(out_dir),
                     "--delete-after", "100"]) == 4
