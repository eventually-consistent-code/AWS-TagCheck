"""
Purpose: FastAPI application — JSON API for the catalog plus (Task 11) the
server-rendered UI. App factory keeps settings and DB injectable for tests.
Author(s): John Reed
"""

import logging
import pathlib

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tagmanager.app.auth import install_auth
from tagmanager.app.queries import violations_query
from tagmanager.app.storage_ui import (storage_insights_router,
                                       storage_ui_router)
from tagmanager.app.ui import ui_router
from tagmanager.models.tables import Resource, ScanRun, Violation

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.app")
LOG.setLevel(logging.INFO)


def create_app(settings, session_maker, scheduler=None):
    """
    Build the FastAPI app.

    :param settings: Settings
    :param session_maker: sessionmaker bound to the catalog DB
    :param scheduler: APScheduler instance for storage scan triggers
        (None disables web-triggered scans)
    :returns: FastAPI app
    """
    app = FastAPI(title="TagManager")

    def db():
        session = session_maker()
        try:
            yield session
        finally:
            session.close()

    @app.get("/api/health")
    def health():
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/api/resources")
    def resources(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cloud: str = "", scope_id: str = "", rtype: str = "",
            tag_key: str = "", tag_value: str = "",
            session=Depends(db)):
        """Filtered catalog listing."""
        query = session.query(Resource)
        if cloud:
            query = query.filter(Resource.cloud == cloud)
        if scope_id:
            query = query.filter(Resource.scope_id == scope_id)
        if rtype:
            query = query.filter(Resource.rtype == rtype)
        rows = query.all()
        if tag_key:
            rows = [r for r in rows if tag_key in r.tags and
                    (not tag_value or r.tags.get(tag_key) == tag_value)]
        return [{"id": r.id, "cloud": r.cloud, "scope_id": r.scope_id,
                 "region": r.region, "rtype": r.rtype,
                 "resource_id": r.resource_id, "name": r.name, "tags": r.tags}
                for r in rows]

    @app.get("/api/violations")
    def violations(  # pylint: disable=redefined-builtin
            cloud: str = "", rule_key: str = "", all: int = 0,
            session=Depends(db)):
        """Violation listing joined to resources — latest run only unless
        ?all=1, matching the UI's /violations scoping."""
        query = violations_query(session, cloud, latest_only=not all)
        if rule_key:
            query = query.filter(Violation.rule_key == rule_key)
        return [{"resource_id": res.resource_id, "name": res.name,
                 "cloud": res.cloud, "rule_key": v.rule_key, "value": v.value,
                 "issue": v.issue, "scan_run_id": v.scan_run_id}
                for v, res in query.all()]

    @app.get("/api/scans")
    def scans(session=Depends(db)):
        """Scan-run history, newest first."""
        rows = session.query(ScanRun).order_by(ScanRun.id.desc()).all()
        return [{"id": r.id, "started_at": r.started_at.isoformat(),
                 "status": r.status, "resources_seen": r.resources_seen,
                 "violation_count": r.violation_count, "skips": r.skips}
                for r in rows]

    templates = Jinja2Templates(
        directory=str(pathlib.Path(__file__).parent / "templates"))
    app.mount("/static", StaticFiles(
        directory=str(pathlib.Path(__file__).parent / "static")), name="static")
    app.include_router(ui_router(templates, session_maker))
    app.include_router(storage_ui_router(templates, session_maker,
                                         scheduler))
    app.include_router(storage_insights_router(templates, session_maker,
                                               settings))
    app.state.scheduler = scheduler

    app.state.settings = settings
    install_auth(app, settings)
    return app
