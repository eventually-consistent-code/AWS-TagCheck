"""
Purpose: Tests for CloudTrail data-event ingestion — record parsing
(incl. ARN fallback and exclude cases), gzip + plain files, the two-source
merge into one index, and the --cloudtrail-logs CLI path.
Author(s): John Reed
"""

import datetime
import gzip
import json

from tagmanager.storage import cli, services
from tagmanager.storage.base import StorageObject
from tagmanager.storage.cloudtrail_log import (load_cloudtrail_index,
                                               parse_record)

NOW = datetime.datetime.now(datetime.timezone.utc)


def _event(name="GetObject", bucket="bkt", key="logs/old.log",
           when="2026-07-30T14:22:09Z", source="s3.amazonaws.com",
           with_params=True, resources=None):
    rec = {"eventSource": source, "eventName": name, "eventTime": when,
           "readOnly": True}
    if with_params:
        rec["requestParameters"] = {"bucketName": bucket, "key": key}
    if resources is not None:
        rec["resources"] = resources
    return rec


def test_parse_record_getobject():
    """A GetObject data event yields (bucket, key, time, 'read')."""
    bucket, key, when, optype = parse_record(_event())
    assert bucket == "bkt"
    assert key == "logs/old.log"
    assert when == datetime.datetime(2026, 7, 30, 14, 22, 9,
                                     tzinfo=datetime.timezone.utc)
    assert optype == "read"


def test_parse_record_select_object_content_counts():
    """SelectObjectContent is a content read too."""
    parsed = parse_record(_event(name="SelectObjectContent"))
    assert parsed is not None and parsed[3] == "read"


def test_parse_record_classifies_writes():
    """Put/Copy/Delete/CompleteMultipartUpload parse as writes."""
    for name in ("PutObject", "CopyObject", "DeleteObject",
                 "CompleteMultipartUpload"):
        parsed = parse_record(_event(name=name))
        assert parsed is not None and parsed[3] == "write", name


def test_parse_record_excludes_metadata_and_non_s3():
    """HeadObject/tagging/ACL/list and non-s3 events are skipped."""
    for name in ("HeadObject", "GetObjectTagging", "GetObjectAcl",
                 "ListObjects"):
        assert parse_record(_event(name=name)) is None
    assert parse_record(_event(source="ec2.amazonaws.com")) is None
    assert parse_record({"not": "an event"}) is None
    assert parse_record(_event(when="garbage")) is None


def test_parse_record_arn_fallback():
    """Truncated requestParameters -> bucket/key from the object ARN."""
    rec = _event(with_params=False, resources=[
        {"type": "AWS::S3::Bucket", "ARN": "arn:aws:s3:::bkt"},
        {"type": "AWS::S3::Object",
         "ARN": "arn:aws:s3:::bkt/reports/2026/q2.pdf"}])
    bucket, key, _, optype = parse_record(rec)
    assert bucket == "bkt"
    assert key == "reports/2026/q2.pdf"
    assert optype == "read"


def test_load_cloudtrail_index_gzip_and_newest(tmp_path):
    """Gzipped file folds; duplicate keys keep the newest read."""
    older = _event(when="2026-01-01T00:00:00Z")
    newer = _event(when="2026-07-30T14:22:09Z")
    other = _event(key="data/x.csv", when="2026-06-01T00:00:00Z")
    doc = {"Records": [older, newer, other,
                       _event(name="PutObject")]}  # write ignored
    path = tmp_path / "111_CloudTrail_us-east-1_x.json.gz"
    path.write_bytes(gzip.compress(json.dumps(doc).encode()))

    index, used = load_cloudtrail_index([str(path)])
    assert used == 3
    assert index[("bkt", "logs/old.log")].month == 7  # newest kept
    assert ("bkt", "data/x.csv") in index


def test_load_cloudtrail_index_plain_json_and_bad_file(tmp_path):
    """Plain .json parses; a malformed file is skipped, not fatal."""
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"Records": [_event()]}), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    index, used = load_cloudtrail_index([str(good), str(bad)])
    assert used == 1
    assert ("bkt", "logs/old.log") in index


def test_build_access_report_merges_sources(tmp_path):
    """Access-log + CloudTrail merge into one index; newest wins; sources
    recorded."""
    ct = tmp_path / "trail.json"
    ct.write_text(json.dumps({"Records": [
        _event(bucket="b", key="k", when="2026-07-01T00:00:00Z")]}),
        encoding="utf-8")
    # S3 access log line for the SAME key, but NEWER
    access = tmp_path / "access.log"
    access.write_text(
        "o b [30/Jul/2026:10:00:00 +0000] ip req id REST.GET.OBJECT k "
        '"GET /b/k HTTP/1.1" 200 - 1 1 1 1 "-" "c" - t= v c a h T - -\n',
        encoding="utf-8")

    report = services.build_access_report(
        access_log_paths=[str(access)], cloudtrail_paths=[str(ct)])
    assert set(report.sources) == {"S3 access logs", "CloudTrail"}
    assert report.index[("b", "k")].day == 30  # access-log read is newer
    assert report.events == 2


def test_cli_cloudtrail_enrichment_flips_fresh(tmp_path, monkeypatch, capsys):
    """--cloudtrail-logs alone flips a stale-by-mtime object fresh and
    prints the cost caveat + source name."""
    monkeypatch.setenv("TAGMANAGER_DB_URL",
                       f"sqlite:///{tmp_path / 'scan.db'}")
    recent = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    trail = tmp_path / "trail.json"
    trail.write_text(json.dumps({"Records": [
        _event(bucket="bkt", key="reports/old.pdf", when=recent)]}),
        encoding="utf-8")
    now = datetime.datetime.now(datetime.timezone.utc)

    class _Provider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            yield StorageObject(backend="s3", container=container,
                                key="reports/old.pdf", size_bytes=1024,
                                last_modified=now - datetime.timedelta(days=700))

        def capabilities(self):
            raise NotImplementedError

    rc = cli.main(["--bucket", "bkt", "--cloudtrail-logs", str(trail)],
                  provider=_Provider())
    assert rc == 0
    out = capsys.readouterr().out
    assert "bill per event" in out
    assert "CloudTrail" in out
    assert "<90d" in out       # flipped fresh by the recent read

    assert cli.main(["--bucket", "b", "--cloudtrail-logs",
                     str(tmp_path / "none*.json")]) == 4
