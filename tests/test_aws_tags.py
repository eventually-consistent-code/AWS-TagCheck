"""
Purpose: Unit tests for tag evaluation helpers (no live AWS).
Author(s): John Reed
"""

import aws


def test_check_data_ok():
    assert aws.check_data("Prod", ["Prod", "Dev"]) is None


def test_check_data_bad():
    assert aws.check_data("prod", ["Prod", "Dev"]) == "prod"


def test_evaluate_required_tags_clean():
    canonical = {"Environment": ["Prod"], "Product": ["Core"]}
    tags = {"Environment": "Prod", "Product": "Core", "Name": "web"}
    assert aws.evaluate_required_tags(tags, canonical) == []


def test_evaluate_required_tags_missing():
    canonical = {"Environment": ["Prod"], "Product": ["Core"]}
    findings = aws.evaluate_required_tags({}, canonical)
    by_key = {f["tag_key"]: f for f in findings}
    assert by_key["Environment"]["issue"] == "missing"
    assert by_key["Environment"]["tag_value"] == "missing environment"
    assert by_key["Product"]["issue"] == "missing"
    assert by_key["Product"]["tag_value"] == "missing product"


def test_evaluate_required_tags_invalid_and_empty():
    canonical = {"Environment": ["Prod"], "Product": ["Core"]}
    findings = aws.evaluate_required_tags(
        {"Environment": "prod", "Product": ""},
        canonical,
    )
    assert len(findings) == 2
    assert findings[0] == {
        "tag_key": "Environment",
        "tag_value": "prod",
        "issue": "invalid",
    }
    assert findings[1]["issue"] == "invalid"
    assert findings[1]["tag_value"] == ""


def test_tags_to_dict():
    assert aws.tags_to_dict({}) == {}
    assert aws.tags_to_dict({"Tags": None}) == {}
    assert aws.tags_to_dict(
        {"Tags": [{"Key": "Name", "Value": "n"}, {"Key": "Product", "Value": "Core"}]}
    ) == {"Name": "n", "Product": "Core"}
