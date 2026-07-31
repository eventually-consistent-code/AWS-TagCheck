"""
Purpose: Storage age-scan CLI — walk buckets, band objects by age against
user thresholds, persist rollups, and print/write the summary. The walking
skeleton for the storage lifecycle optimizer.
Author(s): John Reed
"""

import argparse
import csv
import glob as globlib
import json
import logging
import pathlib
import sys
from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError

from tagmanager.config import get_settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.storage.cost import build_cost_report
from tagmanager.storage.html_report import render_storage_report
from tagmanager.storage.lifecycle_gen import (APPLY_HEADER,
                                              build_lifecycle_configs)
from tagmanager.storage.manifests import (DELETE_APPLY_NOTES,
                                          BatchCopyEmitter,
                                          DeleteManifestEmitter,
                                          MoveManifestEmitter)
from tagmanager.storage.output import (print_cost_report, print_projections,
                                       print_summary, write_cost_csv,
                                       write_csv, write_savings_csv,
                                       write_structure_proposal)
from tagmanager.storage.structure import (build_recommendations,
                                          recs_to_json)
from tagmanager.storage.tiering_gen import (TIERING_APPLY_NOTE,
                                            build_tiering_configs)
from tagmanager.storage.pricing import load_pricing
from tagmanager.storage.projections import project_options
from tagmanager.storage.access_log import load_access_index
from tagmanager.storage.azure_provider import AzureBlobStorageProvider
from tagmanager.storage.fs_provider import FilesystemStorageProvider
from tagmanager.storage.gcs_provider import GcsStorageProvider
from tagmanager.storage.rollup import RollupBuilder
from tagmanager.storage.s3_provider import S3StorageProvider
from tagmanager.storage.store import (latest_complete_run, persist_rollups,
                                      record_artifact, schema_current,
                                      stats_for_run)

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


@dataclass
class ScanExtras:
    """Optional per-object hooks riding along on a scan."""

    emitters: tuple = ()
    access_index: dict = None


