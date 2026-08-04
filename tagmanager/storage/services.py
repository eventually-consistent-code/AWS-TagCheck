"""
Purpose: Storage service layer — every scan/analyze/emit flow as a callable,
argparse-free service the web app and CLI both drive. Services return data
and raise typed errors; they never print. Session discipline: services take
a session_maker and open short sessions at touchpoints — none live across
a bucket walk.
Author(s): John Reed
"""

import json
import logging
import pathlib
from dataclasses import dataclass, field

from botocore.exceptions import BotoCoreError, ClientError

from tagmanager.config import get_settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.storage.access_log import fold_reads
from tagmanager.storage.access_log import iter_events as access_iter_events
from tagmanager.storage.cloudtrail_log import (
    iter_events as cloudtrail_iter_events)
from tagmanager.storage.request_rate import estimate_rates, fold_rates
from tagmanager.storage.azure_provider import AzureBlobStorageProvider
from tagmanager.storage.cost import build_cost_report
from tagmanager.storage.diff import ConfigDiff, diff_bucket
from tagmanager.storage.fs_provider import FilesystemStorageProvider
from tagmanager.storage.gcs_provider import GcsStorageProvider
from tagmanager.storage.html_report import render_storage_report
from tagmanager.storage.lifecycle_gen import (APPLY_HEADER,
                                              build_lifecycle_configs)
from tagmanager.storage.manifests import (BatchCopyEmitter,
                                          DeleteManifestEmitter,
                                          MoveManifestEmitter)
from tagmanager.storage.pricing import load_pricing
from tagmanager.storage.projections import project_options
from tagmanager.storage.rollup import RollupBuilder
from tagmanager.storage.s3_provider import S3StorageProvider
from tagmanager.storage.store import (latest_complete_run, persist_rollups,
                                      record_artifact, schema_current,
                                      stats_for_run)
from tagmanager.storage.structure import build_recommendations, recs_to_json
from tagmanager.storage.tiering_gen import build_tiering_configs

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.storage_services")
LOG.setLevel(logging.INFO)


# Errors

class StorageServiceError(Exception):
    """Config/state error a caller surfaces to the user (CLI: exit 4)."""


class SchemaOutOfDate(StorageServiceError):
    """The live DB is missing columns this code reads/writes."""


class ScanCancelled(Exception):
    """Raised by a per-object hook to stop a walk at a batch boundary.

    Deliberately NOT a StorageServiceError and deliberately not caught by
    the walk's per-bucket error isolation — cancellation must unwind.
    """


# Options

@dataclass
class ScanOptions:  # pylint: disable=too-many-instance-attributes
    """Everything a scan needs; field defaults mirror the CLI flags."""

    backend: str = "s3"
    account_url: str = ""
    buckets: tuple = ()
    prefix: str = ""
    age_band_days: list = None
    prefix_depth: int = None
    rollup_owners: bool = False
    rollup_types: bool = False
    access_log_paths: tuple = ()
    cloudtrail_log_paths: tuple = ()
    access_index: dict = None
    on_object: object = None
    emit_delete_dir: str = ""
    emit_batch_copy_dir: str = ""
    emit_move_plan_dir: str = ""


# Results

@dataclass
class AccessIndexReport:
    """What an access-enrichment fold produced (across sources)."""

    events: int
    keys: int
    index: dict
    sources: list = field(default_factory=list)
    rates: dict = field(default_factory=dict)


@dataclass
class EmitterReport:
    """One streaming emitter's outcome."""

    kind: str
    out_dir: pathlib.Path
    summary: dict
    skipped_conforming: int = 0
    disposition: str = "written"  # written | empty | all_conforming


@dataclass
class ScanResult:
    """A completed (or cancelled) scan."""

    run_id: int
    builder: RollupBuilder
    skips: list
    emitter_reports: list = field(default_factory=list)
    access_report: AccessIndexReport = None
    cancelled: bool = False


@dataclass
class LifecycleEmitResult:
    """Lifecycle configs written to a directory."""

    out_dir: pathlib.Path
    files: list  # (bucket, filename, rule_count)
    skips: list


@dataclass
class TieringEmitResult:
    """Tiering configs written to a directory."""

    out_dir: pathlib.Path
    buckets: list  # (bucket, [config ids])
    skips: list


