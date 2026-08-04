"""
Purpose: Console tables and CSV writers for the storage CLI — summaries,
cost reports, savings projections, layout proposals. Pure presentation;
no scanning, no pricing math.
Author(s): John Reed
"""

import csv
import pathlib

from tagmanager.storage.diff import _effective_prefix
from tagmanager.storage.rollup import band_labels

DROP_WARNING = ("live rule not in generated — an apply REPLACES the whole "
                "config and would DROP it")


def fmt_bytes(num):
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


def write_csv(path, builder):
    """
    Write every rollup cell to a CSV file.

    :param path: output file path
    :param builder: RollupBuilder after the scan
    """
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["container", "prefix", "storage_class", "age_band",
                         "owner", "data_type", "object_count", "total_bytes",
                         "oldest_last_modified", "small_object_count",
                         "small_object_bytes"])
        for (container, prefix, sclass, band, owner,
             data_type), stat in sorted(builder.rollups().items()):
            writer.writerow([container, prefix, sclass, band, owner, data_type,
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
          f"total: {fmt_bytes(builder.bytes_seen)}")
    if builder.access_aware:
        print("(age = access-aware — newest of modified/read; access times "
              "are lower bounds)")
    else:
        print("(age = last modified only — no access telemetry seen)")
    print()

    totals = builder.band_totals()
    for band in band_labels(builder.age_band_days):
        stat = totals.get(band)
        if not stat:
            continue
        print(f"  {band:>10}: {stat.object_count:>10} objects  "
              f"{fmt_bytes(stat.total_bytes):>12}")

    oldest = builder.oldest_objects()
    if oldest:
        print()
        print("oldest objects:")
        schemes = {"s3": "s3://", "azure": "azure://", "gcs": "gs://"}
        for obj in oldest[:5]:
            when = obj.last_modified.date().isoformat()
            scheme = schemes.get(obj.backend, "")
            sep = "" if obj.container.endswith("/") else "/"
            print(f"  {when}  {fmt_bytes(obj.size_bytes):>10}  "
                  f"{scheme}{obj.container}{sep}{obj.key}")


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


def write_structure_proposal(directory, recs, notes, run):
    """
    Write PROPOSAL.md into a directory and return its path.

    :param directory: output directory path string
    :param recs: Recommendation list
    :param notes: out-of-scope note strings
    :param run: StorageScanRun (age-basis caveat)
    :returns: pathlib.Path of the directory
    """
    guidance = {
        "date-split": "Suggested layout: `{prefix}/YYYY/MM/...` — then "
                      "`--emit-move-plan` on the next scan produces old→new "
                      "key CSVs.",
        "zone-split": "Suggested layout: keep the hot tail in place, move "
                      "stale objects under `cold/` — `--emit-move-plan` "
                      "produces the key mapping.",
        "compact-first": "Compact/tar cold small objects (aggregate to the "
                         "partition's time granularity) BEFORE any "
                         "lifecycle transitions.",
        "straight-lifecycle": "Apply a lifecycle rule directly: "
                              "`--emit-lifecycle`.",
        "type-split": "Suggested layout: split by data type "
                      "(`{prefix}/<type>/`) so each type gets its own "
                      "lifecycle policy and access controls.",
        "prefix-fanout": "Spread keys across more prefixes (e.g. a hash or "
                         "date shard under `{prefix}/`) — S3 scales request "
                         "throughput per prefix, so more prefixes = more "
                         "aggregate req/s. Rates are averages; peaks run "
                         "higher.",
        "expire-in-place": "Apply a lifecycle Expiration (not a transition) "
                           "if these objects are short-lived/rewritten — "
                           "`--emit-lifecycle`. Transitioning churn incurs "
                           "minimum-duration early-delete charges. Confirm "
                           "the churn first; logs can't distinguish an "
                           "overwrite from a first write.",
    }
    out_dir = pathlib.Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Storage layout proposal", "",
             "Generated from scan rollups — review before moving anything; "
             "the tool never moves data.", ""]
    for rec in recs:
        loc = f"{rec.container}/{rec.prefix}" if rec.prefix else rec.container
        lines.extend([f"## {rec.kind} — {loc}", "", rec.rationale, "",
                      guidance[rec.kind].format(prefix=rec.prefix)])
        if rec.confidence:
            lines.append(f"Confidence: {rec.confidence} — evidence: "
                         f"{', '.join(rec.evidence)}.")
        if rec.top_owners:
            lines.append(f"Top owners by bytes: {', '.join(rec.top_owners)}.")
        if rec.top_types:
            lines.append(f"Top types by bytes: {', '.join(rec.top_types)}.")
        lines.append("")
    lines.extend(["## Notes", ""])
    lines.extend(f"- {note}" for note in notes)
    if run.access_aware:
        lines.append("- ages are access-aware lower bounds")
    lines.append("- azure/gcs scans record no owner attribution")
    with open(out_dir / "PROPOSAL.md", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"proposal saved to {out_dir}/.")
    return out_dir


