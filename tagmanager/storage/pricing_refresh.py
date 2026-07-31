"""
Purpose: Refresh the shipped pricing snapshot from the public AWS Price List
bulk files — no credentials, one ~500 KB regional JSON. Updates storage
rates in place, keeps fee/constraint metadata, stamps as_of_date, and prints
what changed so price drift lands as a reviewable git diff.
Author(s): John Reed
"""

import argparse
import datetime
import json
import logging
import sys
import urllib.request

from tagmanager.storage.pricing import DATA_DIR

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.pricing_refresh")
LOG.setLevel(logging.INFO)


# Constants

REGION_URL = ("https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
              "AmazonS3/current/{region}/index.json")

# Bulk-file volumeType attribute -> our storage class keys.
VOLUME_TYPE_MAP = {
    "Standard": "STANDARD",
    "Standard - Infrequent Access": "STANDARD_IA",
    "One Zone - Infrequent Access": "ONEZONE_IA",
    "Intelligent-Tiering Frequent Access": "INTELLIGENT_TIERING",
    "Glacier Instant Retrieval": "GLACIER_IR",
    "Amazon Glacier": "GLACIER",
    "Glacier Deep Archive": "DEEP_ARCHIVE",
}

GB_PER_TB = 1024


def extract_storage_rates(offer):
    """
    Flatten a bulk offer file into storage-class rate ladders.

    Joins products (SKU -> volumeType) to terms.OnDemand priceDimensions
    (beginRange/endRange in GB, pricePerUnit GB-Mo).

    :param offer: parsed regional offer JSON
    :returns: dict of storage class -> sorted [[lower_gb, upper_gb|None, rate], ...]
    """
    sku_to_class = {}
    for sku, product in offer.get("products", {}).items():
        if product.get("productFamily") != "Storage":
            continue
        vtype = product.get("attributes", {}).get("volumeType", "")
        if vtype in VOLUME_TYPE_MAP:
            sku_to_class[sku] = VOLUME_TYPE_MAP[vtype]

    ladders = {}
    for sku, sclass in sku_to_class.items():
        for term in offer.get("terms", {}).get("OnDemand", {}).get(sku, {}).values():
            for dim in term.get("priceDimensions", {}).values():
                if dim.get("unit") != "GB-Mo":
                    continue
                lower = float(dim["beginRange"])
                upper = (None if dim["endRange"] == "Inf"
                         else float(dim["endRange"]))
                rate = float(dim["pricePerUnit"]["USD"])
                ladders.setdefault(sclass, []).append([lower, upper, rate])

    for ladder in ladders.values():
        ladder.sort(key=lambda tier: tier[0])
    return ladders


def apply_rates(snapshot, ladders):
    """
    Merge fresh rate ladders into the snapshot, preserving metadata.

    Single-tier ladders collapse to rate_per_gb_month; multi-tier keep
    tier_ranges_gb. Classes absent from the bulk file keep their shipped
    values (the Deep Archive standalone SKU has been seen missing — warn,
    never drop).

    :param snapshot: current snapshot dict (mutated)
    :param ladders: extract_storage_rates() output
    :returns: list of human-readable change lines
    """
    changes = []
    for sclass, entry in snapshot["classes"].items():
        ladder = ladders.get(sclass)
        if not ladder:
            LOG.warning("bulk file has no %s storage SKU — keeping shipped "
                        "rate (known gap, re-check pricing page)", sclass)
            continue

        old = entry.get("tier_ranges_gb") or entry.get("rate_per_gb_month")
        if len(ladder) == 1:
            new_value = ladder[0][2]
            entry.pop("tier_ranges_gb", None)
            entry["rate_per_gb_month"] = new_value
        else:
            new_value = ladder
            entry.pop("rate_per_gb_month", None)
            entry["tier_ranges_gb"] = new_value

        if old != new_value:
            changes.append(f"{sclass}: {old} -> {new_value}")
    return changes


def refresh(region, fetch=None):
    """
    Refresh the s3 snapshot for one region.

    :param region: AWS region code
    :param fetch: callable(url) -> parsed JSON (default: urllib GET)
    :returns: exit code — 0 refreshed, 1 fetch/parse failure
    """
    url = REGION_URL.format(region=region)

    def _default_fetch(target):
        with urllib.request.urlopen(target) as resp:  # nosec B310 - fixed https host
            return json.load(resp)

    fetch = fetch or _default_fetch

    print("fetching bulk pricing file...")
    try:
        offer = fetch(url)
    except Exception as err:  # pylint: disable=broad-exception-caught
        LOG.error("fetch failed for %s: %s", url, err)
        return 1

    path = DATA_DIR / "s3_pricing.json"
    with open(path, encoding="utf-8") as handle:
        snapshot = json.load(handle)

    ladders = extract_storage_rates(offer)
    changes = apply_rates(snapshot, ladders)

    if region != snapshot.get("region"):
        LOG.warning("storage rates refreshed for %s, but fee/monitoring/"
                    "retrieval data still reflects the %s baseline — verify "
                    "fees before trusting projections in this region",
                    region, snapshot.get("region"))
        snapshot["fee_data_region"] = snapshot.get("region")
    snapshot["region"] = region
    snapshot["as_of_date"] = datetime.date.today().isoformat()
    snapshot["source"] = url

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2)
        handle.write("\n")

    if changes:
        print("rate changes:")
        for line in changes:
            print(f"  {line}")
    else:
        print("no rate changes.")
    print(f"snapshot saved ({path.name}, {region}, {snapshot['as_of_date']}).")
    return 0


def main(argv=None):
    """
    CLI entrypoint.

    :param argv: args (None = sys.argv)
    :returns: exit code
    """
    parser = argparse.ArgumentParser(
        prog="tagmanager-pricing-refresh",
        description="Refresh the shipped S3 pricing snapshot from the "
                    "public AWS Price List bulk files.")
    parser.add_argument("--region", default="us-east-1",
                        help="region to refresh pricing for")
    args = parser.parse_args(argv)
    return refresh(args.region)


if __name__ == "__main__":
    sys.exit(main())
