"""
Purpose: Storage age-scan CLI — walk buckets, band objects by age against
user thresholds, persist rollups, and print/write the summary. The walking
skeleton for the storage lifecycle optimizer.
Author(s): John Reed
"""

import argparse
import csv
import logging
import sys

from botocore.exceptions import BotoCoreError, ClientError

from tagmanager.config import get_settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.storage.cost import build_cost_report
from tagmanager.storage.pricing import load_pricing
from tagmanager.storage.projections import project_options
from tagmanager.storage.rollup import RollupBuilder, band_labels
from tagmanager.storage.s3_provider import S3StorageProvider
from tagmanager.storage.store import (latest_complete_run, persist_rollups,
                                      schema_current, stats_for_run)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.storage_cli")
LOG.setLevel(logging.INFO)


# Helpers

def _fmt_bytes(num):
    """
    Human-readable byte count.

    :param num: byte count
    :returns: string like "1.5 GiB"
    """
    size = float(num)
    for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
        if size < 1024 or unit == "PiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} PiB"


def parse_args(argv):
    """
    Build and run the argument parser.

    :param argv: argument list (None = sys.argv)
    :returns: parsed namespace
    """
    parser = argparse.ArgumentParser(
        prog="tagmanager-storage-scan",
        description="Scan mass storage, band objects by age, report rollups.")
    parser.add_argument("--bucket", action="append",
                        help="bucket to scan (repeatable; omit with "
                             "--cost-report to price the latest saved run)")
    parser.add_argument("--prefix", default="",
                        help="only scan keys under this prefix")
    parser.add_argument("--age-bands", default="",
                        help="comma-separated day thresholds, e.g. 90,365")
    parser.add_argument("--prefix-depth", type=int, default=None,
                        help="path segments to roll prefixes up to")
    parser.add_argument("--csv-out", default="",
                        help="write the rollup summary to this CSV path")
    parser.add_argument("--cost-report", action="store_true",
                        help="price the rollups with the shipped snapshot")
    parser.add_argument("--cost-csv", default="",
                        help="write the cost report to this CSV path")
    parser.add_argument("--project-savings", action="store_true",
                        help="project per-option savings for the stale slice")
    parser.add_argument("--savings-csv", default="",
                        help="write the savings projections to this CSV path")
    parser.add_argument("--age-out-map", default="",
                        help="override age-out targets, keyed on threshold "
                             "days: e.g. 90=STANDARD_IA,365=DEEP_ARCHIVE")
    return parser.parse_args(argv)


def scan_buckets(provider, buckets, prefix, builder):
    """
    Stream every bucket through the rollup builder, isolating failures.

    :param provider: StorageProvider
    :param buckets: list of bucket names
    :param prefix: key prefix scope
    :param builder: RollupBuilder
    :returns: list of skip records for buckets that failed
    """
    skips = []
    for bucket in buckets:
        try:
            for obj in provider.list_objects(bucket, prefix=prefix):
                builder.add(obj)
            LOG.info("%s complete...", bucket)
        except (ClientError, BotoCoreError) as err:
            LOG.warning("skipping %s: %s", bucket, err)
            skips.append({"container": bucket, "error": str(err)})
    return skips


def write_csv(path, builder):
    """
    Write every rollup cell to a CSV file.

    :param path: output file path
    :param builder: RollupBuilder after the scan
    """
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["container", "prefix", "storage_class", "age_band",
                         "object_count", "total_bytes", "oldest_last_modified",
                         "small_object_count", "small_object_bytes"])
        for (container, prefix, sclass, band), stat in sorted(builder.rollups().items()):
            writer.writerow([container, prefix, sclass, band,
                             stat.object_count, stat.total_bytes,
                             stat.oldest_last_modified.isoformat()
                             if stat.oldest_last_modified else "",
                             stat.small_object_count, stat.small_object_bytes])