def _rule_summary(rule):
    """A one-line summary of a lifecycle rule or IT config for the diff."""
    prefix = _effective_prefix(rule) or "(whole bucket)"
    trans = rule.get("Transitions") or rule.get("Tierings") or []
    steps = ", ".join(
        f"{t.get('Days', '?')}d->{t.get('StorageClass') or t.get('AccessTier')}"
        for t in trans)
    expiry = rule.get("Expiration", {})
    if expiry.get("Days") is not None:
        steps += f", expire {expiry['Days']}d"
    return f"{prefix}  [{steps}]" if steps else prefix


def _print_rule_set(label, rule_set, flags, id_key):
    """
    Render one config kind's diff for a bucket, rule-by-rule.

    :param label: "lifecycle" or "intelligent-tiering"
    :param rule_set: diff.RuleSetDiff or None
    :param flags: dict — unknown / no_live / not_generated / untouched
    :param id_key: the rule identity field
    """
    if flags["unknown"]:
        print(f"  {label}: unknown — no permission to read config (403); "
              "cannot tell drift")
        return
    if flags["not_generated"]:
        # An apply issues no Put for this kind — live rules stay untouched.
        if flags["untouched"]:
            print(f"  {label}: not generated — an apply would not touch it "
                  f"({flags['untouched']} live rule(s) left as-is)")
        return
    if rule_set is None:
        return
    no_live = flags["no_live"]
    if not (rule_set.has_changes() or rule_set.unchanged):
        print(f"  {label}: no rules on either side")
        return
    if no_live:
        print(f"  {label}: no live config — every generated rule would be "
              "ADDED")
    else:
        print(f"  {label}:")
    for rule in rule_set.would_add:
        print(f"    + ADD     {rule[id_key]}  {_rule_summary(rule)}")
    for generated, live in rule_set.would_change:
        print(f"    ~ CHANGE  {generated[id_key]}")
        print(f"        generated: {_rule_summary(generated)}")
        print(f"        live:      {_rule_summary(live)}")
    for rule in rule_set.would_remove:
        print(f"    - REMOVE  {rule[id_key]}  ({DROP_WARNING})")
    for rule in rule_set.unchanged:
        print(f"    = same    {rule[id_key]}")


def print_config_diff(config_diff):
    """
    Render a ConfigDiff to the console — read-only, apply-ladder rung one.

    :param config_diff: diff.ConfigDiff
    """
    print("***********************************")
    print("*  dry-run diff (read-only)       *")
    print("***********************************")
    if not config_diff.buckets:
        print("no generated config for any bucket — an apply would change "
              "nothing (did you run a scan first?).")
        return
    for bucket in config_diff.buckets:
        print(f"bucket: {bucket.bucket}")
        _print_rule_set("lifecycle", bucket.lifecycle, {
            "unknown": bucket.unknown_lifecycle,
            "no_live": bucket.no_live_lifecycle,
            "not_generated": bucket.lifecycle_not_generated,
            "untouched": bucket.untouched_lifecycle}, "ID")
        _print_rule_set("intelligent-tiering", bucket.tiering, {
            "unknown": bucket.unknown_tiering,
            "no_live": bucket.no_live_tiering,
            "not_generated": bucket.tiering_not_generated,
            "untouched": bucket.untouched_tiering}, "Id")
    verdict = ("changes pending" if config_diff.has_changes()
               else "live already matches — no drift")
    print(f"read-only — nothing was written. this is what an apply WOULD "
          f"do ({verdict}).")
