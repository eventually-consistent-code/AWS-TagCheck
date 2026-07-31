"""
Purpose: Rules engine — evaluate normalized resources against required-tag
rules, and seed the rules table from a legacy canonical.json.
Author(s): John Reed
"""

import json
import logging

from tagmanager.models.tables import RuleRow

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.rules_engine")
LOG.setLevel(logging.INFO)


def _rule_applies(rule, resource):
    """
    Check whether a rule applies to a resource based on cloud and type scoping.
    """
    if rule.applies_cloud and rule.applies_cloud != resource.cloud:
        return False
    if rule.applies_type and rule.applies_type != resource.rtype:
        return False
    return True


def evaluate_resource(resource, rules):
    """
    Evaluate one resource against the rules.

    :param resource: NormalizedResource
    :param rules: iterable with .key/.allowed_values/.applies_cloud/.applies_type
    :returns: list of {rule_key, value, issue} findings
    """
    findings = []
    for rule in rules:
        if not _rule_applies(rule, resource):
            continue
        if rule.key not in resource.tags:
            findings.append({"rule_key": rule.key, "value": "", "issue": "missing"})
            continue
        value = resource.tags[rule.key]
        if value not in rule.allowed_values:
            findings.append({"rule_key": rule.key, "value": value, "issue": "invalid"})
    return findings


def seed_rules_from_canonical(session, path):
    """
    Seed the rules table from canonical.json when the table is empty.

    :param session: SQLAlchemy session
    :param path: path to canonical.json
    """
    if session.query(RuleRow).count():
        return
    LOG.info("seeding rules from %s...", path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for key, values in data.items():
        session.add(RuleRow(key=key, allowed_values=list(values)))
    session.commit()
    LOG.info("rules seeded... %s rule(s)", len(data))
