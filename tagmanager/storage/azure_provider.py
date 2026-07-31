"""
Purpose: Azure Blob storage backend — streams blob metadata (name, size,
tier, last-modified, last-accessed where the account tracks it) via
ContainerClient.list_blobs pagination. SDK imported lazily; the base
install stays cloud-optional.
Author(s): John Reed
"""

import logging

from tagmanager.storage.base import (StorageCapabilities, StorageObject,
                                     StorageProvider)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.azure_blob_storage")
LOG.setLevel(logging.INFO)


def _load_sdk():
    """
    Import the Azure SDK pieces, with a helpful error when absent.

    :returns: (BlobServiceClient, DefaultAzureCredential)
    :raises RuntimeError: azure packages not installed
    """
    try:
        from azure.identity import DefaultAzureCredential  # pylint: disable=import-outside-toplevel
        from azure.storage.blob import BlobServiceClient  # pylint: disable=import-outside-toplevel
    except ImportError as err:
        raise RuntimeError(
            "azure backend needs the optional dependencies — "
            "pip install azure-storage-blob azure-identity") from err
    return BlobServiceClient, DefaultAzureCredential


class AzureBlobStorageProvider(StorageProvider):
    """Reads container inventories via list_blobs pagination."""

    backend_name = "azure"

    def __init__(self, account_url, service_client=None):
        """
        :param account_url: https://<account>.blob.core.windows.net
        :param service_client: injected BlobServiceClient (tests)
        """
        if service_client is None:
            client_cls, credential_cls = _load_sdk()
            service_client = client_cls(account_url,
                                        credential=credential_cls())
        self._service = service_client

    def list_objects(self, container, prefix=""):
        """
        Yield StorageObject for every blob in the container under prefix.

        last_accessed comes from last_accessed_on when the account has
        last-access-time tracking enabled (~daily resolution); None
        otherwise.

        :param container: container name
        :param prefix: optional name prefix
        :yields: StorageObject
        """
        LOG.info("scanning azure container %s...", container)
        client = self._service.get_container_client(container)
        for blob in client.list_blobs(name_starts_with=prefix or None):
            tier = str(blob.blob_tier).upper() if blob.blob_tier else "HOT"
            yield StorageObject(
                backend="azure",
                container=container,
                key=blob.name,
                size_bytes=blob.size,
                last_modified=blob.last_modified,
                storage_class=tier,
                last_accessed=getattr(blob, "last_accessed_on", None),
            )

    def capabilities(self):
        """
        Declare backend capabilities.

        :returns: StorageCapabilities
        """
        return StorageCapabilities(
            supports_storage_class=True,
            supports_last_access=True,
        )
