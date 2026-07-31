"""
Purpose: Shared query helpers for the API and UI routers — keeps the
violations query (join, latest-run scoping, cloud filter) in one place
instead of duplicated between main.py and ui.py.
Author(s): John Reed
"""

from tagmanager.models.tables import Resource, ScanRun, Violation


def scope_violations_to_latest_run(session, query):
    """
    Restrict a Violation query to the most recent ScanRun.

    :param session: SQLAlchemy session
    :param query: base Violation query to restrict
    :returns: query filtered to the latest run's scan_run_id; filters to a
        run id that can never match if no runs exist yet, so callers get
        an empty result instead of an error
    """
    run = session.query(ScanRun).order_by(ScanRun.id.desc()).first()
    return query.filter(Violation.scan_run_id == (run.id if run else -1))


def violations_query(session, cloud="", latest_only=True):
    """
    Build the base violations query — Violation joined to Resource,
    optionally scoped to the latest run and filtered by cloud.

    :param session: SQLAlchemy session
    :param cloud: optional cloud filter
    :param latest_only: when True (default), restrict to the latest
        ScanRun's findings instead of every run's
    :returns: query of (Violation, Resource) pairs
    """
    query = (session.query(Violation, Resource)
             .join(Resource, Violation.resource_pk == Resource.id))
    if latest_only:
        query = scope_violations_to_latest_run(session, query)
    if cloud:
        query = query.filter(Resource.cloud == cloud)
    return query