@dataclass
class StructureResult:
    """Recommendations built and persisted for a run."""

    recs: list
    notes: list
    persisted: int
    truncated: bool


# Session plumbing

def open_storage_session_maker(settings=None):
    """
    Engine + create_all + schema guard → session maker.

    :param settings: Settings (default: from environment)
    :returns: sessionmaker
    :raises SchemaOutOfDate: stale dev DB missing current columns
    """
    settings = settings or get_settings()
    engine = get_engine(settings.db_url)
    create_all(engine)
    if not schema_current(engine):
        raise SchemaOutOfDate(
            f"db schema changed — delete the dev database "
            f"({settings.db_url}) and re-scan")
    return session_factory(engine)


def make_provider(backend, account_url=""):
    """
    Build the provider for a backend.

    :param backend: s3 | azure | gcs | fs
    :param account_url: azure account URL
    :returns: StorageProvider
    :raises StorageServiceError: bad config or missing optional SDK
    """
    try:
        if backend == "azure":
            if not account_url:
                raise StorageServiceError("azure backend needs --account-url")
            return AzureBlobStorageProvider(account_url)
        if backend == "gcs":
            return GcsStorageProvider()
        if backend == "fs":
            return FilesystemStorageProvider()
        return S3StorageProvider()
    except RuntimeError as err:
        raise StorageServiceError(str(err)) from err


def load_backend_pricing(backend):
    """
    Pricing snapshot for a backend.

    :param backend: backend name
    :returns: PricingTable
    :raises StorageServiceError: no snapshot shipped for the backend
    """
    try:
        return load_pricing(provider=backend)
    except FileNotFoundError as err:
        raise StorageServiceError(
            f"no pricing snapshot for backend {backend!r}: {err}") from err


def resolve_age_bands(raw, settings=None):
    """
    Age thresholds from a raw comma string or settings default.

    :param raw: "90,365"-style string or ""
    :param settings: Settings (default: from environment)
    :returns: sorted list of day thresholds
    :raises StorageServiceError: unparseable input
    """
    settings = settings or get_settings()
    if not raw:
        return list(settings.age_band_days)
    try:
        return sorted(int(part) for part in raw.split(","))
    except ValueError as err:
        raise StorageServiceError(
            f"bad --age-bands {raw!r} — expected e.g. 90,365") from err


def parse_age_out_map(raw):
    """
    Parse "90=STANDARD_IA,365=DEEP_ARCHIVE" into {90: "STANDARD_IA", ...}.

    :param raw: flag value ("" -> None)
    :returns: dict of int day -> storage class, or None
    :raises StorageServiceError: malformed pairs
    """
    if not raw:
        return None
    mapping = {}
    for pair in raw.split(","):
        day, _, sclass = pair.partition("=")
        if not sclass:
            raise StorageServiceError(f"bad --age-out-map entry {pair!r}")
        try:
            mapping[int(day)] = sclass.strip()
        except ValueError as err:
            raise StorageServiceError(
                f"bad --age-out-map entry {pair!r}") from err
    return mapping


def validated_band_targets(raw, pricing):
    """
    Parse and validate an age-out override map against a pricing table.

    :param raw: flag-style string
    :param pricing: PricingTable
    :returns: dict or None
    :raises StorageServiceError: unknown class or invalid destination
    """
    band_targets = parse_age_out_map(raw)
    for sclass in (band_targets or {}).values():
        if not pricing.known_class(sclass) or sclass == "STANDARD":
            raise StorageServiceError(
                f"--age-out-map target {sclass!r} is not a valid "
                "lifecycle transition destination")
    return band_targets


def build_access_report(access_log_paths=(), cloudtrail_paths=(),
                        prefix_depth=None):
    """
    Fold access-log and/or CloudTrail files into ONE enrichment index and
    per-prefix request rates, in a single sweep per source file.

    The last-read index merges across sources (newest wins); rate op
    counts sum across sources. Rates are computed only when prefix_depth
    is given.

    :param access_log_paths: S3 server-access-log file paths
    :param cloudtrail_paths: CloudTrail data-event file paths
    :param prefix_depth: run prefix depth for rate aggregation (None
        skips rate estimation)
    :returns: AccessIndexReport
    """
    index = {}
    events = 0
    sources = []
    rate_stats = {}
    for label, iter_fn, paths in (
            ("S3 access logs", access_iter_events, list(access_log_paths)),
            ("CloudTrail", cloudtrail_iter_events, list(cloudtrail_paths))):
        if not paths:
            continue
        materialized = list(iter_fn(paths))
        used = _merge_read_index(index, materialized)
        events += used
        sources.append(label)
        if prefix_depth is not None:
            _merge_rate_stats(rate_stats,
                              fold_rates(materialized, prefix_depth))
    rates = estimate_rates(rate_stats) if prefix_depth is not None else {}
    return AccessIndexReport(events=events, keys=len(index), index=index,
                             sources=sources, rates=rates)


