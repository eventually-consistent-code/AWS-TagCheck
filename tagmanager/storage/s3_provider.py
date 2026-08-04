"""
Purpose: S3 storage backend — streams object metadata (key, size, storage
class, last-modified) from paginated ListObjectsV2, no per-object HEAD calls.
Author(s): John Reed
"""

import logging

import boto3
from botocore.exceptions import ClientError

from tagmanager.storage.base import (StorageCapabilities, StorageObject,
                                     StorageProvider)
from tagmanager.storage.diff import FetchResult

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

        for page in paginator.paginate(Bucket=container, Prefix=prefix,
                                       FetchOwner=True):
            for item in page.get("Contents", []):
                owner = item.get("Owner", {})
                yield StorageObject(
                    backend="s3",
                    container=container,
                    key=item["Key"],
                    size_bytes=item["Size"],
                    last_modified=item["LastModified"],
                    storage_class=item.get("StorageClass", "STANDARD"),
                    owner=owner.get("DisplayName") or owner.get("ID", ""),
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

    # Live-config reads for --dry-run-diff. READ-ONLY: only GET / list
    # calls, never a Put/Delete — this is the apply ladder's rung one.

    def fetch_lifecycle(self, bucket):
        """
        Read a bucket's live lifecycle configuration (read-only).

        :param bucket: bucket name
        :returns: FetchResult — rules present, or present=False on a 404
            (NoSuchLifecycleConfiguration), or unknown=True on a 403
            (AccessDenied — cannot tell drift).
        """
        client = self._session.client("s3")
        try:
            resp = client.get_bucket_lifecycle_configuration(Bucket=bucket)
        except ClientError as err:
            return _fetch_error(err)
        return FetchResult(rules=resp.get("Rules", []), present=True)

    def fetch_tiering(self, bucket):
        """
        Read a bucket's live Intelligent-Tiering configs (read-only).

        Pages the list manually (no registered paginator); an empty list
        means no live config, which is NOT an error.

        :param bucket: bucket name
        :returns: FetchResult — configs present, empty present=False, or
            unknown=True on a 403.
        """
        client = self._session.client("s3")
        configs = []
        token = None
        try:
            while True:
                kwargs = {"Bucket": bucket}
                if token:
                    kwargs["ContinuationToken"] = token
                resp = client.list_bucket_intelligent_tiering_configurations(
                    **kwargs)
                configs.extend(
                    resp.get("IntelligentTieringConfigurationList", []))
                if not resp.get("IsTruncated"):
                    break
                token = resp.get("NextContinuationToken")
        except ClientError as err:
            return _fetch_error(err)
        return FetchResult(rules=configs, present=bool(configs))


def _fetch_error(err):
    """
    Map a botocore ClientError to a FetchResult — 404 empty vs 403 unknown.

    A denied read (403) is unknown (we cannot tell drift), never conflated
    with a genuinely absent config (404 / empty). Any other code re-raises.

    :param err: the botocore ClientError
    :returns: FetchResult
    :raises ClientError: for codes other than the no-config / denied pair
    """
    code = err.response.get("Error", {}).get("Code", "")
    if code == "NoSuchLifecycleConfiguration":
        return FetchResult(rules=[], present=False)
    if code == "AccessDenied":
        return FetchResult(rules=[], present=False, unknown=True)
    raise err