def scan_buckets(provider, buckets, prefix, builder, extras=None):
    """
    Stream every bucket through the rollup builder, isolating failures.

    :param provider: StorageProvider
    :param buckets: list of bucket names
    :param prefix: key prefix scope
    :param builder: RollupBuilder
    :param extras: ScanExtras — manifest emitters offered every object,
        and an optional {(bucket, key): last-read} enrichment index
    :returns: list of skip records for buckets that failed
    """
    extras = extras or ScanExtras()
    skips = []
    for bucket in buckets:
        try:
            for obj in provider.list_objects(bucket, prefix=prefix):
                if (extras.access_index is not None
                        and obj.last_accessed is None):
                    obj.last_accessed = extras.access_index.get(
                        (obj.container, obj.key))
                builder.add(obj)
                for emitter in extras.emitters:
                    emitter.offer(obj)
            LOG.info("%s complete...", bucket)
        except (ClientError, BotoCoreError, OSError) as err:
            LOG.warning("skipping %s: %s", bucket, err)
            skips.append({"container": bucket, "error": str(err)})
    return skips


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
    :returns: exit code — 0 OK, 4 bad override map or no pricing
    """
    pricing = _load_backend_pricing(run.backend)
    if pricing is None:
        return 4
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
    if run.access_aware:
        print("(ages in this run are access-aware lower bounds)")
    if args.savings_csv:
        write_savings_csv(args.savings_csv, projections)
        print(f"savings csv saved to {args.savings_csv}.")
    return 0


def _emit_lifecycle(session, run, args):
    """
    Generate per-bucket lifecycle configs into a directory, with APPLY.md.

    :param session: SQLAlchemy session
    :param run: StorageScanRun to generate from
    :param args: parsed CLI namespace
    :returns: exit code — 0 OK, 4 nothing generated / bad input
    """
    out_dir = pathlib.Path(args.emit_lifecycle)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        band_targets = _parse_age_out_map(args.age_out_map)
        delete_after = getattr(args, "delete_after", None)
        configs, skips = build_lifecycle_configs(
            stats_for_run(session, run.id), run.age_band_days,
            band_targets=band_targets, delete_after=delete_after)
    except ValueError as err:
        LOG.error("%s", err)
        return 4

    if not configs:
        LOG.error("no lifecycle rules to generate — nothing stale and "
                  "transition-eligible in the latest run")
        return 4

    print("generating lifecycle configs...")
    apply_lines = ["# Lifecycle configs — how to apply", "", APPLY_HEADER, ""]
    for bucket, config in sorted(configs.items()):
        path = out_dir / f"{bucket}.lifecycle.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
            handle.write("\n")
        print(f"  {path.name}: {len(config['Rules'])} rule(s)")
        apply_lines.extend([
            f"## {bucket}",
            "",
            "```bash",
            "aws s3api put-bucket-lifecycle-configuration \\",
            f"  --bucket {bucket} \\",
            f"  --lifecycle-configuration file://{path.name}",
            "```",
            "",
            "Blast radius: REPLACES every existing lifecycle rule on "
            f"`{bucket}`. Objects matching the filters transition on the "
            "configured day schedule from object creation.",
            "",
        ])
    if skips:
        apply_lines.append("## Skipped (no rule generated)")
        apply_lines.append("")
        for skip in skips:
            apply_lines.append(f"- {skip}")
            print(f"  skipped: {skip}")
        apply_lines.append("")

    with open(out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(apply_lines))
    print(f"lifecycle configs saved to {out_dir}/.")
    record_artifact(session, run, "lifecycle", out_dir,
                    {"buckets": len(configs),
                     "rules": sum(len(c["Rules"]) for c in configs.values())})
    return 0


def _run_structure(session, run, args):
    """
    Build, print, persist, and optionally emit structure recommendations.

    :param session: SQLAlchemy session
    :param run: StorageScanRun to analyze
    :param args: parsed CLI namespace
    :returns: exit code — 0 OK
    """
    pricing = None
    try:
        pricing = load_pricing(provider=run.backend)
    except FileNotFoundError:
        pass  # $-at-stake attribution simply absent (fs backend)

    recs, notes = build_recommendations(
        stats_for_run(session, run.id), run.age_band_days,
        pricing=pricing, access_aware=run.access_aware)

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

    run.structure_recs = recs_to_json(recs)
    session.commit()

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
    :returns: exit code — 0 OK, 4 no pricing for the backend
    """
    pricing = _load_backend_pricing(run.backend)
    if pricing is None:
        return 4
    report = build_cost_report(stats_for_run(session, run.id), pricing)
    print_cost_report(report)
    if run.access_aware:
        print("(ages in this run are access-aware lower bounds)")
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
    run = latest_complete_run(session, backend=args.backend)
    if run is None:
        LOG.error("no saved storage scan runs — scan first with --bucket")
        return 4
    return _post_scan_outputs(session, run, args)


def _emit_tiering(session, run, args):
    """
    Generate per-bucket Intelligent-Tiering configs into a directory.

    :param session: SQLAlchemy session
    :param run: StorageScanRun to generate from
    :param args: parsed CLI namespace
    :returns: exit code — 0 OK, 4 nothing generated
    """
    out_dir = pathlib.Path(args.emit_tiering)
    out_dir.mkdir(parents=True, exist_ok=True)
    configs, skips = build_tiering_configs(
        stats_for_run(session, run.id), run.age_band_days)
    if not configs:
        LOG.error("no tiering configs to generate — nothing stale and "
                  "eligible in the latest run")
        return 4

    print("generating tiering configs...")
    apply_lines = ["# Intelligent-Tiering configs — how to apply", "",
                   TIERING_APPLY_NOTE, ""]
    for bucket, bucket_configs in sorted(configs.items()):
        for config in bucket_configs:
            path = out_dir / f"{bucket}.{config['Id']}.json"
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(config, handle, indent=2)
                handle.write("\n")
            apply_lines.extend([
                f"## {bucket} — {config['Id']}", "", "```bash",
                "aws s3api put-bucket-intelligent-tiering-configuration \\",
                f"  --bucket {bucket} --id {config['Id']} \\",
                f"  --intelligent-tiering-configuration file://{path.name}",
                "```", ""])
        print(f"  {bucket}: {len(bucket_configs)} config(s)")
    for skip in skips:
        print(f"  skipped: {skip}")
    with open(out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(apply_lines))
    print(f"tiering configs saved to {out_dir}/.")
    record_artifact(session, run, "tiering", out_dir,
                    {"configs": sum(len(c) for c in configs.values())})
    return 0


