"""
Purpose: Unit tests for canonical load and region scan (mocked AWS).
Author(s): John Reed
"""

from unittest import mock

import pytest
from botocore.exceptions import ClientError

import aws
from aws_tag_check import load_canonical, scan_region


def test_load_canonical_ok():
    data = load_canonical("canonical.json")
    assert isinstance(data["Environment"], list)
    assert isinstance(data["Product"], list)


def test_load_canonical_missing(tmp_path):
    with pytest.raises(SystemExit) as exc:
        load_canonical(str(tmp_path / "nope.json"))
    assert exc.value.code == aws.EXIT_CONFIG


def test_load_canonical_bad_shape(tmp_path):
    bad = tmp_path / "canonical.json"
    bad.write_text('{"Environment": "not-a-list"}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_canonical(str(bad))
    assert exc.value.code == aws.EXIT_CONFIG


def test_scan_region_skip_on_client_error():
    canonical = load_canonical("canonical.json")
    with mock.patch(
        "aws_tag_check.iter_instances",
        side_effect=ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "nope"}},
            "DescribeInstances",
        ),
    ):
        viol, skip, seen = scan_region(mock.Mock(), "us-east-1", canonical)
    assert viol == []
    assert seen == 0
    assert skip["code"] == "UnauthorizedOperation"


def test_scan_region_findings():
    canonical = load_canonical("canonical.json")
    instances = [
        {
            "InstanceId": "i-good",
            "Tags": [
                {"Key": "Name", "Value": "ok"},
                {"Key": "Environment", "Value": "Prod"},
                {"Key": "Product", "Value": "Core"},
            ],
        },
        {
            "InstanceId": "i-bad",
            "Tags": [{"Key": "Environment", "Value": "nope"}],
        },
    ]
    with mock.patch(
        "aws_tag_check.iter_instances",
        return_value=iter(instances),
    ):
        viol, skip, seen = scan_region(mock.Mock(), "us-west-2", canonical)
    assert skip is None
    assert seen == 2
    assert not any(v["instance_id"] == "i-good" for v in viol)
    assert any(
        v["instance_id"] == "i-bad"
        and v["tag_key"] == "Environment"
        and v["issue"] == "invalid"
        for v in viol
    )
    assert any(
        v["instance_id"] == "i-bad"
        and v["tag_key"] == "Product"
        and v["issue"] == "missing"
        for v in viol
    )