def _merge_read_index(index, materialized):
    """Fold reads from one source into the shared index; return read count."""
    sub_index, used = fold_reads(materialized)
    for cell_key, read_time in sub_index.items():
        existing = index.get(cell_key)
        if existing is None or read_time > existing:
            index[cell_key] = read_time
    return used


def _merge_rate_stats(into, more):
    """Sum per-prefix op counts and union windows across sources."""
    for key, stat in more.items():
        existing = into.get(key)
        if existing is None:
            into[key] = stat
            continue
        existing.read_count += stat.read_count
        existing.write_count += stat.write_count
        if stat.window_start and (existing.window_start is None
                                  or stat.window_start < existing.window_start):
            existing.window_start = stat.window_start
        if stat.window_end and (existing.window_end is None
                                or stat.window_end > existing.window_end):
            existing.window_end = stat.window_end


# Scan

@dataclass
class ScanExtras:
    """Optional per-object hooks riding along on a scan."""

    emitters: tuple = ()
    access_index: dict = None
    on_object: object = None  # callable(count) — may raise ScanCancelled


def scan_buckets(provider, buckets, prefix, builder, extras=None):
    """
    Stream every bucket through the rollup builder, isolating failures.

    Per-bucket errors become skip records; ScanCancelled from the
    on_object hook unwinds on purpose.

    :param provider: StorageProvider
    :param buckets: list of bucket names
    :param prefix: key prefix scope
    :param builder: RollupBuilder
    :param extras: ScanExtras
    :returns: list of skip records for buckets that failed
    """
    extras = extras or ScanExtras()
    skips = []
    count = 0
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
                count += 1
                if extras.on_object is not None:
                    extras.on_object(count)
            LOG.info("%s complete...", bucket)
        except (ClientError, BotoCoreError, OSError) as err:
            LOG.warning("skipping %s: %s", bucket, err)
            skips.append({"container": bucket, "error": str(err)})
    return skips


def _build_scan_emitters(session, opts, age_band_days):
    """
    Streaming emitters for a scan, from a short-lived session.

    :param session: SQLAlchemy session (pre-scan touchpoint)
    :param opts: ScanOptions
    :param age_band_days: resolved thresholds
    :returns: list of emitters
    :raises StorageServiceError: move plan requested with no movable recs
    """
    emitters = []
    if opts.emit_delete_dir:
        emitters.append(DeleteManifestEmitter(
            opts.emit_delete_dir, stale_after_days=age_band_days[-1]))
    if opts.emit_batch_copy_dir:
        emitters.append(BatchCopyEmitter(
            opts.emit_batch_copy_dir, stale_after_days=age_band_days[-1]))
    if opts.emit_move_plan_dir:
        # Recs load NOW, from the latest COMPLETE run — the run this scan
        # creates is still "running" and carries none yet (two-pass flow).
        prior = latest_complete_run(session, backend=opts.backend)
        prior_recs = list(prior.structure_recs or []) if prior else []
        if not any(rec.get("kind") in MoveManifestEmitter.MOVABLE_KINDS
                   for rec in prior_recs):
            raise StorageServiceError(
                f"no movable structure recommendations on the latest "
                f"{opts.backend} run — run --recommend-structure first, "
                "then rescan with --emit-move-plan")
        emitters.append(MoveManifestEmitter(
            opts.emit_move_plan_dir, prior_recs,
            stale_after_days=age_band_days[0]))
    return emitters


def _finish_move_emitter(emitter):
    """Close a move-plan emitter into an EmitterReport."""
    summary = emitter.close()
    if not summary:
        return EmitterReport("move-plan", emitter.out_dir, {},
                             disposition="empty")
    skipped = summary.pop("_skipped_conforming", 0)
    if not summary:
        return EmitterReport("move-plan", emitter.out_dir, {},
                             skipped_conforming=skipped,
                             disposition="all_conforming")
    _write_move_apply(emitter.out_dir, summary, skipped)
    return EmitterReport("move-plan", emitter.out_dir, summary,
                         skipped_conforming=skipped)


