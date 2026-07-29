#!/usr/bin/env python3

"""
Purpose: Gather tag data from AWS EC2 instances, compare against canonical
lists for environmental consistency, and report deviations. Phase 1 ships
the packaging + credential/account guards + EC2 region smoke path; full
scan and HTML report land in later phases.
Author(s): John Reed, Nick Bitzer
"""


# Imports
import logging
import sys

from aws import (
    EXIT_OK,
    assert_expected_account,
    build_session,
    list_ec2_regions,
    validate_credentials,
)


# Log generator
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.aws_tag_check")
LOG.setLevel(logging.INFO)

# Regions historically inaccessible with the service account (phase 2 may use)
BAD_REGIONS = ["cn-north-1", "us-gov-west-1"]

# Canonical list / HTML report paths (phase 2 / 3)
CON_FILE = "canonical.json"
HTML_FILE = "index.html"


def main():
    """
    Phase 1 walking skeleton: credentials → account guard → EC2 region smoke.
    """
    LOG.info("starting aws tag check guards...")

    session = build_session()
    identity = validate_credentials(session)
    assert_expected_account(identity)

    # Prove boto3 EC2 wiring (read-only); full instance scan is phase 2
    LOG.info("listing ec2 regions (smoke)...")
    regions = list_ec2_regions(session)
    if BAD_REGIONS:
        regions = [r for r in regions if r not in BAD_REGIONS]
    LOG.info("found %s region(s)...", len(regions))

    LOG.info("guards passed...")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
