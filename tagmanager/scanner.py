"""
Purpose: Scanner service — fan out over configured scopes, upsert the
catalog, evaluate rules, record skips without failing the whole run.
Author(s): John Reed
"""

import datetime
import logging

from tagmanager.models.tables import Resource, RuleRow, ScanRun, Violation
from tagmanager.rules.engine import evaluate_resource

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.scanner")
LOG.setLevel(logging.INFO)


def _upsert(session, run, normalized):
    """
    Insert or update the Resource row for one normalized resource.

    :param session: SQLAlchemy session
    :param run: ScanRun row
    :param normalized: NormalizedResource
    :returns: Resource row
    """
    row = session.query(Resource).filter_by(
        cloud=normalized.cloud, resource_id=normalized.resource_id).one_or_none()
    if row is None:
        row = Resource(cloud=normalized.cloud, resource_id=normalized.resource_id)
        session.add(row)
    row.scope_id = normalized.scope_id
    row.region = normalized.region
    row.rtype = normalized.rtype
    row.name = normalized.name
    row.tags = normalized.tags
    row.last_seen_run_id = run.id
    return row


def run_scan(session, providers, scopes):
    """
    Run one scan across every scope; one failing scope becomes a skip.

    :param session: SQLAlchemy session
    :param providers: dict of cloud name -> Provider
    :param scopes: list of ScopeConfig
    :returns: the finished ScanRun
    """
    run = ScanRun(status="running", skips=[])
    session.add(run)
    session.commit()
    rules = session.query(RuleRow).all()
    seen = 0
    violations = 0
    skips = []

    for scope in scopes:
        provider = providers[scope.cloud]
        LOG.info("scanning %s scope %s...", scope.cloud, scope.scope_id)
        try:
            for normalized in provider.list_resources(scope):
                seen += 1
                row = _upsert(session, run, normalized)
                session.flush()
                for finding in evaluate_resource(normalized, rules):
                    violations += 1
                    session.add(Violation(
                        scan_run_id=run.id, resource_pk=row.id,
                        rule_key=finding["rule_key"], value=finding["value"],
                        issue=finding["issue"]))
        except Exception as err:  # pylint: disable=broad-except
            # scope isolation is the contract — one scope failure is a skip
            LOG.warning("skipping scope %s (%s)...", scope.scope_id, err)
            skips.append({"scope_id": scope.scope_id, "error": str(err)})

    run.resources_seen = seen
    run.violation_count = violations
    run.skips = skips
    run.status = "partial" if skips else "complete"
    run.finished_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
    LOG.info("scan complete... %s resource(s), %s violation(s), %s skip(s)",
             seen, violations, len(skips))
    return run
