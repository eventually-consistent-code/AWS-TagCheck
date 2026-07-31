"""
Purpose: Tests for the filesystem storage provider — walk, atime/mtime
mapping, permission isolation, symlink skip, and fs CLI behavior.
Author(s): John Reed
"""

import datetime
import os

from tagmanager.storage import cli
from tagmanager.storage.fs_provider import FilesystemStorageProvider


def _make_tree(root):
    """Build a small tree with known mtimes/atimes."""
    (root / "logs" / "2019").mkdir(parents=True)
    (root / "hot").mkdir()
    old = root / "logs" / "2019" / "dump.tar"
    old.write_bytes(b"x" * 100)
    fresh = root / "hot" / "current.log"
    fresh.write_bytes(b"y" * 50)

    old_epoch = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(days=500)).timestamp()
    os.utime(old, (old_epoch, old_epoch))
    return old, fresh


def test_fs_provider_walks_tree(tmp_path):
    """Files map to StorageObject with relative keys, mtime, atime."""
    _make_tree(tmp_path)
    objs = {o.key: o for o in
            FilesystemStorageProvider().list_objects(str(tmp_path))}

    assert set(objs) == {os.path.join("logs", "2019", "dump.tar"),
                         os.path.join("hot", "current.log")}
    old = objs[os.path.join("logs", "2019", "dump.tar")]
    assert old.size_bytes == 100
    assert old.storage_class == "FILESYSTEM"
    assert old.backend == "fs"
    age = (datetime.datetime.now(datetime.timezone.utc)
           - old.last_modified).days
    assert 499 <= age <= 501
    assert old.last_accessed is not None
    assert old.owner  # resolvable on macOS/Linux test hosts


def test_fs_provider_prefix_scopes_walk(tmp_path):
    """prefix narrows to a subtree."""
    _make_tree(tmp_path)
    objs = list(FilesystemStorageProvider().list_objects(
        str(tmp_path), prefix="hot"))
    assert [o.key for o in objs] == [os.path.join("hot", "current.log")]


def test_fs_provider_skips_symlinks_and_unreadable(tmp_path):
    """Symlinks skipped; unreadable subdirs isolate, walk continues."""
    _make_tree(tmp_path)
    (tmp_path / "loop").symlink_to(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "secret.txt").write_bytes(b"z")
    locked.chmod(0o000)
    try:
        objs = list(FilesystemStorageProvider().list_objects(str(tmp_path)))
    finally:
        locked.chmod(0o755)

    keys = {o.key for o in objs}
    assert os.path.join("hot", "current.log") in keys
    assert not any("secret" in k or "loop" in k for k in keys)


def test_fs_provider_missing_root_raises(tmp_path):
    """A bad root is an error the CLI isolates as a bucket skip."""
    try:
        list(FilesystemStorageProvider().list_objects(str(tmp_path / "nope")))
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_fs_capabilities():
    caps = FilesystemStorageProvider().capabilities()
    assert caps.supports_last_access is True
    assert caps.supports_storage_class is False


def test_cli_fs_scan_and_no_pricing(tmp_path, monkeypatch, capsys):
    """fs scan works end-to-end; cost report says no pricing, exit 4."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    data_root = tmp_path / "share"
    data_root.mkdir()
    _make_tree(data_root)

    rc = cli.main(["--backend", "fs", "--bucket", str(data_root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "storage age scan" in out

    assert cli.main(["--backend", "fs", "--cost-report"]) == 4
