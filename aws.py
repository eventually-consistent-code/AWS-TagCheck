#!/usr/bin/env python3

"""
Purpose: AWS session helpers for tag check — boto3 session, STS identity,
EC2 clients/regions, and simple tag-value membership checks.
Author(s): John Reed, Nick Bitzer
"""


# Imports
import logging
import os

import boto3
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
)


# Log generator
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.aws")
LOG.setLevel(logging.INFO)

# Exit codes shared with the entrypoint (see CONTEXT.md phase 1)
EXIT_OK = 0
EXIT_TAG_VIOLATIONS = 1  # reserved for phase 2+
EXIT_CREDENTIALS = 2
EXIT_ACCOUNT = 3
EXIT_CONFIG = 4

# Env var for the account guard
EXPECTED_ACCOUNT_ENV = "AWS_TAGCHECK_EXPECTED_ACCOUNT"

__all__ = [
    "EXIT_OK",
    "EXIT_TAG_VIOLATIONS",
    "EXIT_CREDENTIALS",
    "EXIT_ACCOUNT",
    "EXIT_CONFIG",
    "EXPECTED_ACCOUNT_ENV",
    "build_session",
    "validate_credentials",
    "assert_expected_account",
    "ec2_client",
    "list_ec2_regions",
    "check_data",
]


def build_session():
    """
    Build a boto3 session using the default credential chain.

    :returns: boto3.Session
    """
    return boto3.Session()


def validate_credentials(session):
    """
    Probe AWS credentials via STS GetCallerIdentity.

    :param session: boto3.Session
    :returns: dict with Account, UserId, Arn on success
    :raises SystemExit: exit code EXIT_CREDENTIALS on failure
    """
    LOG.info("checking credentials...")
    try:
        sts = session.client("sts")
        identity = sts.get_caller_identity()
    except NoCredentialsError:
        LOG.error("no aws credentials found in the default chain...")
        raise SystemExit(EXIT_CREDENTIALS)
    except PartialCredentialsError as err:
        LOG.error("incomplete aws credentials: %s", err)
        raise SystemExit(EXIT_CREDENTIALS)
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "ClientError")
        LOG.error("aws rejected credentials (%s): %s", code, err)
        raise SystemExit(EXIT_CREDENTIALS)
    except Exception as err:  # network / unexpected
        LOG.error("credential check failed: %s", err)
        raise SystemExit(EXIT_CREDENTIALS)

    account = identity.get("Account", "?")
    arn = identity.get("Arn", "?")
    LOG.info("credentials ok... account=%s arn=%s", account, arn)
    return identity


def assert_expected_account(identity):
    """
    Refuse to continue when the caller is not the expected AWS account.

    :param identity: dict from validate_credentials / GetCallerIdentity
    :raises SystemExit: EXIT_CONFIG if env unset, EXIT_ACCOUNT on mismatch
    """
    expected = os.environ.get(EXPECTED_ACCOUNT_ENV, "").strip()
    if not expected:
        LOG.error(
            "missing %s — set it to the 12-digit account id before running...",
            EXPECTED_ACCOUNT_ENV,
        )
        raise SystemExit(EXIT_CONFIG)

    actual = identity.get("Account", "")
    if actual != expected:
        LOG.error(
            "account guard failed... expected=%s actual=%s",
            expected,
            actual,
        )
        raise SystemExit(EXIT_ACCOUNT)

    LOG.info("account guard ok...")


def ec2_client(session, region):
    """
    EC2 client for a region.

    :param session: boto3.Session
    :param region: region name string
    :returns: EC2 client
    """
    return session.client("ec2", region_name=region)


def list_ec2_regions(session):
    """
    List EC2 region names enabled for this account (describe_regions).

    :param session: boto3.Session
    :returns: list of region name strings
    """
    client = session.client("ec2")
    response = client.describe_regions(AllRegions=False)
    names = sorted(r["RegionName"] for r in response.get("Regions", []))
    return names


def check_data(item, values):
    """
    Check if a given string exists in a given list. Matches case!

    :param item: string to be checked
    :param values: list to check string against
    :returns: the item if it is bad/missing from the list, else None
    """
    if item not in values:
        return item
    return None
