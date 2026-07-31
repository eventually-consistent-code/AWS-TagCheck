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


def test_dashboard_compliance_scoped_to_latest_run():
    """
    Dashboard compliance % is based on latest scan run only.
    After second scan with no violations, compliance reaches 100%.
    """
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    create_all(engine)
    maker = session_factory(engine)
    session = maker()

    # First scan: 1 resource with 1 violation
    res1 = Resource(cloud="aws", scope_id="acc1", region="us-east-1",
                    rtype="ec2:instance", resource_id="arn:i-1",
                    name="web", tags={})
    run1 = ScanRun(status="complete", resources_seen=1, violation_count=1,
                   skips=[])
    session.add_all([res1, run1])
    session.commit()
    session.add(Violation(scan_run_id=run1.id, resource_pk=res1.id,
                          rule_key="owner", value="", issue="missing"))
    session.commit()

    # Second scan: same resource, no violations
    run2 = ScanRun(status="complete", resources_seen=1, violation_count=0,
                   skips=[])
    session.add(run2)
    session.commit()

    client = TestClient(create_app(Settings(auth_mode="none"), maker))
    body = client.get("/").text

    # Compliance should be 100% based on run2, not 0% based on run1
    assert "100%" in body
    assert "complete" in body


def test_resources_filter_by_tag_key():
    """Resources page filters by tag_key: only rows with that key."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    create_all(engine)
    maker = session_factory(engine)
    session = maker()

    res_prod = Resource(cloud="aws", scope_id="acc1", region="us-east-1",
                        rtype="ec2:instance", resource_id="arn:prod",
                        name="prod-web", tags={"env": "prod"})
    res_dev = Resource(cloud="aws", scope_id="acc1", region="us-east-1",
                       rtype="ec2:instance", resource_id="arn:dev",
                       name="dev-web", tags={"env": "dev", "team": "backend"})
    res_no_env = Resource(cloud="gcp", scope_id="p1", region="us-central1",
                          rtype="compute.googleapis.com/Instance",
                          resource_id="//inst/data", name="db", tags={})
    session.add_all([res_prod, res_dev, res_no_env])
    session.commit()

    client = TestClient(create_app(Settings(auth_mode="none"), maker))

    # All resources
    all_body = client.get("/resources").text
    assert "prod-web" in all_body and "dev-web" in all_body and "db" in all_body

    # Filter by tag_key=env
    env_body = client.get("/resources?tag_key=env").text
    assert "prod-web" in env_body and "dev-web" in env_body
    assert "db" not in env_body

    # Filter by tag_key=team (only one has it)
    team_body = client.get("/resources?tag_key=team").text
    assert "dev-web" in team_body
    assert "prod-web" not in team_body and "db" not in team_body


def test_violations_filter_by_cloud():
    """Violations page filters by cloud: only shows violations from that cloud."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    create_all(engine)
    maker = session_factory(engine)
    session = maker()

    # One AWS resource with violation
    aws_res = Resource(cloud="aws", scope_id="acc1", region="us-east-1",
                       rtype="ec2:instance", resource_id="arn:i-1",
                       name="aws-web", tags={})
    # One Azure resource with violation
    azure_res = Resource(cloud="azure", scope_id="sub1", region="eastus",
                         rtype="Microsoft.Compute/virtualMachines",
                         resource_id="/vms/vm1", name="azure-web", tags={})

    run = ScanRun(status="complete", resources_seen=2, violation_count=2,
                  skips=[])
    session.add_all([aws_res, azure_res, run])
    session.commit()

    session.add(Violation(scan_run_id=run.id, resource_pk=aws_res.id,
                          rule_key="owner", value="", issue="missing"))
    session.add(Violation(scan_run_id=run.id, resource_pk=azure_res.id,
                          rule_key="compliance", value="bad", issue="failed"))
    session.commit()

    client = TestClient(create_app(Settings(auth_mode="none"), maker))

    # All violations
    all_body = client.get("/violations").text
    assert "aws-web" in all_body and "azure-web" in all_body

    # Filter by cloud=aws
    aws_body = client.get("/violations?cloud=aws").text
    assert "aws-web" in aws_body
    assert "azure-web" not in aws_body

    # Filter by cloud=azure
    azure_body = client.get("/violations?cloud=azure").text
    assert "azure-web" in azure_body
    assert "aws-web" not in azure_body
