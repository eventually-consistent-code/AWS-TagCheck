"""
Purpose: Tests for the S3 storage provider (mocked paginator) and the
storage-scan CLI end-to-end (scan -> rollup -> persist -> CSV).
Author(s): John Reed
"""

import csv
import datetime
from unittest import mock

from tagmanager.storage import cli
from tagmanager.storage.base import StorageObject
from tagmanager.storage.s3_provider import S3StorageProvider

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)


def _mock_session(pages):
    """Build a boto3 Session mock whose s3 paginator yields the given pages."""
    session = mock.Mock()
    client = mock.Mock()
    paginator = mock.Mock()
    paginator.paginate.return_value = iter(pages)
    client.get_paginator.return_value = paginator
    session.client.return_value = client
    return session, client, paginator


def test_s3_provider_yields_normalized_objects():
    """Listing pages map straight onto StorageObject fields."""
    pages = [
        {"Contents": [
            {"Key": "logs/a.log", "Size": 10,
             "LastModified": NOW - datetime.timedelta(days=5)},
            {"Key": "logs/b.log", "Size": 20,
             "LastModified": NOW - datetime.timedelta(days=500),
             "StorageClass": "GLACIER"},
        ]},
        {"Contents": [
            {"Key": "data/c.bin", "Size": 30,
             "LastModified": NOW - datetime.timedelta(days=100)},
        ]},
    ]
    session, client, paginator = _mock_session(pages)

    objs = list(S3StorageProvider(session=session).list_objects("bkt", prefix="p/"))

    assert [o.key for o in objs] == ["logs/a.log", "logs/b.log", "data/c.bin"]
    assert objs[0].storage_class == "STANDARD"
    assert objs[1].storage_class == "GLACIER"
    assert all(o.backend == "s3" and o.container == "bkt" for o in objs)
    client.get_paginator.assert_called_once_with("list_objects_v2")
    paginator.paginate.assert_called_once_with(Bucket="bkt", Prefix="p/",
                                               FetchOwner=True)


def test_s3_provider_handles_empty_bucket():
    """A page with no Contents yields nothing."""
    session, _, _ = _mock_session([{}])
    assert not list(S3StorageProvider(session=session).list_objects("empty"))


def test_s3_capabilities():
    """S3 reports storage classes but no last-access until phase 4."""
    caps = S3StorageProvider(session=mock.Mock()).capabilities()
    assert caps.supports_storage_class is True
    assert caps.supports_last_access is False


class _FakeProvider:
    """In-memory StorageProvider standing in for S3 in CLI tests."""

    backend_name = "s3"

    def __init__(self, objects_by_bucket):
        self._objects = objects_by_bucket

    def list_objects(self, container, prefix=""):
        """Yield canned objects; raise for buckets marked as errors."""
        items = self._objects[container]
        if isinstance(items, Exception):
            raise items
        yield from items

    def capabilities(self):
        """Match the real provider's phase-1 surface."""
        raise NotImplementedError


def _aged_obj(bucket, key, days_old, size):
    return StorageObject(
        backend="s3", container=bucket, key=key, size_bytes=size,
        last_modified=datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=days_old))


def test_cli_end_to_end(tmp_path, monkeypatch):
    """Scan two buckets, persist to sqlite, write CSV, exit 0."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    provider = _FakeProvider({
        "warm": [_aged_obj("warm", "app/current.log", 5, 100)],
        "cold": [_aged_obj("cold", "backups/2019/dump.tar", 800, 5000)],
    })
    csv_path = tmp_path / "out.csv"

    rc = cli.main(["--bucket", "warm", "--bucket", "cold",
                   "--age-bands", "90,365",
                   "--csv-out", str(csv_path)],
                  provider=provider)

    assert rc == 0
    with open(csv_path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    bands = {row["age_band"] for row in rows}
    assert bands == {"<90d", ">365d"}
    cold_row = next(r for r in rows if r["age_band"] == ">365d")
    assert cold_row["container"] == "cold"
    assert cold_row["total_bytes"] == "5000"


def test_cli_isolates_bucket_failures(tmp_path, monkeypatch, capsys):
    """One denied bucket becomes a skip; the run still completes."""
    from botocore.exceptions import ClientError  # pylint: disable=import-outside-toplevel

    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    denied = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}},
                         "ListObjectsV2")
    provider = _FakeProvider({
        "ok": [_aged_obj("ok", "a/x", 5, 10)],
        "denied": denied,
    })

    rc = cli.main(["--bucket", "ok", "--bucket", "denied"], provider=provider)

    assert rc == 0
    out = capsys.readouterr().out
    assert "summary" in out


def test_cli_rejects_bad_age_bands(tmp_path, monkeypatch):
    """Garbage --age-bands is a config error, exit 4."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    provider = _FakeProvider({})
    rc = cli.main(["--bucket", "x", "--age-bands", "banana"], provider=provider)
    assert rc == 4
