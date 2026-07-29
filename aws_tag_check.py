#!/usr/bin/env python3

"""
Purpose: Gather tag data from AWS EC2 instances, compare against canonical
lists for environmental consistency, and report deviations as logs plus an
HTML report (index.html).
Author(s): John Reed, Nick Bitzer
"""


# Imports
import datetime
import html
import json
import logging
import os
import sys
from collections import defaultdict

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

# Canonical list / HTML report paths
CON_FILE = "canonical.json"
HTML_FILE = "index.html"

# Optional extra guidance link (no hard-coded org URLs)
GUIDANCE_URL_ENV = "AWS_TAGCHECK_GUIDANCE_URL"

REPORT_TITLE = "AWS Tag Check Report"

GUIDANCE_LINES = (
    "All EC2 instances must have Environment and Product tags whose values "
    "match the allowed lists in canonical.json.",
    "If a field shows a missing sentinel, add the tag on the instance "
    "(console, CLI, or infrastructure-as-code).",
    "If a field shows an invalid value, correct the tag to a canonical value "
    "or request the list be updated through your normal change process.",
    "A plus was used historically to mean 'ok' in one column; this report "
    "lists only noncompliant tags, one row per tag.",
)


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
    except FileNotFoundError as err:
        LOG.error("canonical file not found: %s", path)
        raise SystemExit(EXIT_CONFIG) from err
    except json.JSONDecodeError as err:
        LOG.error("canonical file is not valid json: %s", err)
        raise SystemExit(EXIT_CONFIG) from err
    except OSError as err:
        LOG.error("could not read canonical file: %s", err)
        raise SystemExit(EXIT_CONFIG) from err

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

    LOG.info(
        "%s Complete... %s instance(s), %s violation(s)",
        region,
        instances_seen,
        len(violations),
    )
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


def _group_violations_by_region(violations):
    """
    Group violation rows by region name (sorted keys).

    :param violations: list of violation dicts
    :returns: ordered dict-like mapping region → rows
    """
    grouped = defaultdict(list)
    for row in violations:
        grouped[row["region"]].append(row)
    return {region: grouped[region] for region in sorted(grouped)}


def render_html_report(violations, run_date, *, summary=None, guidance_url=None):
    """
    Build an HTML report string from violation rows.

    Only regions with ≥1 violation get a table section (empty-region suppress).

    :param violations: list of violation dicts
    :param run_date: date or datetime for the header
    :param summary: optional dict with regions_scanned, instances_seen, region_skips
    :param guidance_url: optional extra documentation URL
    :returns: full HTML document as str
    """
    if summary is None:
        summary = {}
    regions_scanned = int(summary.get("regions_scanned", 0))
    instances_seen = int(summary.get("instances_seen", 0))
    region_skips = summary.get("region_skips") or []

    date_str = (
        run_date.isoformat()
        if hasattr(run_date, "isoformat")
        else str(run_date)
    )
    parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(REPORT_TITLE)}</title>",
        "</head>",
        "<body>",
        f"<h1><u>{html.escape(REPORT_TITLE)}</u></h1>",
        f"<h2><u>{html.escape(date_str)}</u></h2>",
        "<pre>",
        "*******************************************************************************",
    ]
    for line in GUIDANCE_LINES:
        parts.append(f"* {html.escape(line)}")
    if guidance_url:
        parts.append(
            f"* More detail: "
            f'<a href="{html.escape(guidance_url, quote=True)}">'
            f"{html.escape(guidance_url)}</a>"
        )
    parts.extend(
        [
            "*",
            f"* Regions scanned: {regions_scanned}",
            f"* Instances examined: {instances_seen}",
            f"* Violations: {len(violations)}",
            f"* Regions skipped: {len(region_skips)}",
            "*******************************************************************************",
            "</pre>",
            "<hr>",
        ]
    )

    if region_skips:
        skip_names = ", ".join(
            html.escape(s.get("region", "?")) for s in region_skips
        )
        parts.append(f"<p><em>Skipped regions: {skip_names}</em></p>")

    if not violations:
        parts.append("<p><strong>All tags clean — no deviations found.</strong></p>")
    else:
        by_region = _group_violations_by_region(violations)
        for region, rows in by_region.items():
            parts.append(f"<h2>Region {html.escape(region)}</h2>")
            parts.append("<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\">")
            parts.append(
                "<tr>"
                "<th>Instance ID</th>"
                "<th>Name</th>"
                "<th>Tag</th>"
                "<th>Value</th>"
                "<th>Issue</th>"
                "</tr>"
            )
            for row in rows:
                parts.append(
                    "<tr>"
                    f"<td>{html.escape(str(row.get('instance_id', '')))}</td>"
                    f"<td>{html.escape(str(row.get('name', '')))}</td>"
                    f"<td>{html.escape(str(row.get('tag_key', '')))}</td>"
                    f"<td>{html.escape(str(row.get('tag_value', '')))}</td>"
                    f"<td>{html.escape(str(row.get('issue', '')))}</td>"
                    "</tr>"
                )
            parts.append("</table>")

    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def write_html_report(path, html_body):
    """
    Write the HTML report to disk (overwrite).

    :param path: output file path
    :param html_body: full HTML document string
    """
    LOG.info("writing html report...")
    with open(path, "w", encoding="utf-8") as report_file:
        report_file.write(html_body)
    LOG.info("html report saved... %s", path)


def main():
    """
    Guards → load canonical → multi-region EC2 tag scan → HTML report → exit 0/1.
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

    guidance_url = os.environ.get(GUIDANCE_URL_ENV, "").strip() or None
    report = render_html_report(
        violations,
        datetime.date.today(),
        summary={
            "regions_scanned": len(regions),
            "instances_seen": instances_seen,
            "region_skips": region_skips,
        },
        guidance_url=guidance_url,
    )
    write_html_report(HTML_FILE, report)

    if violations:
        LOG.info("found %s tag violation(s)...", len(violations))
        sys.exit(EXIT_TAG_VIOLATIONS)

    LOG.info("all tags clean...")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
