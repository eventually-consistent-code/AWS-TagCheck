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

    # Verify exact AWS API call arguments
    session.client.assert_called_once_with("resourcegroupstaggingapi")
    client.get_paginator.assert_called_once_with("get_resources")


def test_capabilities_direct_write():
    """Test that AWS provider reports direct write capability."""
    provider = AwsProvider(session_builder=lambda scope, region: mock.Mock())
    assert provider.capabilities().supports_direct_write is True


@mock.patch("tagmanager.providers.aws_provider.boto3")
def test_default_session_builder_with_assume_role(mock_boto3):
    """Test session builder assumes role when role_arn is configured."""
    # Mock STS and Session
    sts_client = mock.Mock()
    mock_boto3.client.return_value = sts_client
    session_obj = mock.Mock()
    mock_boto3.Session.return_value = session_obj

    # Configure STS assume_role response
    sts_client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "AKIA123456789",
            "SecretAccessKey": "secret-key",
            "SessionToken": "token-xyz"
        }
    }

    # Import here to use the mocked boto3
    # pylint: disable=import-outside-toplevel
    from tagmanager.providers.aws_provider import _default_session_builder

    scope = ScopeConfig(
        cloud="aws",
        scope_id="111122223333",
        credentials={"role_arn": "arn:aws:iam::111122223333:role/TagManagerRole"},
        regions=["us-east-1"]
    )

    result = _default_session_builder(scope, "us-east-1")

    # Verify STS.assume_role was called with correct params
    sts_client.assume_role.assert_called_once_with(
        RoleArn="arn:aws:iam::111122223333:role/TagManagerRole",
        RoleSessionName="tagmanager"
    )

    # Verify boto3.Session was called with temp credentials
    mock_boto3.Session.assert_called_once_with(
        aws_access_key_id="AKIA123456789",
        aws_secret_access_key="secret-key",
        aws_session_token="token-xyz",
        region_name="us-east-1"
    )

    assert result == session_obj


@mock.patch("tagmanager.providers.aws_provider.boto3")
def test_default_session_builder_with_default_chain(mock_boto3):
    """Test session builder uses default credential chain when no role_arn."""
    session_obj = mock.Mock()
    mock_boto3.Session.return_value = session_obj

    # Import here to use the mocked boto3
    # pylint: disable=import-outside-toplevel
    from tagmanager.providers.aws_provider import _default_session_builder

    scope = ScopeConfig(
        cloud="aws",
        scope_id="111122223333",
        credentials={},
        regions=["us-west-2"]
    )

    result = _default_session_builder(scope, "us-west-2")

    # Verify no STS call was made
    mock_boto3.client.assert_not_called()

    # Verify boto3.Session was called with only region_name
    mock_boto3.Session.assert_called_once_with(region_name="us-west-2")

    assert result == session_obj
