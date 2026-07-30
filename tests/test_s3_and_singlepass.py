"""
Purpose: Unit tests for S3 URI parsing, S3 read/upload helpers, CSV-from-text
parsing, and the single-pass region scan tag map.
Author(s): John Reed
"""

import datetime
from unittest import mock

import pytest

import aws
from aws import (
    parse_s3_uri,
    read_s3_text,
    upload_file_to_s3,
    parse_csv_tags_text,
)
from aws_tag_check import build_report_key, load_canonical, scan_region


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
        "aws_tag_check.iter_instances",
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