def _report_batch_copy(emitter, age_band_days):
    """
    Close a batch-copy emitter, write APPLY.md with the create-job recipe.

    :param emitter: BatchCopyEmitter
    :param age_band_days: run thresholds (drives the recommended class)
    """
    summary = emitter.close()
    if not summary:
        print("no objects past the last age band — no batch-copy manifests.")
        return None
    target = "DEEP_ARCHIVE" if age_band_days[-1] >= 365 else "GLACIER"
    lines = [
        "# Batch Operations copy manifests — how to apply", "",
        "Manifests are `S3BatchOperations_CSV_20180820` (bucket,key; keys "
        "URL-encoded). Upload each CSV to S3, get its ETag "
        "(`aws s3api head-object`), then create the job in the "
        "DESTINATION region:", "",
        "```bash",
        "aws s3control create-job \\",
        "  --account-id <ACCOUNT_ID> --region <DEST_REGION> \\",
        "  --operation '{\"S3PutObjectCopy\": {\"TargetResource\": "
        "\"arn:aws:s3:::<DEST_BUCKET>\", "
        f"\"StorageClass\": \"{target}\"}}' \\",
        "  --manifest '{\"Spec\": {\"Format\": "
        "\"S3BatchOperations_CSV_20180820\", \"Fields\": "
        "[\"Bucket\",\"Key\"]}, \"Location\": {\"ObjectArn\": "
        "\"arn:aws:s3:::<MANIFEST_BUCKET>/<manifest>.csv\", "
        "\"ETag\": \"<ETAG>\"}}' \\",
        "  --report '{\"Bucket\": \"arn:aws:s3:::<REPORT_BUCKET>\", "
        "\"Format\": \"Report_CSV_20180820\", \"Enabled\": true, "
        "\"ReportScope\": \"AllTasks\"}' \\",
        "  --priority 10 --role-arn <BATCH_ROLE_ARN>",
        "```", "",
        "Role trust principal: `batchoperations.s3.amazonaws.com`. "
        "Batch copy handles objects up to 5 GB — larger objects are in "
        "the `.skipped.txt` sidecars and need aws s3 cp or multipart "
        "copy.", "",
    ]
    for bucket, info in sorted(summary.items()):
        print(f"  {bucket}: {info['keys']} copy candidate(s), "
              f"{info['skipped_large']} skipped (>5 GB)")
        lines.append(f"- `{bucket}`: {info['keys']} keys"
                     + (f", {info['skipped_large']} skipped >5 GB"
                        if info["skipped_large"] else ""))
    with open(emitter.out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"batch-copy manifests saved to {emitter.out_dir}/.")
    return summary


def _report_move_plan(emitter):
    """
    Close a move-plan emitter, write APPLY.md, print the summary.

    :param emitter: MoveManifestEmitter
    :returns: summary dict or None
    """
    summary = emitter.close()
    if not summary:
        print("no objects matched the recommendations — no move plans.")
        return None
    skipped = summary.pop("_skipped_conforming", 0)
    lines = [
        "# Move plans — how to apply", "",
        "old_key,new_key CSVs from the latest recommendations. Moves are "
        "COPY + DELETE (object storage has no rename) — copy first, verify, "
        "then delete. Plans are point-in-time; objects written since the "
        "scan are not covered. If a target prefix already exists, review "
        "for collisions before copying.", "",
        "```bash",
        "# per line: aws s3 cp s3://<bucket>/<old_key> "
        "s3://<bucket>/<new_key> && aws s3 rm s3://<bucket>/<old_key>",
        "```", "",
    ]
    for bucket, info in sorted(summary.items()):
        print(f"  {bucket}: {info['moves']} move(s) planned")
        lines.append(f"- `{bucket}`: {info['moves']} moves")
    if skipped:
        note = f"{skipped} object(s) already match the target layout — skipped"
        print(f"  {note}")
        lines.append(f"- {note}")
    with open(emitter.out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"move plans saved to {emitter.out_dir}/.")
    summary["_skipped_conforming"] = skipped
    return summary


