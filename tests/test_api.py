"""
Purpose: API tests via FastAPI TestClient over an in-memory catalog.
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
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    create_all(engine)
    maker = session_factory(engine)
    session = maker()
    res = Resource(cloud="aws", scope_id="1", region="us-east-1",
                   rtype="ec2:instance", resource_id="arn:i-abc", name="web1",
                   tags={"Environment": "nope"})
    run = ScanRun(status="complete", resources_seen=1, violation_count=1, skips=[])
    session.add_all([res, run])
    session.commit()
    session.add(Violation(scan_run_id=run.id, resource_pk=res.id,
                          rule_key="Environment", value="nope", issue="invalid"))
    session.commit()
    app = create_app(Settings(auth_mode="none"), maker)
    return TestClient(app)


def test_health():
    """Health check endpoint."""
    assert _client().get("/api/health").json() == {"status": "ok"}


def test_resources_filter_by_cloud():
    """Resources endpoint filters by cloud."""
    client = _client()
    assert len(client.get("/api/resources?cloud=aws").json()) == 1
    assert client.get("/api/resources?cloud=azure").json() == []


def test_resources_filter_by_tag():
    """Resources endpoint filters by tag key and value."""
    client = _client()
    hits = client.get("/api/resources?tag_key=Environment&tag_value=nope").json()
    assert len(hits) == 1 and hits[0]["name"] == "web1"


def test_violations_and_scans():
    """Violations and scans endpoints."""
    client = _client()
    violations = client.get("/api/violations").json()
    assert violations[0]["rule_key"] == "Environment"
    scans = client.get("/api/scans").json()
    assert scans[0]["status"] == "complete"
