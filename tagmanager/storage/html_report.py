"""
Purpose: Standalone storage insights HTML report — everything the
milestone computes on one page: age distribution, cost, per-option
savings, structure recommendations, artifacts index. Stdlib rendering,
same visual family as the classic report, html.escape on every dynamic
value.
Author(s): John Reed
"""

import html

from tagmanager.storage.output import fmt_bytes
from tagmanager.storage.rollup import band_labels
from tagmanager.storage.structure import out_of_scope_notes


def _esc(value):
    """Escape any dynamic value for HTML."""
    return html.escape(str(value))


def _table(headers, rows):
    """Simple bordered table (classic-report style)."""
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>"
        for row in rows)
    return (f'<table border="1" cellpadding="4" cellspacing="0">'
            f"<tr>{head}</tr>{body}</table>")


def _age_section(stats, age_band_days):
    """Age distribution table from stat rows."""
    totals = {}
    for stat in stats:
        entry = totals.setdefault(stat.age_band, [0, 0])
        entry[0] += stat.object_count
        entry[1] += stat.total_bytes
    rows = [(band, totals[band][0], fmt_bytes(totals[band][1]))
            for band in band_labels(age_band_days) if band in totals]
    if not rows:
        return "<p>no objects in this run.</p>"
    return _table(["age band", "objects", "bytes"], rows)


def _cost_section(report):
    """Cost table from a CostReport, or an honest absence note."""
    if report is None:
        return "<p>no pricing snapshot for this backend — costs omitted.</p>"
    rows = [(f"{row.container}/{row.prefix}" if row.prefix else row.container,
             row.storage_class, row.age_band, f"${row.monthly_cost:,.2f}/mo")
            for row in report.rows[:20]]
    extra = ""
    if len(report.rows) > 20:
        extra = f"<p>... {len(report.rows) - 20} more cells in the CSV.</p>"
    total = (f"<p><b>total: ${report.total_monthly_cost:,.2f}/mo</b> "
             f"(estimate — list pricing, {_esc(report.region)}, snapshot "
             f"{_esc(report.as_of_date)})</p>")
    return _table(["location", "class", "age band", "monthly cost"],
                  rows) + extra + total


def _savings_section(projections):
    """Per-option savings table."""
    if not projections:
        return "<p>no projections available.</p>"
    rows = []
    for proj in projections:
        breakeven = (f"{proj.break_even_months:.1f} mo"
                     if proj.break_even_months is not None else "—")
        flag = "NOT RECOMMENDED" if proj.not_recommended else ""
        rows.append((proj.option, f"${proj.monthly_savings:,.2f}/mo",
                     f"${proj.annual_savings:,.2f}/yr", breakeven, flag,
                     "; ".join(proj.caveats)))
    return _table(["option", "monthly", "annual", "break-even", "flag",
                   "caveats"], rows)


def _structure_section(recs_json, notes):
    """Structure recommendations table from the run's persisted JSON."""
    if not recs_json:
        return ("<p>no reorg recommended — the layout already fits "
                "prefix-scoped lifecycle rules (or --recommend-structure "
                "has not run).</p>")
    rows = []
    for rec in recs_json:
        if rec.get("kind") == "truncated":
            rows.append(("...", "", rec.get("note", ""), "", "", ""))
            continue
        loc = (f"{rec['container']}/{rec['prefix']}" if rec.get("prefix")
               else rec.get("container", ""))
        stake = rec.get("monthly_cost_at_stake") or 0
        rows.append((rec.get("kind", ""), loc,
                     rec.get("rationale", ""),
                     f"${stake:,.2f}/mo" if stake else "—",
                     ", ".join(rec.get("top_owners", [])),
                     ", ".join(rec.get("top_types", []))))
    note_html = "".join(f"<li>{_esc(note)}</li>" for note in notes)
    return (_table(["kind", "location", "rationale", "at stake",
                    "top owners", "top types"], rows)
            + f"<ul>{note_html}</ul>")


def _artifacts_section(artifacts):
    """Artifacts index from the run's recorded emit metadata."""
    if not artifacts:
        return "<p>no artifacts generated for this run.</p>"
    rows = [(entry.get("kind", ""), entry.get("dir", ""),
             entry.get("counts", ""))
            for entry in artifacts]
    return _table(["kind", "directory", "counts"], rows)


def render_storage_report(run, stats, cost_report=None, projections=None):
    """
    The full storage insights page for one scan run.

    :param run: StorageScanRun
    :param stats: its StoragePrefixStat rows
    :param cost_report: CostReport or None (no pricing for the backend)
    :param projections: OptionProjection list or None
    :returns: HTML document string
    """
    age_basis = ("access-aware — newest of modified/read; access times are "
                 "lower bounds" if run.access_aware
                 else "last modified only")
    started = run.started_at.date().isoformat() if run.started_at else "?"
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>TagManager — storage insights</title></head><body>",
        "<h1>Storage insights</h1>",
        f"<p>backend: <b>{_esc(run.backend)}</b> · scanned: "
        f"{_esc(started)} · objects: {run.objects_seen} · total: "
        f"{_esc(fmt_bytes(run.bytes_seen))}</p>",
        f"<p>age basis: {_esc(age_basis)}. All dollar figures are "
        "estimates from list pricing — this is not a bill.</p>",
        "<h2>Age distribution</h2>",
        _age_section(stats, run.age_band_days),
        "<h2>Stale-data cost</h2>",
        _cost_section(cost_report),
        "<h2>Savings options</h2>",
        _savings_section(projections),
        "<h2>Structure recommendations</h2>",
        _structure_section(
            list(run.structure_recs or []),
            out_of_scope_notes(
                any(getattr(s, "data_type", "") for s in stats),
                bool(run.request_rates))),
        "<h2>Generated artifacts</h2>",
        _artifacts_section(list(run.artifacts or [])),
        "</body></html>",
    ]
    return "".join(parts)