def _report_delete_manifests(emitter):
    """
    Close a delete emitter, write its APPLY.md, and print the summary.

    :param emitter: DeleteManifestEmitter
    """
    summary = emitter.close()
    if not summary:
        print("no objects past the last age band — no delete manifests.")
        return None
    lines = ["# Delete manifests — how to apply", ""]
    lines.extend(DELETE_APPLY_NOTES)
    lines.append("")
    for bucket, info in sorted(summary.items()):
        print(f"  {bucket}: {info['keys']} delete candidate(s) across "
              f"{info['files']} manifest file(s)")
        lines.append(f"- `{bucket}`: {info['keys']} keys, "
                     f"{info['files']} chunk file(s)")
    with open(emitter.out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"delete manifests saved to {emitter.out_dir}/.")
    return summary


def _build_emitters(args, session, age_band_days):
    """
    Construct the scan's streaming emitters, or None on a config error.

    :param args: parsed CLI namespace
    :param session: SQLAlchemy session (move-plan rec lookup)
    :param age_band_days: resolved thresholds
    :returns: list of emitters, or None
    """
    emitters = []
    if args.emit_delete_manifests:
        emitters.append(DeleteManifestEmitter(
            args.emit_delete_manifests, stale_after_days=age_band_days[-1]))
    if args.emit_batch_copy:
        emitters.append(BatchCopyEmitter(
            args.emit_batch_copy, stale_after_days=age_band_days[-1]))
    if args.emit_move_plan:
        # Recs load NOW, from the latest COMPLETE run — the run this scan
        # creates is still "running" and carries none yet (two-pass flow).
        prior = latest_complete_run(session, backend=args.backend)
        prior_recs = list(prior.structure_recs or []) if prior else []
        if not any(rec.get("kind") in MoveManifestEmitter.MOVABLE_KINDS
                   for rec in prior_recs):
            LOG.error("no movable structure recommendations on the latest "
                      "%s run — run --recommend-structure first, then "
                      "rescan with --emit-move-plan", args.backend)
            return None
        emitters.append(MoveManifestEmitter(
            args.emit_move_plan, prior_recs,
            stale_after_days=age_band_days[0]))
    return emitters


