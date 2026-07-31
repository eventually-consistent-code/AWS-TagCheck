"""
Purpose: Unit tests for the TagManager data model (SQLite in-memory).
Author(s): John Reed
"""

from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import Resource, RuleRow, ScanRun, Scope, Violation


def _session():
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    return session_factory(engine)()


def test_resource_roundtrip():
    session = _session()
    session.add(Resource(cloud="aws", scope_id="111122223333", region="us-east-1",
                         rtype="ec2:instance", resource_id="i-abc", name="web1",
                         tags={"Environment": "Prod"}))
    session.commit()
    row = session.query(Resource).one()
    assert row.tags == {"Environment": "Prod"}
    assert row.cloud == "aws"


def test_scan_run_with_violation():
    session = _session()
    res = Resource(cloud="aws", scope_id="1", region="r", rtype="t",
                   resource_id="i-1", name="n", tags={})
    run = ScanRun(status="running", resources_seen=0, violation_count=0, skips=[])
    session.add_all([res, run])
    session.commit()
    session.add(Violation(scan_run_id=run.id, resource_pk=res.id,
                          rule_key="Environment", value="", issue="missing"))
    session.commit()
    assert session.query(Violation).one().issue == "missing"


def test_rule_and_scope_tables():
    session = _session()
    session.add_all([
        RuleRow(key="Environment", allowed_values=["Prod", "Dev"]),
        Scope(cloud="azure", scope_id="sub-1", display_name="Core", enabled=True),
    ])
    session.commit()
    assert session.query(RuleRow).one().allowed_values == ["Prod", "Dev"]
    assert session.query(Scope).one().enabled is True
