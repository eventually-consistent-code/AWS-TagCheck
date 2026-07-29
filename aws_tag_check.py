#!/usr/bin/env python3

"""
Purpose: Gather tag data from AWS EC2 instances, compare against canonical
lists for environmental consistency, and report deviations. Phase 2 scans
all accessible regions and records structured noncompliance rows; HTML
report generation lands in phase 3.
Author(s): John Reed, Nick Bitzer
"""


# Imports
import json
import logging
import sys

from botocore.exceptions import ClientError

from aws import (
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_TAG_VIOLATIONS,
    assert_expected_account,
    build_session,
    evaluate_required_tags,
    iter_instances,
    list_ec2_regions,
    tags_to_dict,
    validate_credentials,
)


# Log generator
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.aws_tag_check")
LOG.setLevel(logging.INFO)

# Regions historically inaccessible with the service account
BAD_REGIONS = ["cn-north-1", "us-gov-west-1"]

# Canonical list / HTML report paths (HTML is phase 3)
CON_FILE = "canonical.json"
HTML_FILE = "index.html"


def load_canonical(path):
    """
    Load and validate the canonical Environment/Product lists.

    :param path: path to canonical.json
    :returns: dict with Environment and Product lists
    :raises SystemExit: EXIT_CONFIG on missing or malformed data
    """
    LOG.info("loading canonical data from %s...", path)
    try:
        with open(path, encoding="utf-8") as canonical_file:
            data = json.load(canonical_file)
    except FileNotFoundError:
        LOG.error("canonical file not found: %s", path)
        raise SystemExit(EXIT_CONFIG)
    except json.JSONDecodeError as err:
        LOG.error("canonical file is not valid json: %s", err)
        raise SystemExit(EXIT_CONFIG)
    except OSError as err:
        LOG.error("could not read canonical file: %s", err)
        raise SystemExit(EXIT_CONFIG)

    for key in ("Environment", "Product"):
        if key not in data or not isinstance(data[key], list):
            LOG.error("canonical file must include a list for %s...", key)
            raise SystemExit(EXIT_CONFIG)

    LOG.info(
        "canonical loaded... %s environments, %s products",
        len(data["Environment"]),
        len(data["Product"]),
    )
    return data


def scan_region(session, region, canonical):
    """
    Scan one region for Environment/Product tag violations.

    :param session: boto3.Session
    :param region: region name
    :param canonical: canonical Environment/Product lists
    :returns: (violations list, skip dict or None, instances_seen count)
    """
    violations = []
    instances_seen = 0
    LOG.info("scanning %s...", region)
    try:
        for instance in iter_instances(session, region):
            instances_seen += 1
            tag_map = tags_to_dict(instance)
            name = tag_map.get("Name") or "(no name)"
            instance_id = instance.get("InstanceId", "?")
            for finding in evaluate_required_tags(tag_map, canonical):
                violations.append(
                    {
                        "region": region,
                        "instance_id": instance_id,
                        "name": name,
                        "tag_key": finding["tag_key"],
                        "tag_value": finding["tag_value"],
                        "issue": finding["issue"],
                    }
                )
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "ClientError")
        LOG.warning("skipping region %s (%s)...", region, code)
        skip = {"region": region, "code": code, "message": str(err)}
        return [], skip, 0

    LOG.info("%s Complete... %s instance(s), %s violation(s)",
             region, instances_seen, len(violations))
    return violations, None, instances_seen


def scan_all_regions(session, regions, canonical):
    """
    Scan every region and aggregate violations + skips.

    :returns: (violations, region_skips, instances_seen)
    """
    all_violations = []
    region_skips = []
    instances_seen = 0
    for region in regions:
        violations, skip, seen = scan_region(session, region, canonical)
        all_violations.extend(violations)
        instances_seen += seen
        if skip is not None:
            region_skips.append(skip)
    return all_violations, region_skips, instances_seen


def main():
    """
    Guards → load canonical → multi-region EC2 tag scan → exit 0 or 1.
    """
    LOG.info("starting aws tag check...")

    session = build_session()
    identity = validate_credentials(session)
    assert_expected_account(identity)

    canonical = load_canonical(CON_FILE)

    LOG.info("listing ec2 regions...")
    regions = list_ec2_regions(session)
    if BAD_REGIONS:
        regions = [r for r in regions if r not in BAD_REGIONS]
    LOG.info("found %s region(s) to scan...", len(regions))

    violations, region_skips, instances_seen = scan_all_regions(
        session, regions, canonical
    )

    LOG.info(
        "scan summary... regions=%s skips=%s instances=%s violations=%s",
        len(regions),
        len(region_skips),
        instances_seen,
        len(violations),
    )
    if region_skips:
        LOG.warning(
            "skipped %s region(s): %s",
            len(region_skips),
            ", ".join(s["region"] for s in region_skips),
        )
    for row in violations:
        LOG.info(
            "violation %s %s %s %s=%s (%s)",
            row["region"],
            row["instance_id"],
            row["name"],
            row["tag_key"],
            row["tag_value"],
            row["issue"],
        )

    # Phase 3 will render violations as HTML (HTML_FILE).

    if violations:
        LOG.info("found %s tag violation(s)...", len(violations))
        sys.exit(EXIT_TAG_VIOLATIONS)

    LOG.info("all tags clean...")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
