"""
Purpose: Storage age-scan CLI — a thin shell over the storage service
layer: parse flags into Options, call services, print results. All compute
lives in services.py; all console/CSV output lives here and in output.py.
Author(s): John Reed
"""

import argparse
import csv
import glob as globlib
import logging
import sys

from tagmanager.config import get_settings
from tagmanager.models.tables import StorageScanRun
from tagmanager.storage import services
from tagmanager.storage.output import (print_cost_report, print_projections,
                                       print_summary, write_cost_csv,
                                       write_csv, write_savings_csv,
                                       write_structure_proposal)
from tagmanager.storage.store import latest_complete_run, record_artifact

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.storage_cli")
LOG.setLevel(logging.INFO)


# Helpers

def parse_args(argv):
    """
    Build and run the argument parser.

    :param argv: argument list (None = sys.argv)
    :returns: parsed namespace
    """
    parser = argparse.ArgumentParser(
        prog="tagmanager-storage-scan",
        description="Scan mass storage, band objects by age, report rollups.")
    parser.add_argument("--backend", default="s3",
                        choices=["s3", "azure", "gcs", "fs"],
                        help="storage backend to scan/analyze (default s3); "
                             "fs treats --bucket as a root directory path")
    parser.add_argument("--account-url", default="",
                        help="azure backend: "
                             "https://<account>.blob.core.windows.net")
    parser.add_argument("--bucket", action="append",
                        help="bucket/container to scan (repeatable; omit "
                             "with --cost-report to price the latest run)")
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
    parser.add_argument("--emit-lifecycle", default="", metavar="DIR",
                        help="write per-bucket lifecycle config JSON + "
                             "APPLY.md into DIR (uses the latest saved run)")
    parser.add_argument("--delete-after", type=int, default=None,
                        metavar="DAYS",
                        help="add Expiration rules to --emit-lifecycle "
                             "(the async, AWS-managed mass-delete path)")
    parser.add_argument("--emit-delete-manifests", default="", metavar="DIR",
                        help="scan mode only: stream stale objects (past the "
                             "last age band) into chunked delete-objects "
                             "JSON manifests")
    parser.add_argument("--emit-tiering", default="", metavar="DIR",
                        help="write per-bucket Intelligent-Tiering configs + "
                             "APPLY.md into DIR (uses the latest saved run)")
    parser.add_argument("--emit-batch-copy", default="", metavar="DIR",
                        help="scan mode only: stream stale objects into "
                             "S3 Batch Operations copy manifests (CSV)")
    parser.add_argument("--html-report", default="", metavar="PATH",
                        help="write the storage insights HTML report "
                             "(age, cost, savings, structure, artifacts)")
    parser.add_argument("--recommend-structure", action="store_true",
                        help="derive layout recommendations from the run "
                             "and persist them for move plans/reports")
    parser.add_argument("--structure-csv", default="",
                        help="write the recommendations to this CSV path")
    parser.add_argument("--emit-structure", default="", metavar="DIR",
                        help="write PROPOSAL.md with suggested layouts + "
                             "apply guidance into DIR")
    parser.add_argument("--emit-move-plan", default="", metavar="DIR",
                        help="scan mode only: old-key,new-key move plans "
                             "from the LATEST run's recommendations "
                             "(two-pass: --recommend-structure first)")
    parser.add_argument("--rollup-owners", action="store_true",
                        help="key rollup cells by object owner too (every "
                             "distinct owner splits a prefix's cells — "
                             "cardinality cost; azure/gcs record no owner)")
    parser.add_argument("--access-logs", default="", metavar="GLOB",
                        help="scan mode only: local S3 server-access-log "
                             "files to fold into a last-read index "
                             "(ages become access-aware lower bounds)")
    return parser.parse_args(argv)


def _open_session(settings):
    """
    Session via the service-layer guard, or None with the message logged.

    :param settings: Settings
    :returns: SQLAlchemy session or None
    """
    try:
        return services.open_storage_session_maker(settings)()
    except services.SchemaOutOfDate as err:
        LOG.error("%s", err)
        return None


def _run_cost_report(session, run, args):
    """
    Build, print, and optionally CSV the cost report for one run.

    :returns: exit code — 0 OK, 4 no pricing for the backend
    """
    try:
        report = services.analyze_cost(session, run)
    except services.StorageServiceError as err:
        LOG.error("%s", err)
        return 4
    print_cost_report(report)
    if run.access_aware:
        print("(ages in this run are access-aware lower bounds)")
    if args.cost_csv:
        write_cost_csv(args.cost_csv, report)
        print(f"cost csv saved to {args.cost_csv}.")
    return 0