def _finish_emitter(emitter, age_band_days):
    """
    Close one emitter, write its APPLY.md, and describe the outcome.

    :param emitter: streaming emitter
    :param age_band_days: resolved thresholds
    :returns: EmitterReport
    """
    if isinstance(emitter, MoveManifestEmitter):
        return _finish_move_emitter(emitter)

    kind = ("delete-manifests" if isinstance(emitter, DeleteManifestEmitter)
            else "batch-copy")
    summary = emitter.close()
    if not summary:
        return EmitterReport(kind, emitter.out_dir, {}, disposition="empty")
    if kind == "delete-manifests":
        _write_delete_apply(emitter.out_dir, summary)
    else:
        _write_batch_copy_apply(emitter.out_dir, summary, age_band_days)
    return EmitterReport(kind, emitter.out_dir, summary)


def run_storage_scan(session_maker, opts, provider=None, settings=None):
    """
    The full scan flow: provider, enrichment, walk, persist, artifacts.

    Sessions are short: one pre-scan touchpoint (emitter construction),
    one post-scan touchpoint (persist + artifact records). None live
    across the walk.

    :param session_maker: sessionmaker (thread-safe factory)
    :param opts: ScanOptions
    :param provider: injected StorageProvider (tests / callers)
    :param settings: Settings (default: from environment)
    :returns: ScanResult
    :raises StorageServiceError: config errors
    """
    settings = settings or get_settings()
    age_band_days = (list(opts.age_band_days) if opts.age_band_days
                     else list(settings.age_band_days))
    prefix_depth = (opts.prefix_depth if opts.prefix_depth is not None
                    else settings.storage_prefix_depth)

    if provider is None:
        provider = make_provider(opts.backend, opts.account_url)
    builder = RollupBuilder(age_band_days=age_band_days,
                            prefix_depth=prefix_depth,
                            rollup_owners=opts.rollup_owners,
                            rollup_types=opts.rollup_types)

    session = session_maker()
    try:
        emitters = _build_scan_emitters(session, opts, age_band_days)
    finally:
        session.close()

    outcome, access_report = _walk(provider, opts, builder, emitters,
                                   age_band_days)
    run_id, reports = _persist_scan(session_maker, builder,
                                    provider.backend_name, outcome)
    return ScanResult(run_id=run_id, builder=builder, skips=outcome.skips,
                      emitter_reports=reports, access_report=access_report,
                      cancelled=outcome.cancelled)


def _walk(provider, opts, builder, emitters, age_band_days):
    """
    The bucket walk with enrichment and cancellation handling.

    :returns: (_WalkOutcome, AccessIndexReport or None)
    """
    access_report = None
    access_index = opts.access_index
    if access_index is None and (opts.access_log_paths
                                 or opts.cloudtrail_log_paths):
        access_report = build_access_report(
            access_log_paths=opts.access_log_paths,
            cloudtrail_paths=opts.cloudtrail_log_paths,
            prefix_depth=builder.prefix_depth)
        access_index = access_report.index

    cancelled = False
    try:
        skips = scan_buckets(provider, list(opts.buckets), opts.prefix,
                             builder,
                             extras=ScanExtras(emitters=tuple(emitters),
                                               access_index=access_index,
                                               on_object=opts.on_object))
    except ScanCancelled:
        cancelled = True
        skips = [{"container": "*", "error": "scan cancelled"}]
    rates = access_report.rates if access_report else {}
    return (_WalkOutcome(skips=skips, cancelled=cancelled,
                         emitters=emitters, age_band_days=age_band_days,
                         request_rates=rates),
            access_report)


@dataclass
class _WalkOutcome:
    """What a finished (or cancelled) walk hands to the persist step."""

    skips: list
    cancelled: bool
    emitters: list
    age_band_days: list
    request_rates: dict = field(default_factory=dict)


