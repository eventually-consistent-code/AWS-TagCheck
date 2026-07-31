"""
Purpose: Unit tests for the rules engine and canonical.json seeding.
Author(s): John Reed
"""

from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import RuleRow
from tagmanager.providers.base import NormalizedResource
from tagmanager.rules.engine import evaluate_resource, seed_rules_from_canonical


def _resource(tags, cloud="aws", rtype="ec2:instance"):
    """
    Helper to create a NormalizedResource for testing.
    """
    return NormalizedResource(cloud=cloud, scope_id="s", region="r", rtype=rtype,
                              resource_id="x", name="n", tags=tags)


def _rules():
    """
    Helper to create a list of test RuleRows.
    """
    return [RuleRow(key="Environment", allowed_values=["Prod", "Dev"]),
            RuleRow(key="Product", allowed_values=["Core"])]


def test_missing_and_invalid():
    """
    Test that missing tags and invalid values are detected.
    """
    findings = evaluate_resource(_resource({"Environment": "nope"}), _rules())
    assert {"rule_key": "Environment", "value": "nope", "issue": "invalid"} in findings
    assert {"rule_key": "Product", "value": "", "issue": "missing"} in findings


def test_clean_resource_no_findings():
    """
    Test that a resource with all valid tags produces no findings.
    """
    findings = evaluate_resource(
        _resource({"Environment": "Prod", "Product": "Core"}), _rules())
    assert findings == []


def test_cloud_scoped_rule_skips_other_cloud():
    """
    Test that cloud-scoped rules only apply to matching clouds.
    """
    rule = RuleRow(key="CostCenter", allowed_values=["cc1"], applies_cloud="azure")
    assert evaluate_resource(_resource({}, cloud="aws"), [rule]) == []
    assert evaluate_resource(_resource({}, cloud="azure"), [rule]) == [
        {"rule_key": "CostCenter", "value": "", "issue": "missing"}]


def test_seed_from_canonical(tmp_path):
    """
    Test that seed_rules_from_canonical correctly loads rules from canonical.json.
    """
    canonical = tmp_path / "canonical.json"
    canonical.write_text('{"Environment": ["Prod"], "Product": ["Core"]}',
                         encoding="utf-8")
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    session = session_factory(engine)()
    seed_rules_from_canonical(session, str(canonical))
    seed_rules_from_canonical(session, str(canonical))  # idempotent
    assert session.query(RuleRow).count() == 2
