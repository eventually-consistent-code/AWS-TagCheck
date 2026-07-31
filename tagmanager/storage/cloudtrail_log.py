"""
Purpose: CloudTrail S3 data-event parsing — fold GetObject/SelectObjectContent
records into a per-(bucket, key) last-read index, the SAME index the S3
server-access-log parser feeds. Data events are off by default and bill per
event; absence just means no enrichment. Derived last-read times are LOWER
BOUNDS (delivery lags), never ground truth.
Author(s): John Reed
"""

import datetime
import gzip
import json
import logging

from tagmanager.storage.access_log import READ, WRITE, fold_reads

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.cloudtrail_log")
LOG.setLevel(logging.INFO)


# Constants

S3_EVENT_SOURCE = "s3.amazonaws.com"
# Object-BODY reads only — matches the access-log parser's REST.GET.OBJECT
# (which excludes HEAD). readOnly alone is NOT a filter: tagging/ACL reads
# are readOnly too, so the eventName allowlist is required.
READ_EVENT_NAMES = ("GetObject", "SelectObjectContent")
WRITE_EVENT_NAMES = ("PutObject", "CopyObject", "DeleteObject",
                     "CompleteMultipartUpload")
S3_OBJECT_RESOURCE = "AWS::S3::Object"


def _parse_time(stamp):
    """ISO-8601 UTC ('2026-07-30T14:22:09Z') -> aware datetime, or None."""
    try:
        return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _bucket_key_from_arn(resources):
    """
    (bucket, key) from the AWS::S3::Object entry's ARN, or (None, None).

    Fallback for records whose requestParameters was truncated (>100 KB).
    """
    for res in resources or []:
        if res.get("type") == S3_OBJECT_RESOURCE and res.get("ARN"):
            tail = res["ARN"].split(":::", 1)[-1]
            if "/" in tail:
                bucket, key = tail.split("/", 1)
                return bucket, key
    return None, None


def parse_record(rec):
    """
    One CloudTrail event -> (bucket, key, time, optype) or None.

    optype is READ (GetObject/SelectObjectContent) or WRITE
    (Put/Copy/Delete/CompleteMultipartUpload). Non-S3 events, other
    operations, and records missing a key are skipped.

    :param rec: one element of a CloudTrail file's "Records" array
    :returns: (bucket, key, aware datetime, optype) or None
    """
    if not isinstance(rec, dict):
        return None
    if rec.get("eventSource") != S3_EVENT_SOURCE:
        return None
    name = rec.get("eventName")
    if name in READ_EVENT_NAMES:
        optype = READ
    elif name in WRITE_EVENT_NAMES:
        optype = WRITE
    else:
        return None
    when = _parse_time(rec.get("eventTime", ""))
    if when is None:
        return None

    params = rec.get("requestParameters") or {}
    bucket = params.get("bucketName")
    key = params.get("key")
    if not key:  # requestParameters truncated -> object-ARN fallback
        bucket, key = _bucket_key_from_arn(rec.get("resources"))
    if not bucket or not key:
        return None
    return bucket, key, when, optype


def load_cloudtrail_index(paths):
    """
    Fold CloudTrail data-event files into {(bucket, key): newest read}.

    Each file is a gzipped (or plain) JSON object with a "Records" array.

    :param paths: iterable of local CloudTrail log file paths
    :returns: (index dict, records_used count)
    """
    paths = list(paths)
    index, used = fold_reads(iter_events(paths))
    LOG.info("cloudtrail index: %s read events over %s keys from %s file(s).",
             used, len(index), len(paths))
    return index, used


def iter_events(paths):
    """
    Yield every parsed op record (not None) from the CloudTrail files.

    :param paths: iterable of local CloudTrail log file paths
    :yields: (bucket, key, datetime, optype)
    """
    for path in paths:
        for rec in _iter_records(path):
            parsed = parse_record(rec)
            if parsed is not None:
                yield parsed


def _iter_records(path):
    """
    Yield the "Records" of one CloudTrail file (gzip first, then plain).

    A malformed or non-conforming file is skipped with a warning — one
    bad export never sinks the scan.
    """
    try:
        raw = _read_bytes(path)
        document = json.loads(raw)
    except (OSError, ValueError) as err:
        LOG.warning("skipping cloudtrail file %s: %s", path, err)
        return
    yield from document.get("Records", [])


def _read_bytes(path):
    """Read a file as text, transparently decompressing gzip."""
    with open(path, "rb") as handle:
        head = handle.read(2)
        handle.seek(0)
        if head == b"\x1f\x8b":  # gzip magic
            return gzip.decompress(handle.read()).decode("utf-8", "replace")
        return handle.read().decode("utf-8", "replace")