def _post_scan_outputs(session, run, args):
    """
    Optional analysis/artifact outputs after a scan (or on the latest run).

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :param args: parsed CLI namespace
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


def _make_provider(args):
    """
    Build the provider for the selected backend.

    :param args: parsed CLI namespace
    :returns: StorageProvider, or None on config error
    """
    try:
        if args.backend == "azure":
            if not args.account_url:
                LOG.error("azure backend needs --account-url")
                return None
            return AzureBlobStorageProvider(args.account_url)
        if args.backend == "gcs":
            return GcsStorageProvider()
        if args.backend == "fs":
            return FilesystemStorageProvider()
        return S3StorageProvider()
    except RuntimeError as err:
        LOG.error("%s", err)
        return None


def _load_backend_pricing(backend):
    """
    Pricing snapshot for a backend, or None with a message.

    :param backend: backend name
    :returns: PricingTable or None
    """
    try:
        return load_pricing(provider=backend)
    except FileNotFoundError as err:
        LOG.error("no pricing snapshot for backend %r: %s", backend, err)
        return None


def _resolve_age_bands(args, settings):
    """
    Age thresholds from the flag or settings; None on bad input.

    :param args: parsed CLI namespace
    :param settings: Settings
    :returns: sorted list of day thresholds, or None
    """
    if not args.age_bands:
        return list(settings.age_band_days)
    try:
        return sorted(int(part) for part in args.age_bands.split(","))
    except ValueError:
        LOG.error("bad --age-bands %r — expected e.g. 90,365", args.age_bands)
        return None


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


def _write_html_report(session, run, args):
    """
    Compose and write the storage insights HTML report for one run.

    :param session: SQLAlchemy session
    :param run: StorageScanRun to report on
    :param args: parsed CLI namespace
    :returns: exit code — 0 OK
    """
    stats = stats_for_run(session, run.id)
    cost_report = None
    projections = None
    try:
        pricing = load_pricing(provider=run.backend)
        cost_report = build_cost_report(stats, pricing)
        projections = project_options(stats, pricing, run.age_band_days)
    except FileNotFoundError:
        pass  # fs backend — report renders with costs honestly omitted

    page = render_storage_report(run, stats, cost_report=cost_report,
                                 projections=projections)
    with open(args.html_report, "w", encoding="utf-8") as handle:
        handle.write(page)
    print(f"storage report saved to {args.html_report}.")
    return 0


def _load_access_index_arg(args):
    """
    Resolve --access-logs into an enrichment index.

    :param args: parsed CLI namespace
    :returns: (index or None, ok bool)
    """
    if not args.access_logs:
        return None, True
    log_files = sorted(globlib.glob(args.access_logs))
    if not log_files:
        LOG.error("--access-logs matched no files: %r", args.access_logs)
        return None, False
    print("loading access logs...")
    access_index, used = load_access_index(log_files)
    print(f"access index ready: {used} read event(s), "
          f"{len(access_index)} key(s). ages become access-aware "
          "lower bounds (log delivery is best-effort, hours of lag).")
    return access_index, True


def _finish_emitters(session, run, emitters, age_band_days):
    """
    Close every emitter, write its APPLY.md, record its artifact entry.

    :param session: SQLAlchemy session
    :param run: StorageScanRun just persisted
    :param emitters: streaming emitters from the scan
    :param age_band_days: resolved thresholds
    """
    for emitter in emitters:
        if isinstance(emitter, DeleteManifestEmitter):
            summary = _report_delete_manifests(emitter)
            kind = "delete-manifests"
        elif isinstance(emitter, MoveManifestEmitter):
            summary = _report_move_plan(emitter)
            kind = "move-plan"
        else:
            summary = _report_batch_copy(emitter, age_band_days)
            kind = "batch-copy"
        if summary:
            record_artifact(session, run, kind, emitter.out_dir,
                            {b: dict(info) if isinstance(info, dict) else info
                             for b, info in summary.items()})


def _scan(settings, args, provider):
    """
    Scan mode: walk buckets, persist rollups, run requested outputs.

    :param settings: Settings
    :param args: parsed CLI namespace
    :param provider: StorageProvider override for tests (None = build one)
    :returns: exit code — 0 OK, 4 config error
    """
    age_band_days = _resolve_age_bands(args, settings)
    if age_band_days is None:
        return 4

    prefix_depth = (args.prefix_depth if args.prefix_depth is not None
                    else settings.storage_prefix_depth)

    if provider is None:
        provider = _make_provider(args)
        if provider is None:
            return 4
    builder = RollupBuilder(age_band_days=age_band_days,
                            prefix_depth=prefix_depth,
                            rollup_owners=args.rollup_owners)

    # Guard the schema BEFORE the walk — a stale dev DB should fail in
    # milliseconds, not after a full bucket scan.
    session = _open_session(settings)
    if session is None:
        return 4

    emitters = _build_emitters(args, session, age_band_days)
    if emitters is None:
        return 4

    access_index, index_ok = _load_access_index_arg(args)
    if not index_ok:
        return 4

    print("scanning storage...")
    skips = scan_buckets(provider, args.bucket, args.prefix, builder,
                         extras=ScanExtras(emitters=tuple(emitters),
                                           access_index=access_index))

    run = persist_rollups(session, builder, backend=provider.backend_name,
                          skips=skips)
    session.commit()
    LOG.info("rollups saved (run %s, status %s).", run.id, run.status)

    print_summary(builder)

    if args.csv_out:
        write_csv(args.csv_out, builder)
        print(f"csv saved to {args.csv_out}.")

    _finish_emitters(session, run, emitters, age_band_days)

    return _post_scan_outputs(session, run, args)


if __name__ == "__main__":
    sys.exit(main())