def _persist_scan(session_maker, builder, backend, outcome):
    """
    Post-scan touchpoint: persist rollups, finish emitters, record artifacts.

    :returns: (run_id, list of EmitterReport)
    """
    session = session_maker()
    try:
        run = persist_rollups(session, builder, backend=backend,
                              skips=outcome.skips)
        if outcome.request_rates:
            run.request_rates = outcome.request_rates
        session.commit()
        if outcome.cancelled:
            run.status = "cancelled"
            session.commit()
        LOG.info("rollups saved (run %s, status %s).", run.id, run.status)

        reports = []
        for emitter in outcome.emitters:
            report = _finish_emitter(emitter, outcome.age_band_days)
            reports.append(report)
            if report.summary:
                record_artifact(
                    session, run, report.kind, report.out_dir,
                    {b: dict(info) if isinstance(info, dict) else info
                     for b, info in report.summary.items()})
        return run.id, reports
    finally:
        session.close()


# Analysis / artifact services (operate on a persisted run)

def analyze_cost(session, run):
    """
    Cost report for one run.

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :returns: CostReport
    :raises StorageServiceError: no pricing for the backend
    """
    pricing = load_backend_pricing(run.backend)
    return build_cost_report(stats_for_run(session, run.id), pricing)


def analyze_projections(session, run, age_out_map_raw=""):
    """
    Per-option savings projections for one run.

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :param age_out_map_raw: CLI-style override string
    :returns: list of OptionProjection
    :raises StorageServiceError: no pricing / invalid override map
    """
    pricing = load_backend_pricing(run.backend)
    band_targets = validated_band_targets(age_out_map_raw, pricing)
    try:
        return project_options(stats_for_run(session, run.id), pricing,
                               run.age_band_days, band_targets=band_targets)
    except ValueError as err:
        raise StorageServiceError(str(err)) from err


def recommend_structure(session, run):
    """
    Build recommendations, persist them on the run, report truncation.

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :returns: StructureResult
    """
    pricing = None
    try:
        pricing = load_pricing(provider=run.backend)
    except FileNotFoundError:
        pass  # $-at-stake attribution simply absent (fs backend)

    recs, notes = build_recommendations(
        stats_for_run(session, run.id), run.age_band_days,
        pricing=pricing, access_aware=run.access_aware,
        request_rates=run.request_rates or {})
    run.structure_recs = recs_to_json(recs)
    session.commit()
    truncated = bool(run.structure_recs
                     and run.structure_recs[-1].get("kind") == "truncated")
    persisted = len(run.structure_recs) - (1 if truncated else 0)
    return StructureResult(recs=recs, notes=notes, persisted=persisted,
                           truncated=truncated)


def dry_run_diff(session, run, provider):
    """
    Diff live S3 config against what this run would generate — read-only.

    Regenerates the lifecycle + intelligent-tiering configs in-memory from
    the run and diffs them, per bucket, against the LIVE config fetched via
    the provider's read-only GET/list calls. Writes nothing — the apply
    ladder's rung one.

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :param provider: an S3StorageProvider (fetch_lifecycle / fetch_tiering)
    :returns: diff.ConfigDiff
    :raises StorageServiceError: when the run is not an S3 backend
    """
    if run.backend != "s3":
        raise StorageServiceError(
            "dry-run-diff is S3 only — lifecycle / intelligent-tiering are "
            f"S3 concepts (this run's backend is {run.backend})")

    stats = stats_for_run(session, run.id)
    generated_lifecycle, _ = build_lifecycle_configs(stats, run.age_band_days)
    generated_tiering, _ = build_tiering_configs(stats, run.age_band_days)

    buckets = sorted(set(generated_lifecycle) | set(generated_tiering))
    bucket_diffs = []
    for bucket in buckets:
        life_rules = generated_lifecycle.get(bucket, {}).get("Rules", [])
        tier_configs = generated_tiering.get(bucket, [])
        bucket_diffs.append(diff_bucket(
            bucket, life_rules, provider.fetch_lifecycle(bucket),
            tier_configs, provider.fetch_tiering(bucket)))
    return ConfigDiff(buckets=bucket_diffs)