def print_summary(builder):
    """
    Print the age-band summary table and notable objects.

    :param builder: RollupBuilder after the scan
    """
    print("***********************************")
    print("*  storage age scan — summary     *")
    print("***********************************")
    print(f"objects: {builder.objects_seen}   "
          f"total: {_fmt_bytes(builder.bytes_seen)}")
    print("(age = last modified; last-accessed enrichment lands in phase 4)")
    print()

    totals = builder.band_totals()
    for band in band_labels(builder.age_band_days):
        stat = totals.get(band)
        if not stat:
            continue
        print(f"  {band:>10}: {stat.object_count:>10} objects  "
              f"{_fmt_bytes(stat.total_bytes):>12}")

    oldest = builder.oldest_objects()
    if oldest:
        print()
        print("oldest objects:")
        for obj in oldest[:5]:
            when = obj.last_modified.date().isoformat()
            print(f"  {when}  {_fmt_bytes(obj.size_bytes):>10}  "
                  f"s3://{obj.container}/{obj.key}")


def print_cost_report(report):
    """
    Print the cost report: top cells, band totals, grand total.

    :param report: CostReport
    """
    print("***********************************")
    print("*  storage cost report            *")
    print("***********************************")
    print(f"(estimate — list pricing, {report.region}, "
          f"snapshot {report.as_of_date})")
    print()

    for row in report.rows[:15]:
        loc = f"{row.container}/{row.prefix}" if row.prefix else row.container
        print(f"  ${row.monthly_cost:>10.2f}/mo  {row.age_band:>10}  "
              f"{row.storage_class:<14} {loc}")
    if len(report.rows) > 15:
        print(f"  ... {len(report.rows) - 15} more cells in --cost-csv")

    print()
    for band, cost in sorted(report.band_totals.items()):
        print(f"  {band:>10}: ${cost:,.2f}/mo")
    print(f"  total: ${report.total_monthly_cost:,.2f}/mo")

    if report.unknown_classes:
        print(f"  (unpriced storage classes skipped: "
              f"{', '.join(report.unknown_classes)})")


def write_cost_csv(path, report):
    """
    Write every cost row to a CSV file.

    :param path: output file path
    :param report: CostReport
    """
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["container", "prefix", "storage_class", "age_band",
                         "object_count", "total_bytes", "monthly_cost_usd"])
        for row in report.rows:
            writer.writerow([row.container, row.prefix, row.storage_class,
                             row.age_band, row.object_count, row.total_bytes,
                             f"{row.monthly_cost:.6f}"])


def print_projections(projections):
    """
    Print the per-option savings table.

    :param projections: list of OptionProjection
    """
    print("***********************************")
    print("*  savings projections            *")
    print("***********************************")
    print("(stale slice only — estimate, list pricing)")
    print()
    for proj in projections:
        flag = "  NOT RECOMMENDED" if proj.not_recommended else ""
        breakeven = (f"break-even {proj.break_even_months:.1f}mo"
                     if proj.break_even_months is not None else "no break-even")
        print(f"  {proj.option:<20} ${proj.monthly_savings:>10.2f}/mo  "
              f"${proj.annual_savings:>11.2f}/yr  "
              f"one-time ${proj.one_time_cost:.2f}  {breakeven}{flag}")
        for caveat in proj.caveats:
            print(f"      - {caveat}")
    print()


def write_savings_csv(path, projections):
    """
    Write the projections to CSV.

    :param path: output file path
    :param projections: list of OptionProjection
    """
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["option", "monthly_savings_usd", "annual_savings_usd",
                         "one_time_cost_usd", "break_even_months",
                         "not_recommended", "caveats"])
        for proj in projections:
            writer.writerow([
                proj.option, f"{proj.monthly_savings:.6f}",
                f"{proj.annual_savings:.6f}", f"{proj.one_time_cost:.6f}",
                "" if proj.break_even_months is None
                else f"{proj.break_even_months:.2f}",
                proj.not_recommended, "; ".join(proj.caveats)])


def _parse_age_out_map(raw):
    """
    Parse --age-out-map "90=STANDARD_IA,365=DEEP_ARCHIVE" into {90: ...}.

    :param raw: flag value ("" -> None)
    :returns: dict of int day -> storage class, or None
    :raises ValueError: malformed pairs
    """
    if not raw:
        return None
    mapping = {}
    for pair in raw.split(","):
        day, _, sclass = pair.partition("=")
        if not sclass:
            raise ValueError(f"bad --age-out-map entry {pair!r}")
        mapping[int(day)] = sclass.strip()
    return mapping