def _run_projections(session, run, args):
    """
    Build, print, and optionally CSV the savings projections for one run.

    :returns: exit code — 0 OK, 4 bad override map or no pricing
    """
    try:
        projections = services.analyze_projections(
            session, run, age_out_map_raw=args.age_out_map)
    except services.StorageServiceError as err:
        LOG.error("%s", err)
        return 4
    print_projections(projections)
    if run.access_aware:
        print("(ages in this run are access-aware lower bounds)")
    if args.savings_csv:
        write_savings_csv(args.savings_csv, projections)
        print(f"savings csv saved to {args.savings_csv}.")
    return 0


def _emit_lifecycle(session, run, args):
    """
    Generate per-bucket lifecycle configs into a directory, with APPLY.md.

    :returns: exit code — 0 OK, 4 nothing generated / bad input
    """
    try:
        result = services.emit_lifecycle_artifacts(
            session, run, args.emit_lifecycle,
            age_out_map_raw=args.age_out_map,
            delete_after=args.delete_after)
    except services.StorageServiceError as err:
        LOG.error("%s", err)
        return 4
    print("generating lifecycle configs...")
    for _, filename, rules in result.files:
        print(f"  {filename}: {rules} rule(s)")
    for skip in result.skips:
        print(f"  skipped: {skip}")
    print(f"lifecycle configs saved to {result.out_dir}/.")
    return 0


def _emit_tiering(session, run, args):
    """
    Generate per-bucket Intelligent-Tiering configs into a directory.

    :returns: exit code — 0 OK, 4 nothing generated
    """
    try:
        result = services.emit_tiering_artifacts(session, run,
                                                 args.emit_tiering)
    except services.StorageServiceError as err:
        LOG.error("%s", err)
        return 4
    print("generating tiering configs...")
    for bucket, ids in result.buckets:
        print(f"  {bucket}: {len(ids)} config(s)")
    for skip in result.skips:
        print(f"  skipped: {skip}")
    print(f"tiering configs saved to {result.out_dir}/.")
    return 0


def _run_structure(session, run, args):
    """
    Build, print, persist, and optionally emit structure recommendations.

    :returns: exit code — 0 OK
    """
    result = services.recommend_structure(session, run)
    recs, notes = result.recs, result.notes

    print("***********************************")
    print("*  structure recommendations      *")
    print("***********************************")
    if not recs:
        print("no reorg recommended — the layout already fits "
              "prefix-scoped lifecycle rules.")
    for rec in recs:
        loc = f"{rec.container}/{rec.prefix}" if rec.prefix else rec.container
        stake = (f"  (${rec.monthly_cost_at_stake:.2f}/mo at stake)"
                 if rec.monthly_cost_at_stake else "")
        print(f"  {rec.kind:<18} {loc}{stake}")
        print(f"      {rec.rationale}")
        if rec.top_owners:
            print(f"      top owners: {', '.join(rec.top_owners)}")
    for note in notes:
        print(f"  - {note}")
    if result.truncated:
        print(f"  (persisted top {result.persisted} by $ at "
              "stake — remainder in --structure-csv only)")

    if args.structure_csv:
        with open(args.structure_csv, "w", newline="",
                  encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["kind", "container", "prefix", "rationale",
                             "monthly_cost_at_stake", "top_owners"])
            for rec in recs:
                writer.writerow([rec.kind, rec.container, rec.prefix,
                                 rec.rationale,
                                 f"{rec.monthly_cost_at_stake:.6f}",
                                 "; ".join(rec.top_owners)])
        print(f"structure csv saved to {args.structure_csv}.")

    if args.emit_structure:
        out_dir = write_structure_proposal(args.emit_structure, recs,
                                           notes, run)
        record_artifact(session, run, "structure-proposal", out_dir,
                        {"recommendations": len(recs)})
    return 0


def _write_html_report(session, run, args):
    """
    Compose and write the storage insights HTML report for one run.

    :returns: exit code — 0 OK
    """
    services.write_html_report_file(session, run, args.html_report)
    print(f"storage report saved to {args.html_report}.")
    return 0


def _post_scan_outputs(session, run, args):
    """
    Optional analysis/artifact outputs after a scan (or on the latest run).

    :returns: exit code
    """
    steps = []
    if args.cost_report:
        steps.append(_run_cost_report)
    if args.project_savings:
        steps.append(_run_projections)
    if args.emit_lifecycle:
        steps.append(_emit_lifecycle)
    if args.emit_tiering:
        steps.append(_emit_tiering)
    if args.recommend_structure:
        steps.append(_run_structure)
    if args.html_report:
        steps.append(_write_html_report)
    for step in steps:
        rc = step(session, run, args)
        if rc:
            return rc
    return 0


