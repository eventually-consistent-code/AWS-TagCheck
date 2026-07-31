"""
Purpose: S3 storage backend — streams object metadata (key, size, storage
class, last-modified) from paginated ListObjectsV2, no per-object HEAD calls.
Author(s): John Reed
"""

import logging

import boto3

from tagmanager.storage.base import (StorageCapabilities, StorageObject,
                                     StorageProvider)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.s3_storage")
LOG.setLevel(logging.INFO)


class S3StorageProvider(StorageProvider):
    """Reads bucket inventories via ListObjectsV2 pagination."""

    backend_name = "s3"

    def __init__(self, session=None):
        """
        Initialize the provider.

        :param session: boto3.Session (default: environment credential chain)
        """
        self._session = session or boto3.Session()

    def list_objects(self, container, prefix=""):
        """
        Yield StorageObject for every object in the bucket under prefix.

        Each listing page already carries Key/Size/StorageClass/LastModified,
        so the walk costs one API call per 1000 objects and nothing more.

        :param container: bucket name
        :param prefix: optional key prefix
        :yields: StorageObject
        """
        LOG.info("scanning s3 bucket %s...", container)
        client = self._session.client("s3")
        paginator = client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=container, Prefix=prefix):
            for item in page.get("Contents", []):
                yield StorageObject(
                    backend="s3",
                    container=container,
                    key=item["Key"],
                    size_bytes=item["Size"],
                    last_modified=item["LastModified"],
                    storage_class=item.get("StorageClass", "STANDARD"),
                )

    def capabilities(self):
        """
        Declare backend capabilities.

        Last-access enrichment (server access logs / Storage Class Analysis)
        lands in phase 4 — until then age means last-modified.

        :returns: StorageCapabilities
        """
        return StorageCapabilities(
            supports_storage_class=True,
            supports_last_access=False,
        )
