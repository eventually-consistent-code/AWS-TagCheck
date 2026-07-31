"""
Purpose: Unit tests for S3 URI parsing, S3 read/upload helpers, CSV-from-text
parsing, and the single-pass region scan tag map.
Author(s): John Reed
"""

import datetime
from unittest import mock

import pytest
from botocore.exceptions import ClientError

import aws
from aws import (
    parse_s3_uri,
    read_s3_text,
    upload_file_to_s3,
    parse_csv_tags_text,
)
from aws_tag_manager import (
    build_report_key,
    load_canonical,
    load_csv_tags,
    scan_region,
    upload_artifacts,
)


def test_parse_s3_uri_ok():
    bucket, key = parse_s3_uri("s3://my-bucket/reports/2026-07-30.html")
    assert bucket == "my-bucket"
    assert key == "reports/2026-07-30.html"


def test_parse_s3_uri_rejects_non_s3():
    with pytest.raises(ValueError):
        parse_s3_uri("https://example.com/foo.csv")


def test_parse_s3_uri_rejects_missing_key():
    with pytest.raises(ValueError):
        parse_s3_uri("s3://bucket-only")


def test_read_s3_text():
    body = mock.Mock()
    body.read.return_value = b"resource_id,tag_key,tag_value\n"
    client = mock.Mock()
    client.get_object.return_value = {"Body": body}
    session = mock.Mock()
    session.client.return_value = client

    text = read_s3_text(session, "s3://bkt/in/tags.csv")

    session.client.assert_called_once_with("s3")
    client.get_object.assert_called_once_with(Bucket="bkt", Key="in/tags.csv")
    assert text == "resource_id,tag_key,tag_value\n"


def test_upload_file_to_s3(tmp_path):
    report = tmp_path / "index.html"
    report.write_text("<html></html>", encoding="utf-8")
    client = mock.Mock()
    session = mock.Mock()
    session.client.return_value = client

    upload_file_to_s3(
        session, "bkt", "reports/x.html", str(report), content_type="text/html"
    )

    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "bkt"
    assert kwargs["Key"] == "reports/x.html"
    assert kwargs["Body"] == b"<html></html>"
    assert kwargs["ContentType"] == "text/html"


def test_build_report_key():
    key = build_report_key(datetime.date(2026, 7, 30))
    assert key == "reports/2026-07-30.html"


def test_parse_csv_tags_text():
    text = (
        "resource_id,tag_key,tag_value\n"
        "i-abc,Environment,Prod\n"
        "i-abc,Product,Core\n"
        ",Environment,skipme\n"
    )
    tags = parse_csv_tags_text(text)
    assert tags == {"i-abc": {"Environment": "Prod", "Product": "Core"}}


def _s3_session(put_object=None):
    client = mock.Mock()
    if put_object is not None:
        client.put_object.side_effect = put_object
    session = mock.Mock()
    session.client.return_value = client
    return session, client


def test_upload_artifacts_all_ok(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "gold-list.json").write_text("{}", encoding="utf-8")
    (tmp_path / "conflicts.json").write_text("[]", encoding="utf-8")
    session, client = _s3_session()
    args = mock.Mock(
        s3_bucket="bkt", write_gold=True, csv="tags.csv", gold_output="gold-list.json"
    )

    assert upload_artifacts(session, args) is True
    assert client.put_object.call_count == 3


def test_upload_artifacts_reports_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    session, client = _s3_session(
        put_object=ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "nope"}},
            "PutObject",
        )
    )
    args = mock.Mock(s3_bucket="bkt", write_gold=False, csv=None)

    assert upload_artifacts(session, args) is False


def test_load_csv_tags_missing_file_exits():
    args = mock.Mock(csv="definitely-not-here.csv")
    with pytest.raises(SystemExit) as exc:
        load_csv_tags(mock.Mock(), args)
    assert exc.value.code == aws.EXIT_CONFIG


def test_load_csv_tags_from_s3():
    args = mock.Mock(csv="s3://bkt/in/tags.csv")
    with mock.patch(
        "aws_tag_manager.read_s3_text",
        return_value="resource_id,tag_key,tag_value\ni-abc,Environment,Prod\n",
    ):
        tags = load_csv_tags(mock.Mock(), args)
    assert tags == {"i-abc": {"Environment": "Prod"}}


def test_scan_region_returns_tag_map():
    canonical = load_canonical("canonical.json")
    instances = [
        {
            "InstanceId": "i-good",
            "Tags": [
                {"Key": "Environment", "Value": "Prod"},
                {"Key": "Product", "Value": "Core"},
            ],
        },
    ]
    with mock.patch(
        "aws_tag_manager.iter_instances",
        return_value=iter(instances),
    ):
        viol, skip, seen, tag_map = scan_region(
            mock.Mock(), "us-west-2", canonical
        )
    assert skip is None
    assert seen == 1
    assert tag_map == {
        "i-good": {"Environment": "Prod", "Product": "Core"}
    }
