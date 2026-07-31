"""
Purpose: Console tables and CSV writers for the storage CLI — summaries,
cost reports, savings projections, layout proposals. Pure presentation;
no scanning, no pricing math.
Author(s): John Reed
"""

import csv
import pathlib

from tagmanager.storage.rollup import band_labels


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
