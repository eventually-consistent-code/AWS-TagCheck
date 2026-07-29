"""
Purpose: Unit tests for credential and account guards (mocked).
Author(s): John Reed
"""

from unittest import mock

import boto3
import pytest
from botocore.stub import Stubber

import aws


def test_assert_expected_account_missing_env(monkeypatch):
    monkeypatch.delenv(aws.EXPECTED_ACCOUNT_ENV, raising=False)
    with pytest.raises(SystemExit) as exc:
        aws.assert_expected_account({"Account": "111111111111"})
    assert exc.value.code == aws.EXIT_CONFIG


def test_assert_expected_account_mismatch(monkeypatch):
    monkeypatch.setenv(aws.EXPECTED_ACCOUNT_ENV, "999999999999")
    with pytest.raises(SystemExit) as exc:
        aws.assert_expected_account({"Account": "111111111111"})
    assert exc.value.code == aws.EXIT_ACCOUNT


def test_assert_expected_account_match(monkeypatch):
    monkeypatch.setenv(aws.EXPECTED_ACCOUNT_ENV, "111111111111")
    aws.assert_expected_account({"Account": "111111111111"})


def test_validate_credentials_stubbed():
    session = boto3.Session(region_name="us-east-1")
    client = session.client("sts")
    stubber = Stubber(client)
    stubber.add_response(
        "get_caller_identity",
        {
            "UserId": "AIDATEST",
            "Account": "111111111111",
            "Arn": "arn:aws:iam::111111111111:user/test",
        },
    )
    with stubber:
        with mock.patch.object(session, "client", return_value=client):
            identity = aws.validate_credentials(session)
    assert identity["Account"] == "111111111111"
