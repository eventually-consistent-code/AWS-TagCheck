"""
Purpose: Unit tests for the scanner service — upsert, violations, skip isolation.
Author(s): John Reed
"""

from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import Resource, RuleRow, Violation
from tagmanager.providers.base import (
    NormalizedResource,
    Provider,
    ProviderCapabilities,
    ScopeConfig,
)
from tagmanager.scanner import run_scan


class _StubProvider(Provider):
    """Stub provider for testing — yields resources or raises on demand."""
    cloud_name = "stub"

    def __init__(self, resources_by_scope):
        """
        Initialize stub provider.

        :param resources_by_scope: dict mapping scope_id to list of resources or Exception
        """
        self._by_scope = resources_by_scope

    def list_resources(self, scope):
        """
        List resources for a scope; raise if value is an Exception.

        :param scope: ScopeConfig
        """
        value = self._by_scope[scope.scope_id]
        if isinstance(value, Exception):
            raise value
        yield from value

    def capabilities(self):
        """Return capabilities for this provider."""
        return ProviderCapabilities(supports_direct_write=False)


def _res(rid, tags):
    """
    Construct a normalized resource for testing.

    :param rid: resource ID
    :param tags: tags dict
    :returns: NormalizedResource
    """
    return NormalizedResource(cloud="stub", scope_id="s1", region="r", rtype="t",
                              resource_id=rid, name=rid, tags=tags)


def _session():
    """
    Create an in-memory SQLite session with schema and a test rule.

    :returns: SQLAlchemy session
    """
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    session = session_factory(engine)()
    session.add(RuleRow(key="Environment", allowed_values=["Prod"]))
    session.commit()
    return session


def test_scan_upserts_and_finds_violations():
    """Scan creates resource rows and records violations."""
    session = _session()
    provider = _StubProvider({"s1": [_res("a", {"Environment": "Prod"}),
                                     _res("b", {})]})
    scope = ScopeConfig(cloud="stub", scope_id="s1", credentials={})

    run = run_scan(session, {"stub": provider}, [scope])

    assert run.status == "complete"
    assert run.resources_seen == 2
    assert run.violation_count == 1
    violation = session.query(Violation).one()
    assert violation.rule_key == "Environment"
    assert violation.issue == "missing"


def test_rescan_updates_not_duplicates():
    """Rescan with same resource ID updates tags, does not duplicate."""
    session = _session()
    scope = ScopeConfig(cloud="stub", scope_id="s1", credentials={})
    run_scan(session, {"stub": _StubProvider({"s1": [_res("a", {})]})}, [scope])
    run_scan(session, {"stub": _StubProvider(
        {"s1": [_res("a", {"Environment": "Prod"})]})}, [scope])
    assert session.query(Resource).count() == 1
    assert session.query(Resource).one().tags == {"Environment": "Prod"}


def test_scope_failure_isolated_as_skip():
    """One scope fails; others continue; skip recorded; status is partial."""
    session = _session()
    provider = _StubProvider({"bad": RuntimeError("denied"),
                              "good": [_res("a", {"Environment": "Prod"})]})
    scopes = [ScopeConfig(cloud="stub", scope_id="bad", credentials={}),
              ScopeConfig(cloud="stub", scope_id="good", credentials={})]

    run = run_scan(session, {"stub": provider}, scopes)

    assert run.status == "partial"
    assert run.skips == [{"scope_id": "bad", "error": "denied"}]
    assert run.resources_seen == 1
