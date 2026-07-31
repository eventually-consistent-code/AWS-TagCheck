"""
Purpose: Server-rendered read-only UI — dashboard, resource browser,
violation list.
Author(s): John Reed
"""

from fastapi import APIRouter, Request
from sqlalchemy import func
from sqlalchemy.exc import OperationalError

from tagmanager.app.queries import violations_query
from tagmanager.models.tables import (Resource, ScanRun, StoragePrefixStat,
                                      StorageScanRun, Violation)


def ui_router(templates, session_maker):
    """
    Build the UI router.

    :param templates: Jinja2Templates
    :param session_maker: sessionmaker
    :returns: APIRouter
    """
    router = APIRouter()

    @router.get("/")
    def dashboard(request: Request):
        """Latest scan status + per-cloud counts."""
        session = session_maker()
        try:
            run = session.query(ScanRun).order_by(ScanRun.id.desc()).first()
            by_cloud = (session.query(Resource.cloud, func.count(Resource.id))  # pylint: disable=not-callable
                        .group_by(Resource.cloud).all())
            # Count distinct resources with violations in the latest run only
            violating = 0
            if run:
                violating = (session.query(func.count(func.distinct(  # pylint: disable=not-callable
                    Violation.resource_pk)))
                    .filter(Violation.scan_run_id == run.id).scalar() or 0)
            compliance = 100
            if run and run.resources_seen:
                compliance = round(100 * (1 - violating / run.resources_seen))
            return templates.TemplateResponse(request, "dashboard.html", {
                "run": run, "by_cloud": by_cloud, "compliance_pct": compliance})
        finally:
            session.close()

    @router.get("/resources")
    def resources(request: Request, cloud: str = "", rtype: str = "",
                  tag_key: str = ""):
        """Filterable resource table."""
        session = session_maker()
        try:
            query = session.query(Resource)
            if cloud:
                query = query.filter(Resource.cloud == cloud)
            if rtype:
                query = query.filter(Resource.rtype == rtype)
            rows = query.all()
            # Filter by tag_key if provided (mirror /api/resources logic)
            if tag_key:
                rows = [r for r in rows if tag_key in r.tags]
            return templates.TemplateResponse(request, "resources.html", {
                "rows": rows, "cloud": cloud, "rtype": rtype, "tag_key": tag_key})
        finally:
            session.close()

    @router.get("/violations")
    def violations(request: Request, cloud: str = "", all: int = 0):  # pylint: disable=redefined-builtin
        """Findings joined to their resources — latest run only unless
        ?all=1, matching the rest of the dashboard's latest-run scoping."""
        session = session_maker()
        try:
            query = violations_query(session, cloud, latest_only=not all)
            return templates.TemplateResponse(request, "violations.html",
                                              {"rows": query.all(), "cloud": cloud})
        finally:
            session.close()

    @router.get("/storage")
    def storage(request: Request):
        """Latest storage scan: bands, top cost prefixes, recommendations."""
        session = session_maker()
        try:
            run = (session.query(StorageScanRun)
                   .filter(StorageScanRun.status.in_(["complete", "partial"]))
                   .order_by(StorageScanRun.id.desc()).first())
            band_rows = []
            top_cells = []
            if run:
                stats = (session.query(StoragePrefixStat)
                         .filter(StoragePrefixStat.scan_run_id == run.id)
                         .all())
                bands = {}
                for stat in stats:
                    entry = bands.setdefault(stat.age_band, [0, 0])
                    entry[0] += stat.object_count
                    entry[1] += stat.total_bytes
                band_rows = sorted(bands.items())
                merged = {}
                for stat in stats:
                    key = (stat.container, stat.prefix, stat.storage_class,
                           stat.age_band)
                    row = merged.setdefault(key, [0, 0])
                    row[0] += stat.object_count
                    row[1] += stat.total_bytes
                top_cells = sorted(
                    ((key, counts) for key, counts in merged.items()),
                    key=lambda item: -item[1][1])[:10]
            return templates.TemplateResponse(request, "storage.html", {
                "run": run, "band_rows": band_rows, "top_cells": top_cells,
                "recs": list(run.structure_recs or []) if run else [],
                "stale_schema": False})
        except OperationalError:
            # Old dev DB missing new storage columns — say so, don't 500.
            return templates.TemplateResponse(request, "storage.html", {
                "run": None, "band_rows": [], "top_cells": [], "recs": [],
                "stale_schema": True})
        finally:
            session.close()

    return router
