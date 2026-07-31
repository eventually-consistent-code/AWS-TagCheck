"""
Purpose: UI smoke tests — pages render with catalog data present.
Author(s): John Reed
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from tagmanager.app.main import create_app
from tagmanager.config import Settings
from tagmanager.models.base import create_all, session_factory
from tagmanager.models.tables import Resource, ScanRun, Violation


def _client():
    """Build a test client with sample data."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    create_all(engine)
    maker = session_factory(engine)
    session = maker()
    res = Resource(cloud="gcp", scope_id="p1", region="us-central1",
                   rtype="compute.googleapis.com/Instance",
                   resource_id="//inst/web1", name="web1", tags={"env": "prod"})
    run = ScanRun(status="partial", resources_seen=1, violation_count=1,
                  skips=[{"scope_id": "p2", "error": "denied"}])
    session.add_all([res, run])
    session.commit()
    session.add(Violation(scan_run_id=run.id, resource_pk=res.id,
                          rule_key="owner", value="", issue="missing"))
    session.commit()
    return TestClient(create_app(Settings(auth_mode="none"), maker))


def test_dashboard_renders_scan_status():
    """Dashboard page renders latest scan data."""
    body = _client().get("/").text
    assert "TagManager" in body
    assert "partial" in body


def test_resources_page_lists_and_filters():
    """Resources page lists all resources and filters by cloud."""
    client = _client()
    assert "web1" in client.get("/resources").text
    assert "web1" not in client.get("/resources?cloud=aws").text


def test_violations_page_lists_findings():
    """Violations page displays all findings."""
    body = _client().get("/violations").text
    assert "owner" in body and "missing" in body
