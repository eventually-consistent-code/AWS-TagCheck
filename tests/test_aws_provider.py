"""
Purpose: Unit tests for the AWS provider (stubbed Tagging API client).
Author(s): John Reed
"""

from unittest import mock

from tagmanager.providers.aws_provider import AwsProvider
from tagmanager.providers.base import ScopeConfig


def _page(arn, tags):
    return {"ResourceTagMappingList": [
        {"ResourceARN": arn, "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}]}


def test_list_resources_normalizes_arn_and_tags():
    """Test that list_resources normalizes ARN and extracts tags correctly."""
    client = mock.Mock()
    paginator = mock.Mock()
    paginator.paginate.return_value = iter([_page(
        "arn:aws:ec2:us-east-1:111122223333:instance/i-abc",
        {"Name": "web1", "Environment": "Prod"})])
    client.get_paginator.return_value = paginator
    session = mock.Mock()
    session.client.return_value = client

    provider = AwsProvider(session_builder=lambda scope, region: session)
    scope = ScopeConfig(cloud="aws", scope_id="111122223333",
                        credentials={}, regions=["us-east-1"])
    resources = list(provider.list_resources(scope))

    assert len(resources) == 1
    res = resources[0]
    assert res.rtype == "ec2:instance"
    assert res.resource_id == "arn:aws:ec2:us-east-1:111122223333:instance/i-abc"
    assert res.name == "web1"
    assert res.tags["Environment"] == "Prod"
    assert res.region == "us-east-1"


def test_capabilities_direct_write():
    """Test that AWS provider reports direct write capability."""
    provider = AwsProvider(session_builder=lambda scope, region: mock.Mock())
    assert provider.capabilities().supports_direct_write is True
