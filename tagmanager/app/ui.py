"""
Purpose: Server-rendered read-only UI — dashboard, resource browser,
violation list.
Author(s): John Reed
"""

from fastapi import APIRouter, Request
from sqlalchemy import func

from tagmanager.models.tables import Resource, ScanRun, Violation


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
            violating = (session.query(func.count(func.distinct(  # pylint: disable=not-callable
                Violation.resource_pk))).scalar() or 0)
            compliance = 100
            if run and run.resources_seen:
                compliance = round(100 * (1 - violating / run.resources_seen))
            return templates.TemplateResponse(request, "dashboard.html", {
                "run": run, "by_cloud": by_cloud, "compliance_pct": compliance})
        finally:
            session.close()

    @router.get("/resources")
    def resources(request: Request, cloud: str = "", rtype: str = ""):
        """Filterable resource table."""
        session = session_maker()
        try:
            query = session.query(Resource)
            if cloud:
                query = query.filter(Resource.cloud == cloud)
            if rtype:
                query = query.filter(Resource.rtype == rtype)
            return templates.TemplateResponse(request, "resources.html", {
                "rows": query.all(), "cloud": cloud, "rtype": rtype})
        finally:
            session.close()

    @router.get("/violations")
    def violations(request: Request):
        """All findings joined to their resources."""
        session = session_maker()
        try:
            rows = (session.query(Violation, Resource)
                    .join(Resource, Violation.resource_pk == Resource.id).all())
            return templates.TemplateResponse(request, "violations.html",
                                              {"rows": rows})
        finally:
            session.close()

    return router
