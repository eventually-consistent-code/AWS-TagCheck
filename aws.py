#!/usr/bin/env python3

"""
Purpose: AWS session helpers for tag check — boto3 session, STS identity,
EC2 clients/regions, instance enumeration, and tag compliance checks.
Author(s): John Reed, Nick Bitzer
"""


# Imports
import logging
import os
from collections import defaultdict

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

# Exit codes shared with the entrypoint
EXIT_OK = 0
EXIT_TAG_VIOLATIONS = 1
EXIT_CREDENTIALS = 2
EXIT_ACCOUNT = 3
EXIT_CONFIG = 4

# Env var for the account guard
EXPECTED_ACCOUNT_ENV = "AWS_TAGCHECK_EXPECTED_ACCOUNT"

# Required tag keys and missing-value sentinels (legacy-friendly)
REQUIRED_TAGS = (
    ("Environment", "missing environment"),
    ("Product", "missing product"),
)

# Default: scan everything except terminated
DEFAULT_INSTANCE_FILTERS = [
    {
        "Name": "instance-state-name",
        "Values": [
            "pending",
            "running",
            "shutting-down",
            "stopping",
            "stopped",
        ],
    }
]

__all__ = [
    "EXIT_OK",
    "EXIT_TAG_VIOLATIONS",
    "EXIT_CREDENTIALS",
    "EXIT_ACCOUNT",
    "EXIT_CONFIG",
    "EXPECTED_ACCOUNT_ENV",
    "REQUIRED_TAGS",
    "DEFAULT_INSTANCE_FILTERS",
    "build_session",
    "validate_credentials",
    "assert_expected_account",
    "ec2_client",
    "list_ec2_regions",
    "check_data",
    "tags_to_dict",
    "iter_instances",
    "evaluate_required_tags",
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
    except NoCredentialsError as err:
        LOG.error("no aws credentials found in the default chain...")
        raise SystemExit(EXIT_CREDENTIALS) from err
    except PartialCredentialsError as err:
        LOG.error("incomplete aws credentials: %s", err)
        raise SystemExit(EXIT_CREDENTIALS) from err
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "ClientError")
        LOG.error("aws rejected credentials (%s): %s", code, err)
        raise SystemExit(EXIT_CREDENTIALS) from err
    except Exception as err:  # network / unexpected
        LOG.error("credential check failed: %s", err)
        raise SystemExit(EXIT_CREDENTIALS) from err

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


def tags_to_dict(instance):
    """
    Normalize an instance Tags list to a Key→Value dict.

    :param instance: describe_instances instance dict
    :returns: dict of tag key to value (empty if no tags)
    """
    tags = instance.get("Tags") or []
    return {t["Key"]: t["Value"] for t in tags if "Key" in t}


def iter_instances(session, region, filters=None):
    """
    Yield EC2 instance dicts for a region via paginated describe_instances.

    :param session: boto3.Session
    :param region: region name string
    :param filters: optional Filters list; default excludes terminated only
    :yields: instance dicts from Reservations
    """
    client = ec2_client(session, region)
    paginator = client.get_paginator("describe_instances")
    if filters is None:
        filters = DEFAULT_INSTANCE_FILTERS
    paginate_kwargs = {}
    if filters:
        paginate_kwargs["Filters"] = filters
    for page in paginator.paginate(**paginate_kwargs):
        for reservation in page.get("Reservations", []):
            yield from reservation.get("Instances", [])


def evaluate_required_tags(tag_map, canonical):
    """
    Evaluate Environment and Product tags against canonical lists.

    :param tag_map: dict of tag Key→Value
    :param canonical: dict with Environment and Product lists
    :returns: list of {tag_key, tag_value, issue} for noncompliant tags
    """
    findings = []
    for tag_key, missing_sentinel in REQUIRED_TAGS:
        allowed = canonical.get(tag_key, [])
        if tag_key not in tag_map:
            findings.append(
                {
                    "tag_key": tag_key,
                    "tag_value": missing_sentinel,
                    "issue": "missing",
                }
            )
            continue
        value = tag_map[tag_key]
        if check_data(value, allowed) is not None:
            findings.append(
                {
                    "tag_key": tag_key,
                    "tag_value": value,
                    "issue": "invalid",
                }
            )
    return findings


def parse_csv_tags(path):
    """
    Parse a CSV file of tag entries. Expected columns: resource_id, tag_key, tag_value.
    Returns a dict mapping resource_id -> { tag_key: tag_value }
    """
    import csv

    tags = defaultdict(dict)
    with open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        # Support common alternate header names
        for row in reader:
            rid = (row.get("resource_id") or row.get("instance_id") or row.get("resource") or "").strip()
            key = (row.get("tag_key") or row.get("key") or "").strip()
            value = (row.get("tag_value") or row.get("value") or "").strip()
            if not rid or not key:
                # skip malformed/empty rows
                continue
            tags[rid][key] = value
    return dict(tags)


def merge_tag_maps(aws_map, csv_map):
    """
    Merge AWS-provided tag maps and CSV-provided tag maps.

    aws_map/csv_map: dict of resource_id -> { key: value }

    Returns: (gold_map, conflicts)
      - gold_map: resource_id -> merged {key: value} (CSV value preferred when conflict)
      - conflicts: list of {resource_id, tag_key, aws_value, csv_value}

    Merge policy: when both AWS and CSV have a value and they differ, the CSV
    value is placed in the working gold_map but a conflict entry is emitted for
    interactive review.
    """
    gold = {}
    conflicts = []
    resource_ids = set(aws_map.keys()) | set(csv_map.keys())
    for rid in resource_ids:
        gold[rid] = {}
        aws_tags = aws_map.get(rid, {}) or {}
        csv_tags = csv_map.get(rid, {}) or {}
        keys = set(aws_tags.keys()) | set(csv_tags.keys())
        for k in keys:
            a = aws_tags.get(k)
            c = csv_tags.get(k)
            if a is not None and c is not None:
                if a == c:
                    gold[rid][k] = a
                else:
                    gold[rid][k] = c
                    conflicts.append({"resource_id": rid, "tag_key": k, "aws_value": a, "csv_value": c})
            elif c is not None:
                gold[rid][k] = c
            elif a is not None:
                gold[rid][k] = a
    return gold, conflicts
