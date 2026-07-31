"""
Purpose: Google Cloud Storage backend — streams blob metadata (name, size,
storage class, updated) via Client.list_blobs pagination. GCS exposes no
per-object last-access time, so ages here are modified-age only. SDK
imported lazily; the base install stays cloud-optional.
Author(s): John Reed
"""

import logging

from tagmanager.storage.base import (StorageCapabilities, StorageObject,
                                     StorageProvider)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.gcs_storage")
LOG.setLevel(logging.INFO)


def _load_sdk():
    """
    Import the GCS client class, with a helpful error when absent.

    :returns: google.cloud.storage.Client class
    :raises RuntimeError: google-cloud-storage not installed
    """
    try:
        from google.cloud import storage  # pylint: disable=import-outside-toplevel
    except ImportError as err:
        raise RuntimeError(
            "gcs backend needs the optional dependency — "
            "pip install google-cloud-storage") from err
    return storage.Client


class GcsStorageProvider(StorageProvider):
    """Reads bucket inventories via list_blobs pagination."""

    backend_name = "gcs"

    def __init__(self, client=None):
        """
        :param client: injected google.cloud.storage.Client (tests)
        """
        if client is None:
            client = _load_sdk()()
        self._client = client

    def list_objects(self, container, prefix=""):
        """
        Yield StorageObject for every object in the bucket under prefix.

        :param container: bucket name
        :param prefix: optional name prefix
        :yields: StorageObject
        """
        LOG.info("scanning gcs bucket %s...", container)
        for blob in self._client.list_blobs(container, prefix=prefix or None):
            yield StorageObject(
                backend="gcs",
                container=container,
                key=blob.name,
                size_bytes=blob.size,
                last_modified=blob.updated,
                storage_class=blob.storage_class or "STANDARD",
            )

    def capabilities(self):
        """
        Declare backend capabilities.

        GCS has no per-object last-access surface — modified-age only.

        :returns: StorageCapabilities
        """
        return StorageCapabilities(
            supports_storage_class=True,
            supports_last_access=False,
        )