def emit_lifecycle_artifacts(session, run, out_dir, age_out_map_raw="",
                             delete_after=None):
    """
    Write per-bucket lifecycle configs + APPLY.md; record the artifact.

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :param out_dir: output directory
    :param age_out_map_raw: CLI-style override string
    :param delete_after: optional Expiration days
    :returns: LifecycleEmitResult
    :raises StorageServiceError: invalid input or nothing to generate
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        band_targets = parse_age_out_map(age_out_map_raw)
        configs, skips = build_lifecycle_configs(
            stats_for_run(session, run.id), run.age_band_days,
            band_targets=band_targets, delete_after=delete_after)
    except ValueError as err:
        raise StorageServiceError(str(err)) from err

    if not configs:
        raise StorageServiceError(
            "no lifecycle rules to generate — nothing stale and "
            "transition-eligible in the latest run")

    files = _write_lifecycle_files(out_dir, configs, skips)
    record_artifact(session, run, "lifecycle", out_dir,
                    {"buckets": len(configs),
                     "rules": sum(len(c["Rules"]) for c in configs.values())})
    return LifecycleEmitResult(out_dir=out_dir, files=files, skips=skips)


def _write_lifecycle_files(out_dir, configs, skips):
    """
    Write per-bucket lifecycle JSON + APPLY.md; return the file list.

    :returns: list of (bucket, filename, rule_count)
    """
    files = []
    apply_lines = ["# Lifecycle configs — how to apply", "", APPLY_HEADER, ""]
    for bucket, config in sorted(configs.items()):
        path = out_dir / f"{bucket}.lifecycle.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
            handle.write("\n")
        files.append((bucket, path.name, len(config["Rules"])))
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
        apply_lines.append("")

    with open(out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(apply_lines))
    return files


def emit_tiering_artifacts(session, run, out_dir):
    """
    Write per-bucket Intelligent-Tiering configs + APPLY.md; record it.

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :param out_dir: output directory
    :returns: TieringEmitResult
    :raises StorageServiceError: nothing to generate
    """
    from tagmanager.storage.tiering_gen import TIERING_APPLY_NOTE  # pylint: disable=import-outside-toplevel

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    configs, skips = build_tiering_configs(
        stats_for_run(session, run.id), run.age_band_days)
    if not configs:
        raise StorageServiceError(
            "no tiering configs to generate — nothing stale and "
            "eligible in the latest run")

    buckets = []
    apply_lines = ["# Intelligent-Tiering configs — how to apply", "",
                   TIERING_APPLY_NOTE, ""]
    for bucket, bucket_configs in sorted(configs.items()):
        ids = []
        for config in bucket_configs:
            path = out_dir / f"{bucket}.{config['Id']}.json"
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(config, handle, indent=2)
                handle.write("\n")
            ids.append(config["Id"])
            apply_lines.extend([
                f"## {bucket} — {config['Id']}", "", "```bash",
                "aws s3api put-bucket-intelligent-tiering-configuration \\",
                f"  --bucket {bucket} --id {config['Id']} \\",
                f"  --intelligent-tiering-configuration file://{path.name}",
                "```", ""])
        buckets.append((bucket, ids))
    with open(out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(apply_lines))
    record_artifact(session, run, "tiering", out_dir,
                    {"configs": sum(len(c) for c in configs.values())})
    return TieringEmitResult(out_dir=out_dir, buckets=buckets, skips=skips)


def write_html_report_file(session, run, path):
    """
    Compose and write the storage insights HTML report for one run.

    :param session: SQLAlchemy session
    :param run: StorageScanRun
    :param path: output file path
    :returns: the path written
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
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(page)
    return path


# APPLY.md writers (artifact content, service-side)

def _write_delete_apply(out_dir, summary):
    """Write the delete-manifests APPLY.md."""
    from tagmanager.storage.manifests import DELETE_APPLY_NOTES  # pylint: disable=import-outside-toplevel
    lines = ["# Delete manifests — how to apply", ""]
    lines.extend(DELETE_APPLY_NOTES)
    lines.append("")
    for bucket, info in sorted(summary.items()):
        lines.append(f"- `{bucket}`: {info['keys']} keys, "
                     f"{info['files']} chunk file(s)")
    with open(out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _write_move_apply(out_dir, summary, skipped):
    """Write the move-plan APPLY.md."""
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
        lines.append(f"- `{bucket}`: {info['moves']} moves")
    if skipped:
        lines.append(f"- {skipped} object(s) already match the target "
                     "layout — skipped")
    with open(out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _write_batch_copy_apply(out_dir, summary, age_band_days):
    """Write the batch-copy APPLY.md with the create-job recipe."""
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
        lines.append(f"- `{bucket}`: {info['keys']} keys"
                     + (f", {info['skipped_large']} skipped >5 GB"
                        if info["skipped_large"] else ""))
    with open(out_dir / "APPLY.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