def _analyze_latest(settings, args):
    """
    Report-only path: price/project the latest saved run, no scan.

    :returns: exit code — 0 OK, 4 nothing to analyze
    """
    session = _open_session(settings)
    if session is None:
        return 4
    run = latest_complete_run(session, backend=args.backend)
    if run is None:
        LOG.error("no saved storage scan runs — scan first with --bucket")
        return 4
    return _post_scan_outputs(session, run, args)


def _print_emitter_report(report):
    """
    Reproduce the classic console lines for one emitter outcome.

    :param report: services.EmitterReport
    """
    if report.kind == "delete-manifests":
        if report.disposition == "empty":
            print("no objects past the last age band — no delete manifests.")
            return
        for bucket, info in sorted(report.summary.items()):
            print(f"  {bucket}: {info['keys']} delete candidate(s) across "
                  f"{info['files']} manifest file(s)")
        print(f"delete manifests saved to {report.out_dir}/.")
        return

    if report.kind == "move-plan":
        if report.disposition == "empty":
            print("no objects matched the recommendations — no move plans.")
            return
        if report.disposition == "all_conforming":
            print(f"all {report.skipped_conforming} matched object(s) "
                  "already conform to the target layout — nothing to move.")
            return
        for bucket, info in sorted(report.summary.items()):
            print(f"  {bucket}: {info['moves']} move(s) planned")
        if report.skipped_conforming:
            print(f"  {report.skipped_conforming} object(s) already match "
                  "the target layout — skipped")
        print(f"move plans saved to {report.out_dir}/.")
        return

    # batch-copy
    if report.disposition == "empty":
        print("no objects past the last age band — no batch-copy manifests.")
        return
    for bucket, info in sorted(report.summary.items()):
        print(f"  {bucket}: {info['keys']} copy candidate(s), "
              f"{info['skipped_large']} skipped (>5 GB)")
    print(f"batch-copy manifests saved to {report.out_dir}/.")


def _scan(settings, args, provider):
    """
    Scan mode: build options, run the scan service, print everything.

    :returns: exit code — 0 OK, 4 config error
    """
    try:
        age_band_days = services.resolve_age_bands(args.age_bands, settings)
    except services.StorageServiceError as err:
        LOG.error("%s", err)
        return 4

    access_index = None
    if args.access_logs:
        log_files = sorted(globlib.glob(args.access_logs))
        if not log_files:
            LOG.error("--access-logs matched no files: %r", args.access_logs)
            return 4
        print("loading access logs...")
        access_report = services.build_access_report(log_files)
        access_index = access_report.index
        print(f"access index ready: {access_report.events} read event(s), "
              f"{access_report.keys} key(s). ages become access-aware "
              "lower bounds (log delivery is best-effort, hours of lag).")

    try:
        maker = services.open_storage_session_maker(settings)
    except services.SchemaOutOfDate as err:
        LOG.error("%s", err)
        return 4

    opts = services.ScanOptions(
        backend=args.backend,
        account_url=args.account_url,
        buckets=tuple(args.bucket),
        prefix=args.prefix,
        age_band_days=age_band_days,
        prefix_depth=args.prefix_depth,
        rollup_owners=args.rollup_owners,
        access_index=access_index,
        emit_delete_dir=args.emit_delete_manifests,
        emit_batch_copy_dir=args.emit_batch_copy,
        emit_move_plan_dir=args.emit_move_plan,
    )

    print("scanning storage...")
    try:
        result = services.run_storage_scan(maker, opts, provider=provider,
                                           settings=settings)
    except services.StorageServiceError as err:
        LOG.error("%s", err)
        return 4

    print_summary(result.builder)

    if args.csv_out:
        write_csv(args.csv_out, result.builder)
        print(f"csv saved to {args.csv_out}.")

    for report in result.emitter_reports:
        _print_emitter_report(report)

    session = maker()
    run = session.get(StorageScanRun, result.run_id)
    return _post_scan_outputs(session, run, args)


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

    if not args.bucket and not (args.cost_report or args.project_savings
                                or args.emit_lifecycle or args.emit_tiering
                                or args.recommend_structure
                                or args.html_report):
        LOG.error("nothing to do — pass --bucket to scan, or --cost-report / "
                  "--project-savings / --emit-lifecycle / --emit-tiering / "
                  "--recommend-structure / --html-report to work from the "
                  "latest saved run")
        return 4

    if (args.emit_delete_manifests or args.emit_batch_copy
            or args.emit_move_plan) and not args.bucket:
        LOG.error("key-level manifests need a scan — rollups keep no object "
                  "keys; pass --bucket")
        return 4

    if not args.bucket:
        return _analyze_latest(settings, args)
    return _scan(settings, args, provider)


if __name__ == "__main__":
    sys.exit(main())
