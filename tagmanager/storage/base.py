"""
Purpose: Storage backend contract — normalized object record, capability
flags, and the abstract interface every mass-storage backend implements
(S3 first; Azure Blob, GCS, and SMB/local filesystem follow in phase 4).
Author(s): John Reed
"""

import abc
import datetime
from dataclasses import dataclass


@dataclass
class StorageObject:  # pylint: disable=too-many-instance-attributes
    """One stored object/file in cross-backend normal form."""

    backend: str
    container: str
    key: str
    size_bytes: int
    last_modified: datetime.datetime
    storage_class: str = "STANDARD"
    owner: str = ""
    region: str = ""
    last_accessed: datetime.datetime = None


@dataclass
class StorageCapabilities:
    """What a storage backend can report beyond the basics."""

    supports_storage_class: bool
    supports_last_access: bool


class StorageProvider(abc.ABC):
    """Abstract mass-storage backend: read-only inventory, never mutation."""

    backend_name = "abstract"

    @abc.abstractmethod
    def list_objects(self, container, prefix=""):
        """
        Yield StorageObject for every object in the container under prefix.

        Implementations stream — one page at a time, never the full listing
        in memory.

        :param container: bucket / container / share root name
        :param prefix: optional key prefix to scope the walk
        :yields: StorageObject
        """

    @abc.abstractmethod
    def capabilities(self):
        """
        Declare backend capabilities.

        :returns: StorageCapabilities
        """
