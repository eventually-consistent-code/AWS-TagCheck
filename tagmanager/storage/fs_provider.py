"""
Purpose: Filesystem storage backend — recursive scandir walk of a local
path or mounted SMB share. mtime is last-modified, atime is last-accessed
(honest where the mount updates it, e.g. not on noatime mounts), owner
comes from the uid when the platform can resolve it. Permission errors
skip the subtree and keep walking.
Author(s): John Reed
"""

import datetime
import logging
import os
import pathlib

from tagmanager.storage.base import (StorageCapabilities, StorageObject,
                                     StorageProvider)

try:
    import pwd
except ImportError:  # Windows — resolve owners as empty
    pwd = None

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.fs_storage")
LOG.setLevel(logging.INFO)


def _owner_name(uid, cache):
    """
    Best-effort uid -> username, cached; empty when unresolvable.

    :param uid: numeric uid from stat
    :param cache: dict cache (mutated)
    :returns: username string or ""
    """
    if pwd is None:
        return ""
    if uid not in cache:
        try:
            cache[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            cache[uid] = ""
    return cache[uid]


def _utc(timestamp):
    """Epoch seconds -> timezone-aware UTC datetime."""
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)


class FilesystemStorageProvider(StorageProvider):
    """Reads directory trees as storage inventories."""

    backend_name = "fs"

    def list_objects(self, container, prefix=""):
        """
        Yield StorageObject for every file under the root path.

        :param container: root directory path (local or mounted share)
        :param prefix: optional relative sub-path to scope the walk
        :yields: StorageObject
        """
        root = pathlib.Path(container)
        start = root / prefix if prefix else root
        if not start.is_dir():
            raise FileNotFoundError(f"not a directory: {start}")
        LOG.info("scanning filesystem tree %s...", start)
        owner_cache = {}
        yield from self._walk(start, root, owner_cache)

    def _walk(self, directory, root, owner_cache):
        """Recurse one directory, isolating permission failures."""
        try:
            entries = list(os.scandir(directory))
        except PermissionError as err:
            LOG.warning("skipping %s: %s", directory, err)
            return
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    yield from self._walk(entry.path, root, owner_cache)
                    continue
                stat = entry.stat(follow_symlinks=False)
            except (PermissionError, FileNotFoundError) as err:
                LOG.warning("skipping %s: %s", entry.path, err)
                continue
            yield StorageObject(
                backend="fs",
                container=str(root),
                key=os.path.relpath(entry.path, root),
                size_bytes=stat.st_size,
                last_modified=_utc(stat.st_mtime),
                storage_class="FILESYSTEM",
                owner=_owner_name(stat.st_uid, owner_cache),
                last_accessed=_utc(stat.st_atime),
            )

    def capabilities(self):
        """
        Declare backend capabilities.

        :returns: StorageCapabilities
        """
        return StorageCapabilities(
            supports_storage_class=False,
            supports_last_access=True,
        )