def _run_projections(session, run, args):
    """
    Build, print, and optionally CSV the savings projections for one run.

    :param session: SQLAlchemy session
    :param run: StorageScanRun to project from
    :param args: parsed CLI namespace
    :returns: exit code — 0 OK, 4 bad override map
    """
    pricing = load_pricing(provider="s3")
    try:
        band_targets = _parse_age_out_map(args.age_out_map)
        for sclass in (band_targets or {}).values():
            if not pricing.known_class(sclass) or sclass == "STANDARD":
                raise ValueError(
                    f"--age-out-map target {sclass!r} is not a valid "
                    "lifecycle transition destination")
        projections = project_options(stats_for_run(session, run.id), pricing,
                                      run.age_band_days,
                                      band_targets=band_targets)
    except ValueError as err:
        LOG.error("%s", err)
        return 4
    print_projections(projections)
    if args.savings_csv:
        write_savings_csv(args.savings_csv, projections)
        print(f"savings csv saved to {args.savings_csv}.")
    return 0


def _open_session(settings):
    """
    Engine + schema guard + session, or None on a stale dev DB.

    :param settings: Settings
    :returns: SQLAlchemy session or None
    """
    engine = get_engine(settings.db_url)
    create_all(engine)
    if not schema_current(engine):
        LOG.error("db schema changed — delete the dev database (%s) and "
                  "re-scan", settings.db_url)
        return None
    return session_factory(engine)()


def _run_cost_report(session, run, args):
    """
    Build, print, and optionally CSV the cost report for one run.

    :param session: SQLAlchemy session
    :param run: StorageScanRun to price
    :param args: parsed CLI namespace
    :returns: exit code — 0 OK
    """
    pricing = load_pricing(provider="s3")
    report = build_cost_report(stats_for_run(session, run.id), pricing)
    print_cost_report(report)
    if args.cost_csv:
        write_cost_csv(args.cost_csv, report)
        print(f"cost csv saved to {args.cost_csv}.")
    return 0


def _analyze_latest(settings, args):
    """
    Report-only path: price/project the latest saved run, no scan.

    :param settings: Settings
    :param args: parsed CLI namespace
    :returns: exit code — 0 OK, 4 nothing to analyze
    """
    session = _open_session(settings)
    if session is None:
        return 4
    run = latest_complete_run(session, backend="s3")
    if run is None:
        LOG.error("no saved storage scan runs — scan first with --bucket")
        return 4
    if args.cost_report:
        _run_cost_report(session, run, args)
    if args.project_savings:
        return _run_projections(session, run, args)
    return 0


def main(argv=None, provider=None):
    """
    Run the scan and/or cost report.

    Scan mode needs --bucket; --cost-report alone prices the latest saved
    run; both together scan first and price the fresh run.

    :param argv: CLI args (None = sys.argv)
    :param provider: StorageProvider override for tests
    :returns: exit code — 0 OK, 4 config error
    """
    args = parse_args(argv)
    settings = get_settings()

    if not args.bucket and not (args.cost_report or args.project_savings):
        LOG.error("nothing to do — pass --bucket to scan, --cost-report "
                  "and/or --project-savings to analyze the latest saved run")
        return 4

    if not args.bucket:
        return _analyze_latest(settings, args)

    if args.age_bands:
        try:
            age_band_days = sorted(int(part) for part in args.age_bands.split(","))
        except ValueError:
            LOG.error("bad --age-bands %r — expected e.g. 90,365", args.age_bands)
            return 4
    else:
        age_band_days = list(settings.age_band_days)

    prefix_depth = (args.prefix_depth if args.prefix_depth is not None
                    else settings.storage_prefix_depth)

    provider = provider or S3StorageProvider()
    builder = RollupBuilder(age_band_days=age_band_days,
                            prefix_depth=prefix_depth)

    # Guard the schema BEFORE the walk — a stale dev DB should fail in
    # milliseconds, not after a full bucket scan.
    session = _open_session(settings)
    if session is None:
        return 4

    print("scanning storage...")
    skips = scan_buckets(provider, args.bucket, args.prefix, builder)

    run = persist_rollups(session, builder, backend=provider.backend_name,
                          skips=skips)
    session.commit()
    LOG.info("rollups saved (run %s, status %s).", run.id, run.status)

    print_summary(builder)

    if args.csv_out:
        write_csv(args.csv_out, builder)
        print(f"csv saved to {args.csv_out}.")

    if args.cost_report:
        _run_cost_report(session, run, args)
    if args.project_savings:
        return _run_projections(session, run, args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
