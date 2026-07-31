# TagManager Platform Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-cloud (AWS/Azure/GCP) tag-compliance platform: one container running FastAPI + Jinja/htmx UI, Postgres/SQLite catalog, provider plugin interface, rules engine, scheduled scans.

**Architecture:** Modular monolith in `tagmanager/` package. Providers normalize each cloud's bulk inventory API into one resource model; a scanner service upserts the catalog and evaluates DB-stored rules into violations; FastAPI serves JSON API + server-rendered read-only UI behind OIDC (with a dev bypass).

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.x, Jinja2 + htmx, APScheduler, authlib, pydantic-settings, boto3, azure-mgmt-resourcegraph, google-cloud-asset. Tests: pytest + unittest.mock stubs (no moto).

## Global Constraints

- Python 3.10 floor (matches CI workflow)
- pylint 10.00/10 with repo `pylintrc`; pycodestyle max-line-length 120 (`tox.ini`)
- TDD: every production change gets a failing test first
- John's coding style (`~/.claude/rules/coding-style.md`): module docstring preamble with Purpose/Author(s), `LOG = logging.getLogger("root.<module>")` pattern, chatty lowercase status logs with trailing `...`, docstrings on every function/class
- AWS test convention: stub clients via `unittest.mock` — assert on exact call args; same pattern for Azure/GCP SDKs
- Secrets only from env vars / cloud secret managers — never in code, config files, or DB
- Existing CLI `aws_tag_manager.py` and its 32 tests must stay green through every task
- New runtime deps land in `pyproject.toml` `[project.dependencies]`; test-only deps in `[dev]`

---

### Task 1: Package scaffold + settings

**Files:**
- Create: `tagmanager/__init__.py`, `tagmanager/config.py`
- Modify: `pyproject.toml` (add fastapi, uvicorn, sqlalchemy, jinja2, apscheduler, authlib, pydantic-settings, httpx to dependencies; keep boto3)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `tagmanager.config.Settings` (pydantic-settings BaseSettings) with fields `db_url: str = "sqlite:///tagmanager.db"`, `auth_mode: str = "none"` (`"none"|"oidc"`), `oidc_issuer: str = ""`, `oidc_client_id: str = ""`, `oidc_client_secret: str = ""`, `scan_interval_minutes: int = 60`, env prefix `TAGMANAGER_`. Function `get_settings() -> Settings`.

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Unit tests for tagmanager settings loading and env overrides.
Author(s): John Reed
"""

from tagmanager.config import Settings, get_settings


def test_settings_defaults():
    settings = Settings()
    assert settings.db_url == "sqlite:///tagmanager.db"
    assert settings.auth_mode == "none"
    assert settings.scan_interval_minutes == 60


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("TAGMANAGER_DB_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("TAGMANAGER_AUTH_MODE", "oidc")
    settings = Settings()
    assert settings.db_url == "postgresql://u:p@h/db"
    assert settings.auth_mode == "oidc"


def test_get_settings_returns_settings():
    assert isinstance(get_settings(), Settings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tagmanager'`

- [ ] **Step 3: Add deps and write minimal implementation**

In `pyproject.toml` dependencies add: `"fastapi>=0.110"`, `"uvicorn>=0.29"`, `"sqlalchemy>=2.0"`, `"jinja2>=3.1"`, `"apscheduler>=3.10"`, `"authlib>=1.3"`, `"pydantic-settings>=2.2"`, `"httpx>=0.27"`. Then `.venv/bin/pip install -e ".[dev]"`.

`tagmanager/__init__.py`:

```python
"""
Purpose: TagManager — multi-cloud tag compliance platform package.
Author(s): John Reed
"""
```

`tagmanager/config.py`:

```python
"""
Purpose: Settings for TagManager — env-driven config with TAGMANAGER_ prefix.
Author(s): John Reed
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings; every field overridable via TAGMANAGER_<FIELD> env var."""

    model_config = SettingsConfigDict(env_prefix="TAGMANAGER_")

    db_url: str = "sqlite:///tagmanager.db"
    auth_mode: str = "none"
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    scan_interval_minutes: int = 60


def get_settings():
    """
    Build a Settings instance from the environment.

    :returns: Settings
    """
    return Settings()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v` → PASS, then full suite `.venv/bin/python -m pytest tests/ -q` → all green (35 passed).

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_config.py
git add tagmanager/ tests/test_config.py pyproject.toml
git commit -m "Add tagmanager package scaffold and env-driven settings"
```

---

### Task 2: Data model + session factory

**Files:**
- Create: `tagmanager/models/__init__.py`, `tagmanager/models/base.py`, `tagmanager/models/tables.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `tagmanager.models.base.get_engine(db_url) -> Engine`, `create_all(engine)`, `session_factory(engine) -> sessionmaker`. `tagmanager.models.tables`: `Resource` (id, cloud, scope_id, region, rtype, resource_id, name, tags JSON, last_seen_run_id), `ScanRun` (id, started_at, finished_at, status `"running"|"complete"|"partial"`, resources_seen, violation_count, skips JSON), `Violation` (id, scan_run_id FK, resource_pk FK, rule_key, value, issue), `RuleRow` (id, key, allowed_values JSON, applies_cloud nullable, applies_type nullable), `Scope` (id, cloud, scope_id, display_name, regions JSON nullable, enabled bool). Unique constraint on Resource (cloud, resource_id).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tagmanager.models'`

- [ ] **Step 3: Write minimal implementation**

`tagmanager/models/__init__.py`: docstring-only preamble (same style as Task 1).

`tagmanager/models/base.py`:

```python
"""
Purpose: SQLAlchemy engine/session plumbing and declarative base.
Author(s): John Reed
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all TagManager tables."""


def get_engine(db_url):
    """
    Build an engine for the given database URL.

    :param db_url: SQLAlchemy database URL
    :returns: Engine
    """
    return create_engine(db_url)


def create_all(engine):
    """
    Create all tables (idempotent).

    :param engine: Engine
    """
    Base.metadata.create_all(engine)


def session_factory(engine):
    """
    Session factory bound to the engine.

    :param engine: Engine
    :returns: sessionmaker
    """
    return sessionmaker(bind=engine)
```

`tagmanager/models/tables.py`:

```python
"""
Purpose: TagManager tables — resources, scan runs, violations, rules, scopes.
Author(s): John Reed
"""

import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tagmanager.models.base import Base


class Resource(Base):
    """Current normalized state of one cloud resource."""

    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("cloud", "resource_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cloud: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[str] = mapped_column(String(128))
    region: Mapped[str] = mapped_column(String(64))
    rtype: Mapped[str] = mapped_column(String(128))
    resource_id: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(256), default="")
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    last_seen_run_id: Mapped[int] = mapped_column(Integer, nullable=True)


class ScanRun(Base):
    """One scheduled or manual scan execution."""

    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow)
    finished_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    resources_seen: Mapped[int] = mapped_column(Integer, default=0)
    violation_count: Mapped[int] = mapped_column(Integer, default=0)
    skips: Mapped[list] = mapped_column(JSON, default=list)


class Violation(Base):
    """One rule finding against one resource in one scan."""

    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    resource_pk: Mapped[int] = mapped_column(ForeignKey("resources.id"))
    rule_key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(512), default="")
    issue: Mapped[str] = mapped_column(String(32))


class RuleRow(Base):
    """One required-tag rule (allowed values, optional cloud/type scoping)."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128))
    allowed_values: Mapped[list] = mapped_column(JSON, default=list)
    applies_cloud: Mapped[str] = mapped_column(String(16), nullable=True)
    applies_type: Mapped[str] = mapped_column(String(128), nullable=True)


class Scope(Base):
    """One configured account / subscription / project to scan."""

    __tablename__ = "scopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cloud: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    regions: Mapped[list] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_models.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_models.py
git add tagmanager/models/ tests/test_models.py
git commit -m "Add data model: resources, scan runs, violations, rules, scopes"
```

---

### Task 3: Provider base — normalized resource + interface

**Files:**
- Create: `tagmanager/providers/__init__.py`, `tagmanager/providers/base.py`
- Test: `tests/test_provider_base.py`

**Interfaces:**
- Produces: `NormalizedResource` dataclass `(cloud, scope_id, region, rtype, resource_id, name, tags: dict)`; `ScopeConfig` dataclass `(cloud, scope_id, credentials: dict, regions: list | None = None)`; `ProviderCapabilities` dataclass `(supports_direct_write: bool)`; abstract class `Provider` with `cloud_name: str` class attr, abstract `list_resources(self, scope) -> Iterator[NormalizedResource]`, abstract `capabilities(self) -> ProviderCapabilities`, and concrete `apply_tags(self, scope, resource_id, tags)` / `export_changeset(self, changes)` both raising `NotImplementedError("sub-project 2")`.

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Unit tests for the provider base interface and normalized resource.
Author(s): John Reed
"""

import pytest

from tagmanager.providers.base import (
    NormalizedResource,
    Provider,
    ProviderCapabilities,
    ScopeConfig,
)


class _FakeProvider(Provider):
    cloud_name = "fake"

    def list_resources(self, scope):
        yield NormalizedResource(cloud="fake", scope_id=scope.scope_id,
                                 region="r1", rtype="thing", resource_id="x-1",
                                 name="one", tags={"k": "v"})

    def capabilities(self):
        return ProviderCapabilities(supports_direct_write=False)


def test_normalized_resource_fields():
    scope = ScopeConfig(cloud="fake", scope_id="s1", credentials={})
    resources = list(_FakeProvider().list_resources(scope))
    assert resources[0].tags == {"k": "v"}
    assert resources[0].scope_id == "s1"


def test_provider_cannot_instantiate_abstract():
    with pytest.raises(TypeError):
        Provider()  # pylint: disable=abstract-class-instantiated


def test_write_methods_reserved_for_sp2():
    provider = _FakeProvider()
    scope = ScopeConfig(cloud="fake", scope_id="s1", credentials={})
    with pytest.raises(NotImplementedError):
        provider.apply_tags(scope, "x-1", {"k": "v"})
    with pytest.raises(NotImplementedError):
        provider.export_changeset([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_provider_base.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`tagmanager/providers/__init__.py`: docstring preamble. `tagmanager/providers/base.py`:

```python
"""
Purpose: Provider plugin contract — normalized resource model, scope config,
capability flags, and the abstract interface every cloud implements.
Author(s): John Reed
"""

import abc
from dataclasses import dataclass, field


@dataclass
class NormalizedResource:
    """One cloud resource in cross-cloud normal form (labels become tags)."""

    cloud: str
    scope_id: str
    region: str
    rtype: str
    resource_id: str
    name: str
    tags: dict = field(default_factory=dict)


@dataclass
class ScopeConfig:
    """One account/subscription/project plus how to reach it."""

    cloud: str
    scope_id: str
    credentials: dict
    regions: list = None


@dataclass
class ProviderCapabilities:
    """What a provider can do beyond reading."""

    supports_direct_write: bool


class Provider(abc.ABC):
    """Abstract cloud provider: read now, write methods land in sub-project 2."""

    cloud_name = "abstract"

    @abc.abstractmethod
    def list_resources(self, scope):
        """
        Yield NormalizedResource for every taggable resource in the scope.

        :param scope: ScopeConfig
        :yields: NormalizedResource
        """

    @abc.abstractmethod
    def capabilities(self):
        """
        Declare provider capabilities.

        :returns: ProviderCapabilities
        """

    def apply_tags(self, scope, resource_id, tags):
        """Direct tag write — implemented in sub-project 2."""
        raise NotImplementedError("sub-project 2")

    def export_changeset(self, changes):
        """Change-set export — implemented in sub-project 2."""
        raise NotImplementedError("sub-project 2")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_provider_base.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_provider_base.py
git add tagmanager/providers/ tests/test_provider_base.py
git commit -m "Add provider base: normalized resource, scope config, abstract interface"
```

---

### Task 4: Rules engine + canonical seed

**Files:**
- Create: `tagmanager/rules/__init__.py`, `tagmanager/rules/engine.py`
- Test: `tests/test_rules_engine.py`

**Interfaces:**
- Consumes: `NormalizedResource` from Task 3; `RuleRow` from Task 2.
- Produces: `evaluate_resource(resource, rules) -> list[dict]` where each dict is `{"rule_key": str, "value": str, "issue": "missing"|"invalid"}` and `rules` is an iterable of objects with `.key`, `.allowed_values`, `.applies_cloud`, `.applies_type` (RuleRow satisfies this); `seed_rules_from_canonical(session, path)` — reads canonical.json `{"Environment": [...], "Product": [...]}` and inserts one RuleRow per key if the rules table is empty (idempotent).

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Unit tests for the rules engine and canonical.json seeding.
Author(s): John Reed
"""

from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import RuleRow
from tagmanager.providers.base import NormalizedResource
from tagmanager.rules.engine import evaluate_resource, seed_rules_from_canonical


def _resource(tags, cloud="aws", rtype="ec2:instance"):
    return NormalizedResource(cloud=cloud, scope_id="s", region="r", rtype=rtype,
                              resource_id="x", name="n", tags=tags)


def _rules():
    return [RuleRow(key="Environment", allowed_values=["Prod", "Dev"]),
            RuleRow(key="Product", allowed_values=["Core"])]


def test_missing_and_invalid():
    findings = evaluate_resource(_resource({"Environment": "nope"}), _rules())
    assert {"rule_key": "Environment", "value": "nope", "issue": "invalid"} in findings
    assert {"rule_key": "Product", "value": "", "issue": "missing"} in findings


def test_clean_resource_no_findings():
    findings = evaluate_resource(
        _resource({"Environment": "Prod", "Product": "Core"}), _rules())
    assert findings == []


def test_cloud_scoped_rule_skips_other_cloud():
    rule = RuleRow(key="CostCenter", allowed_values=["cc1"], applies_cloud="azure")
    assert evaluate_resource(_resource({}, cloud="aws"), [rule]) == []
    assert evaluate_resource(_resource({}, cloud="azure"), [rule]) == [
        {"rule_key": "CostCenter", "value": "", "issue": "missing"}]


def test_seed_from_canonical(tmp_path):
    canonical = tmp_path / "canonical.json"
    canonical.write_text('{"Environment": ["Prod"], "Product": ["Core"]}',
                         encoding="utf-8")
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    session = session_factory(engine)()
    seed_rules_from_canonical(session, str(canonical))
    seed_rules_from_canonical(session, str(canonical))  # idempotent
    assert session.query(RuleRow).count() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_rules_engine.py -v` → FAIL, module not found.

- [ ] **Step 3: Write minimal implementation**

`tagmanager/rules/__init__.py`: docstring preamble. `tagmanager/rules/engine.py`:

```python
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
    """A rule applies unless its cloud/type scoping says otherwise."""
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_rules_engine.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_rules_engine.py
git add tagmanager/rules/ tests/test_rules_engine.py
git commit -m "Add rules engine with cloud/type scoping and canonical seed"
```

---

### Task 5: AWS provider (Resource Groups Tagging API)

**Files:**
- Create: `tagmanager/providers/aws_provider.py`
- Test: `tests/test_aws_provider.py`

**Interfaces:**
- Consumes: `Provider`, `NormalizedResource`, `ScopeConfig`, `ProviderCapabilities` from Task 3.
- Produces: `AwsProvider(Provider)` with `cloud_name = "aws"`; `list_resources(scope)` — for each region in `scope.regions` (required for AWS), builds a session (assume-role when `scope.credentials["role_arn"]` present, default chain otherwise), pages `resourcegroupstaggingapi.get_resources`, yields NormalizedResource with `rtype` = service:type parsed from the ARN (e.g. `ec2:instance`), `name` = `Name` tag if present. `capabilities()` returns `supports_direct_write=True`.

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Unit tests for the AWS provider (stubbed Tagging API client).
Author(s): John Reed
"""

from unittest import mock

from tagmanager.providers.aws_provider import AwsProvider
from tagmanager.providers.base import ScopeConfig


def _page(arn, tags):
    return {"ResourceTagMappingList": [
        {"ResourceARN": arn, "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}]}


def test_list_resources_normalizes_arn_and_tags():
    client = mock.Mock()
    paginator = mock.Mock()
    paginator.paginate.return_value = iter([_page(
        "arn:aws:ec2:us-east-1:111122223333:instance/i-abc",
        {"Name": "web1", "Environment": "Prod"})])
    client.get_paginator.return_value = paginator
    session = mock.Mock()
    session.client.return_value = client

    provider = AwsProvider(session_builder=lambda scope, region: session)
    scope = ScopeConfig(cloud="aws", scope_id="111122223333",
                        credentials={}, regions=["us-east-1"])
    resources = list(provider.list_resources(scope))

    assert len(resources) == 1
    res = resources[0]
    assert res.rtype == "ec2:instance"
    assert res.resource_id == "arn:aws:ec2:us-east-1:111122223333:instance/i-abc"
    assert res.name == "web1"
    assert res.tags["Environment"] == "Prod"
    assert res.region == "us-east-1"


def test_capabilities_direct_write():
    provider = AwsProvider(session_builder=lambda scope, region: mock.Mock())
    assert provider.capabilities().supports_direct_write is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_aws_provider.py -v` → FAIL, module not found.

- [ ] **Step 3: Write minimal implementation**

```python
"""
Purpose: AWS provider — bulk inventory via the Resource Groups Tagging API,
assume-role per account, ARN-derived resource types.
Author(s): John Reed
"""

import logging

import boto3

from tagmanager.providers.base import NormalizedResource, Provider, ProviderCapabilities

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.aws_provider")
LOG.setLevel(logging.INFO)


def _default_session_builder(scope, region):
    """Assume the scope's role when configured; default chain otherwise."""
    role_arn = scope.credentials.get("role_arn")
    if not role_arn:
        return boto3.Session(region_name=region)
    sts = boto3.client("sts")
    creds = sts.assume_role(RoleArn=role_arn, RoleSessionName="tagmanager")["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region,
    )


def _rtype_from_arn(arn):
    """arn:aws:ec2:region:acct:instance/i-abc -> ec2:instance."""
    parts = arn.split(":", 5)
    service = parts[2] if len(parts) > 2 else "unknown"
    rest = parts[5] if len(parts) > 5 else ""
    kind = rest.split("/", 1)[0].split(":", 1)[0] or "resource"
    return f"{service}:{kind}"


class AwsProvider(Provider):
    """Reads every taggable resource in an account via the Tagging API."""

    cloud_name = "aws"

    def __init__(self, session_builder=_default_session_builder):
        """
        :param session_builder: callable(scope, region) -> boto3.Session
        """
        self._session_builder = session_builder

    def list_resources(self, scope):
        """
        Yield NormalizedResource for every tagged/taggable resource.

        :param scope: ScopeConfig with regions list set
        :yields: NormalizedResource
        """
        for region in scope.regions or []:
            LOG.info("scanning aws %s %s...", scope.scope_id, region)
            session = self._session_builder(scope, region)
            client = session.client("resourcegroupstaggingapi")
            paginator = client.get_paginator("get_resources")
            for page in paginator.paginate():
                for item in page.get("ResourceTagMappingList", []):
                    arn = item["ResourceARN"]
                    tags = {t["Key"]: t["Value"] for t in item.get("Tags", [])}
                    yield NormalizedResource(
                        cloud="aws", scope_id=scope.scope_id, region=region,
                        rtype=_rtype_from_arn(arn), resource_id=arn,
                        name=tags.get("Name", ""), tags=tags)

    def capabilities(self):
        """AWS supports direct tag writes (TagResources) come sub-project 2."""
        return ProviderCapabilities(supports_direct_write=True)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_aws_provider.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_aws_provider.py
git add tagmanager/providers/aws_provider.py tests/test_aws_provider.py
git commit -m "Add AWS provider over the Resource Groups Tagging API"
```

---

### Task 6: Azure provider (Resource Graph)

**Files:**
- Create: `tagmanager/providers/azure_provider.py`
- Modify: `pyproject.toml` (add `"azure-identity>=1.16"`, `"azure-mgmt-resourcegraph>=8.0"`)
- Test: `tests/test_azure_provider.py`

**Interfaces:**
- Consumes: Task 3 base classes.
- Produces: `AzureProvider(Provider)`, `cloud_name = "azure"`; `list_resources(scope)` runs Resource Graph query `Resources | project id, name, type, location, tags, subscriptionId` against `scope.scope_id` (subscription id), pages via `skip_token`, yields NormalizedResource (`region` = location, `rtype` = Azure type e.g. `microsoft.compute/virtualmachines`, `tags` = tags map or `{}`). Client injected via `client_builder(scope)` for tests. `capabilities()` → `supports_direct_write=True`.

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Unit tests for the Azure provider (stubbed Resource Graph client).
Author(s): John Reed
"""

from unittest import mock

from tagmanager.providers.azure_provider import AzureProvider
from tagmanager.providers.base import ScopeConfig


def _response(rows, skip_token=None):
    resp = mock.Mock()
    resp.data = rows
    resp.skip_token = skip_token
    return resp


def test_list_resources_pages_and_normalizes():
    client = mock.Mock()
    client.resources.side_effect = [
        _response([{"id": "/subscriptions/s1/rg/vm1", "name": "vm1",
                    "type": "microsoft.compute/virtualmachines",
                    "location": "eastus", "tags": {"Environment": "Prod"},
                    "subscriptionId": "s1"}], skip_token="next"),
        _response([{"id": "/subscriptions/s1/rg/sa1", "name": "sa1",
                    "type": "microsoft.storage/storageaccounts",
                    "location": "eastus", "tags": None, "subscriptionId": "s1"}]),
    ]
    provider = AzureProvider(client_builder=lambda scope: client)
    scope = ScopeConfig(cloud="azure", scope_id="s1", credentials={})

    resources = list(provider.list_resources(scope))

    assert len(resources) == 2
    assert resources[0].rtype == "microsoft.compute/virtualmachines"
    assert resources[0].tags == {"Environment": "Prod"}
    assert resources[1].tags == {}
    assert client.resources.call_count == 2


def test_capabilities_direct_write():
    provider = AzureProvider(client_builder=lambda scope: mock.Mock())
    assert provider.capabilities().supports_direct_write is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_azure_provider.py -v` → FAIL, module not found.

- [ ] **Step 3: Write minimal implementation**

Add the two Azure deps to `pyproject.toml`, `pip install -e ".[dev]"`, then `tagmanager/providers/azure_provider.py`:

```python
"""
Purpose: Azure provider — bulk inventory via one Resource Graph query per
subscription, service-principal credentials from the environment.
Author(s): John Reed
"""

import logging

from tagmanager.providers.base import NormalizedResource, Provider, ProviderCapabilities

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.azure_provider")
LOG.setLevel(logging.INFO)

QUERY = "Resources | project id, name, type, location, tags, subscriptionId"


def _default_client_builder(scope):
    """Resource Graph client using DefaultAzureCredential (env-driven SP)."""
    # imported lazily so tests never need the Azure SDK wired
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.resourcegraph import ResourceGraphClient
    return ResourceGraphClient(DefaultAzureCredential())


class AzureProvider(Provider):
    """Reads every resource + tags in a subscription via Resource Graph."""

    cloud_name = "azure"

    def __init__(self, client_builder=_default_client_builder):
        """
        :param client_builder: callable(scope) -> ResourceGraphClient
        """
        self._client_builder = client_builder

    def list_resources(self, scope):
        """
        Yield NormalizedResource for every resource in the subscription.

        :param scope: ScopeConfig (scope_id = subscription id)
        :yields: NormalizedResource
        """
        from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
        client = self._client_builder(scope)
        LOG.info("scanning azure subscription %s...", scope.scope_id)
        skip_token = None
        while True:
            request = QueryRequest(
                subscriptions=[scope.scope_id], query=QUERY,
                options=QueryRequestOptions(skip_token=skip_token))
            response = client.resources(request)
            for row in response.data:
                yield NormalizedResource(
                    cloud="azure", scope_id=scope.scope_id,
                    region=row.get("location", ""), rtype=row.get("type", ""),
                    resource_id=row.get("id", ""), name=row.get("name", ""),
                    tags=row.get("tags") or {})
            skip_token = getattr(response, "skip_token", None)
            if not skip_token:
                break

    def capabilities(self):
        """Azure supports direct tag writes (Tags API) come sub-project 2."""
        return ProviderCapabilities(supports_direct_write=True)
```

Note for the test: the stub client bypasses `QueryRequest` construction only at the client boundary — the models import stays inside `list_resources`, so patch `azure.mgmt.resourcegraph.models` is NOT needed; install the SDK as a real dependency and the import just works.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_azure_provider.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_azure_provider.py
git add tagmanager/providers/azure_provider.py tests/test_azure_provider.py pyproject.toml
git commit -m "Add Azure provider over Resource Graph"
```

---

### Task 7: GCP provider (Cloud Asset Inventory)

**Files:**
- Create: `tagmanager/providers/gcp_provider.py`
- Modify: `pyproject.toml` (add `"google-cloud-asset>=3.24"`)
- Test: `tests/test_gcp_provider.py`

**Interfaces:**
- Consumes: Task 3 base classes.
- Produces: `GcpProvider(Provider)`, `cloud_name = "gcp"`; `list_resources(scope)` calls `client.list_assets(request={"parent": f"projects/{scope.scope_id}", "content_type": "RESOURCE"})`, yields NormalizedResource with `tags` = GCP labels (`asset.resource.data.get("labels", {})`), `rtype` = `asset.asset_type` (e.g. `compute.googleapis.com/Instance`), `region` parsed from resource location field or `"global"`. Client injected via `client_builder(scope)`. `capabilities()` → `supports_direct_write=False` (read-only until the sub-project 2 shim).

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Unit tests for the GCP provider (stubbed Asset Inventory client).
Author(s): John Reed
"""

from unittest import mock

from tagmanager.providers.gcp_provider import GcpProvider
from tagmanager.providers.base import ScopeConfig


def _asset(name, asset_type, labels, location="us-central1"):
    asset = mock.Mock()
    asset.name = name
    asset.asset_type = asset_type
    asset.resource.data = {"labels": labels, "name": name.rsplit("/", 1)[-1]}
    asset.resource.location = location
    return asset


def test_list_resources_normalizes_labels_to_tags():
    client = mock.Mock()
    client.list_assets.return_value = iter([
        _asset("//compute.googleapis.com/projects/p1/zones/z/instances/web1",
               "compute.googleapis.com/Instance", {"environment": "prod"})])
    provider = GcpProvider(client_builder=lambda scope: client)
    scope = ScopeConfig(cloud="gcp", scope_id="p1", credentials={})

    resources = list(provider.list_resources(scope))

    assert len(resources) == 1
    res = resources[0]
    assert res.tags == {"environment": "prod"}
    assert res.rtype == "compute.googleapis.com/Instance"
    assert res.region == "us-central1"
    kwargs = client.list_assets.call_args.kwargs
    assert kwargs["request"]["parent"] == "projects/p1"


def test_capabilities_read_only():
    provider = GcpProvider(client_builder=lambda scope: mock.Mock())
    assert provider.capabilities().supports_direct_write is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_gcp_provider.py -v` → FAIL, module not found.

- [ ] **Step 3: Write minimal implementation**

Add `google-cloud-asset` dep, install, then `tagmanager/providers/gcp_provider.py`:

```python
"""
Purpose: GCP provider — bulk inventory via Cloud Asset Inventory; labels
normalize to tags. Read-only in sub-project 1 (write shim lands in SP2).
Author(s): John Reed
"""

import logging

from tagmanager.providers.base import NormalizedResource, Provider, ProviderCapabilities

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.gcp_provider")
LOG.setLevel(logging.INFO)


def _default_client_builder(scope):
    """Asset client using application-default credentials."""
    from google.cloud import asset_v1
    return asset_v1.AssetServiceClient()


class GcpProvider(Provider):
    """Reads every asset + labels in a project via Cloud Asset Inventory."""

    cloud_name = "gcp"

    def __init__(self, client_builder=_default_client_builder):
        """
        :param client_builder: callable(scope) -> AssetServiceClient
        """
        self._client_builder = client_builder

    def list_resources(self, scope):
        """
        Yield NormalizedResource for every asset in the project.

        :param scope: ScopeConfig (scope_id = project id)
        :yields: NormalizedResource
        """
        client = self._client_builder(scope)
        LOG.info("scanning gcp project %s...", scope.scope_id)
        assets = client.list_assets(request={
            "parent": f"projects/{scope.scope_id}",
            "content_type": "RESOURCE",
        })
        for asset in assets:
            data = asset.resource.data or {}
            yield NormalizedResource(
                cloud="gcp", scope_id=scope.scope_id,
                region=getattr(asset.resource, "location", "") or "global",
                rtype=asset.asset_type, resource_id=asset.name,
                name=data.get("name", ""), tags=dict(data.get("labels", {})))

    def capabilities(self):
        """GCP label writes are per-service — read-only until the SP2 shim."""
        return ProviderCapabilities(supports_direct_write=False)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_gcp_provider.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_gcp_provider.py
git add tagmanager/providers/gcp_provider.py tests/test_gcp_provider.py pyproject.toml
git commit -m "Add GCP provider over Cloud Asset Inventory (read-only)"
```

---

### Task 8: Scanner service

**Files:**
- Create: `tagmanager/scanner.py`
- Test: `tests/test_scanner.py`

**Interfaces:**
- Consumes: models (Task 2), `Provider`/`ScopeConfig` (Task 3), `evaluate_resource` (Task 4).
- Produces: `run_scan(session, providers, scopes) -> ScanRun` where `providers` is `dict[str, Provider]` keyed by cloud name and `scopes` is `list[ScopeConfig]`. Behavior: creates a ScanRun; per scope, iterates the matching provider's `list_resources`, upserts Resource rows (match on cloud+resource_id), evaluates rules (loaded once from RuleRow), writes Violations; a provider exception for a scope appends `{"scope_id", "error"}` to `run.skips` and continues; final `status` = `"complete"` if no skips else `"partial"`; fills `resources_seen`, `violation_count`, `finished_at`.

- [ ] **Step 1: Write the failing test**

```python
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
    cloud_name = "stub"

    def __init__(self, resources_by_scope):
        self._by_scope = resources_by_scope

    def list_resources(self, scope):
        value = self._by_scope[scope.scope_id]
        if isinstance(value, Exception):
            raise value
        yield from value

    def capabilities(self):
        return ProviderCapabilities(supports_direct_write=False)


def _res(rid, tags):
    return NormalizedResource(cloud="stub", scope_id="s1", region="r", rtype="t",
                              resource_id=rid, name=rid, tags=tags)


def _session():
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    session = session_factory(engine)()
    session.add(RuleRow(key="Environment", allowed_values=["Prod"]))
    session.commit()
    return session


def test_scan_upserts_and_finds_violations():
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
    session = _session()
    scope = ScopeConfig(cloud="stub", scope_id="s1", credentials={})
    run_scan(session, {"stub": _StubProvider({"s1": [_res("a", {})]})}, [scope])
    run_scan(session, {"stub": _StubProvider(
        {"s1": [_res("a", {"Environment": "Prod"})]})}, [scope])
    assert session.query(Resource).count() == 1
    assert session.query(Resource).one().tags == {"Environment": "Prod"}


def test_scope_failure_isolated_as_skip():
    session = _session()
    provider = _StubProvider({"bad": RuntimeError("denied"),
                              "good": [_res("a", {"Environment": "Prod"})]})
    scopes = [ScopeConfig(cloud="stub", scope_id="bad", credentials={}),
              ScopeConfig(cloud="stub", scope_id="good", credentials={})]

    run = run_scan(session, {"stub": provider}, scopes)

    assert run.status == "partial"
    assert run.skips == [{"scope_id": "bad", "error": "denied"}]
    assert run.resources_seen == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_scanner.py -v` → FAIL, module not found.

- [ ] **Step 3: Write minimal implementation**

```python
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
    """Insert or update the Resource row for one normalized resource."""
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
        except Exception as err:  # scope isolation is the contract
            LOG.warning("skipping scope %s (%s)...", scope.scope_id, err)
            skips.append({"scope_id": scope.scope_id, "error": str(err)})

    run.resources_seen = seen
    run.violation_count = violations
    run.skips = skips
    run.status = "partial" if skips else "complete"
    run.finished_at = datetime.datetime.utcnow()
    session.commit()
    LOG.info("scan complete... %s resource(s), %s violation(s), %s skip(s)",
             seen, violations, len(skips))
    return run
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_scanner.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_scanner.py
git add tagmanager/scanner.py tests/test_scanner.py
git commit -m "Add scanner service with upsert and scope-skip isolation"
```

---

### Task 9: API — health, resources, violations, scans

**Files:**
- Create: `tagmanager/app/__init__.py`, `tagmanager/app/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: models (Task 2), Settings (Task 1).
- Produces: `create_app(settings, session_maker) -> FastAPI` with routes: `GET /api/health` → `{"status": "ok"}`; `GET /api/resources?cloud=&scope_id=&rtype=&tag_key=&tag_value=` → JSON list of resource dicts (id, cloud, scope_id, region, rtype, resource_id, name, tags); `GET /api/violations?cloud=&rule_key=` → list of {resource_id, name, cloud, rule_key, value, issue, scan_run_id}; `GET /api/scans` → list of scan runs newest-first (id, started_at ISO, status, resources_seen, violation_count, skips). Session per request via dependency. Auth enforcement arrives in Task 10 — routes are open when `auth_mode == "none"`.

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: API tests via FastAPI TestClient over an in-memory catalog.
Author(s): John Reed
"""

from fastapi.testclient import TestClient

from tagmanager.app.main import create_app
from tagmanager.config import Settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import Resource, ScanRun, Violation


def _client():
    engine = get_engine("sqlite:///:memory:")
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
    assert _client().get("/api/health").json() == {"status": "ok"}


def test_resources_filter_by_cloud():
    client = _client()
    assert len(client.get("/api/resources?cloud=aws").json()) == 1
    assert client.get("/api/resources?cloud=azure").json() == []


def test_resources_filter_by_tag():
    client = _client()
    hits = client.get("/api/resources?tag_key=Environment&tag_value=nope").json()
    assert len(hits) == 1 and hits[0]["name"] == "web1"


def test_violations_and_scans():
    client = _client()
    violations = client.get("/api/violations").json()
    assert violations[0]["rule_key"] == "Environment"
    scans = client.get("/api/scans").json()
    assert scans[0]["status"] == "complete"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_api.py -v` → FAIL, module not found.

- [ ] **Step 3: Write minimal implementation**

`tagmanager/app/__init__.py`: docstring preamble. `tagmanager/app/main.py`:

```python
"""
Purpose: FastAPI application — JSON API for the catalog plus (Task 11) the
server-rendered UI. App factory keeps settings and DB injectable for tests.
Author(s): John Reed
"""

import logging

from fastapi import Depends, FastAPI

from tagmanager.models.tables import Resource, ScanRun, Violation

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.app")
LOG.setLevel(logging.INFO)


def create_app(settings, session_maker):
    """
    Build the FastAPI app.

    :param settings: Settings
    :param session_maker: sessionmaker bound to the catalog DB
    :returns: FastAPI app
    """
    app = FastAPI(title="TagManager")

    def db():
        session = session_maker()
        try:
            yield session
        finally:
            session.close()

    @app.get("/api/health")
    def health():
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/api/resources")
    def resources(cloud: str = "", scope_id: str = "", rtype: str = "",
                  tag_key: str = "", tag_value: str = "",
                  session=Depends(db)):
        """Filtered catalog listing."""
        query = session.query(Resource)
        if cloud:
            query = query.filter(Resource.cloud == cloud)
        if scope_id:
            query = query.filter(Resource.scope_id == scope_id)
        if rtype:
            query = query.filter(Resource.rtype == rtype)
        rows = query.all()
        if tag_key:
            rows = [r for r in rows if tag_key in r.tags and
                    (not tag_value or r.tags.get(tag_key) == tag_value)]
        return [{"id": r.id, "cloud": r.cloud, "scope_id": r.scope_id,
                 "region": r.region, "rtype": r.rtype,
                 "resource_id": r.resource_id, "name": r.name, "tags": r.tags}
                for r in rows]

    @app.get("/api/violations")
    def violations(cloud: str = "", rule_key: str = "", session=Depends(db)):
        """Violation listing joined to resources."""
        query = (session.query(Violation, Resource)
                 .join(Resource, Violation.resource_pk == Resource.id))
        if cloud:
            query = query.filter(Resource.cloud == cloud)
        if rule_key:
            query = query.filter(Violation.rule_key == rule_key)
        return [{"resource_id": res.resource_id, "name": res.name,
                 "cloud": res.cloud, "rule_key": v.rule_key, "value": v.value,
                 "issue": v.issue, "scan_run_id": v.scan_run_id}
                for v, res in query.all()]

    @app.get("/api/scans")
    def scans(session=Depends(db)):
        """Scan-run history, newest first."""
        rows = session.query(ScanRun).order_by(ScanRun.id.desc()).all()
        return [{"id": r.id, "started_at": r.started_at.isoformat(),
                 "status": r.status, "resources_seen": r.resources_seen,
                 "violation_count": r.violation_count, "skips": r.skips}
                for r in rows]

    app.state.settings = settings
    return app
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_api.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_api.py
git add tagmanager/app/ tests/test_api.py
git commit -m "Add catalog JSON API: health, resources, violations, scans"
```

---

### Task 10: OIDC auth with dev bypass

**Files:**
- Create: `tagmanager/app/auth.py`
- Modify: `tagmanager/app/main.py` (wire middleware + login routes)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: Settings (Task 1), `create_app` (Task 9).
- Produces: `tagmanager/app/auth.py` exposing `install_auth(app, settings)`. Behavior: `auth_mode == "none"` → no-op (dev/test). `auth_mode == "oidc"` → authlib OAuth client registered from `oidc_issuer`/`oidc_client_id`/`oidc_client_secret` (server metadata URL `{issuer}/.well-known/openid-configuration`); routes `GET /login` (redirect to IdP), `GET /auth/callback` (token → `request.session["user"] = {"email", "name"}`), `GET /logout`; HTTP middleware rejecting unauthenticated requests to `/api/*` and `/` with 401 (except `/api/health`, `/login`, `/auth/callback`). Starlette SessionMiddleware with secret from `TAGMANAGER_SESSION_SECRET` env (default random per boot). `create_app` calls `install_auth(app, settings)` last so the middleware wraps all routes.

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Auth tests — dev bypass leaves API open; oidc mode gates routes.
Author(s): John Reed
"""

from fastapi.testclient import TestClient

from tagmanager.app.main import create_app
from tagmanager.config import Settings
from tagmanager.models.base import create_all, get_engine, session_factory


def _client(auth_mode):
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    settings = Settings(auth_mode=auth_mode, oidc_issuer="https://idp.example",
                        oidc_client_id="cid", oidc_client_secret="secret")
    return TestClient(create_app(settings, session_factory(engine)))


def test_none_mode_leaves_api_open():
    assert _client("none").get("/api/resources").status_code == 200


def test_oidc_mode_rejects_anonymous_api():
    assert _client("oidc").get("/api/resources").status_code == 401


def test_oidc_mode_health_stays_open():
    assert _client("oidc").get("/api/health").status_code == 200


def test_oidc_mode_login_redirects_to_idp():
    response = _client("oidc").get("/login", follow_redirects=False)
    assert response.status_code in (302, 307)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v` → FAIL (`test_oidc_mode_rejects_anonymous_api` gets 200 — no gate exists; `/login` 404).

- [ ] **Step 3: Write minimal implementation**

`tagmanager/app/auth.py`:

```python
"""
Purpose: OIDC login for the TagManager UI/API with a dev bypass mode.
Author(s): John Reed
"""

import logging
import os
import secrets

from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.auth")
LOG.setLevel(logging.INFO)

OPEN_PATHS = ("/api/health", "/login", "/auth/callback")


def install_auth(app, settings):
    """
    Wire session + OIDC auth onto the app; no-op when auth_mode is none.

    :param app: FastAPI app
    :param settings: Settings
    """
    if settings.auth_mode != "oidc":
        LOG.info("auth mode none — running open (dev only)...")
        return

    app.add_middleware(SessionMiddleware, secret_key=os.environ.get(
        "TAGMANAGER_SESSION_SECRET", secrets.token_hex(32)))

    oauth = OAuth()
    oauth.register(
        name="idp",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=(
            f"{settings.oidc_issuer}/.well-known/openid-configuration"),
        client_kwargs={"scope": "openid email profile"},
    )

    @app.get("/login")
    async def login(request: Request):
        """Send the user to the IdP."""
        redirect_uri = request.url_for("auth_callback")
        return await oauth.idp.authorize_redirect(request, redirect_uri)

    @app.get("/auth/callback")
    async def auth_callback(request: Request):
        """Complete the code flow, stash the user in the session."""
        token = await oauth.idp.authorize_access_token(request)
        info = token.get("userinfo") or {}
        request.session["user"] = {"email": info.get("email", ""),
                                   "name": info.get("name", "")}
        LOG.info("login ok... %s", info.get("email", "?"))
        return RedirectResponse(url="/")

    @app.get("/logout")
    async def logout(request: Request):
        """Drop the session."""
        request.session.clear()
        return RedirectResponse(url="/login")

    @app.middleware("http")
    async def require_user(request: Request, call_next):
        """401 for anything but the open paths when not logged in."""
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        if not request.session.get("user"):
            return JSONResponse({"title": "unauthorized", "status": 401},
                                status_code=401)
        return await call_next(request)
```

In `create_app` (Task 9's `main.py`), after all routes are registered and before `return app`, add:

```python
    from tagmanager.app.auth import install_auth
    install_auth(app, settings)
```

(Import at module top in the real edit; shown inline here for placement clarity.)

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_auth.py tests/test_api.py -v` → PASS (api tests still green under none mode); full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_auth.py
git add tagmanager/app/auth.py tagmanager/app/main.py tests/test_auth.py
git commit -m "Add OIDC auth with dev bypass and session middleware"
```

---

### Task 11: Read-only web UI (Jinja2 + htmx)

**Files:**
- Create: `tagmanager/app/templates/base.html`, `tagmanager/app/templates/dashboard.html`, `tagmanager/app/templates/resources.html`, `tagmanager/app/templates/violations.html`, `tagmanager/app/ui.py`
- Modify: `tagmanager/app/main.py` (mount UI router + Jinja2Templates)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `create_app` internals (Task 9), models (Task 2).
- Produces: routes `GET /` (dashboard: latest scan status, compliance % = 1 − violating resources/seen, counts by cloud), `GET /resources` (filter form GET params cloud/rtype/tag_key, table), `GET /violations` (table, filter by cloud). htmx loaded from a vendored static file `tagmanager/app/static/htmx.min.js` (self-contained container — no CDN). `ui_router(templates, session_maker) -> APIRouter`.

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: UI smoke tests — pages render with catalog data present.
Author(s): John Reed
"""

from fastapi.testclient import TestClient

from tagmanager.app.main import create_app
from tagmanager.config import Settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import Resource, ScanRun, Violation


def _client():
    engine = get_engine("sqlite:///:memory:")
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
    body = _client().get("/").text
    assert "TagManager" in body
    assert "partial" in body


def test_resources_page_lists_and_filters():
    client = _client()
    assert "web1" in client.get("/resources").text
    assert "web1" not in client.get("/resources?cloud=aws").text


def test_violations_page_lists_findings():
    body = _client().get("/violations").text
    assert "owner" in body and "missing" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ui.py -v` → FAIL — `GET /` 404.

- [ ] **Step 3: Write minimal implementation**

Download htmx once: `curl -sSLo tagmanager/app/static/htmx.min.js https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js` (vendored, committed).

`tagmanager/app/templates/base.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>TagManager</title>
  <script src="/static/htmx.min.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; }
    table { border-collapse: collapse; }
    td, th { border: 1px solid #999; padding: 4px 8px; }
    nav a { margin-right: 1rem; }
  </style>
</head>
<body>
  <h1>TagManager</h1>
  <nav>
    <a href="/">Dashboard</a>
    <a href="/resources">Resources</a>
    <a href="/violations">Violations</a>
  </nav>
  <hr>
  {% block content %}{% endblock %}
</body>
</html>
```

`dashboard.html`:

```html
{% extends "base.html" %}
{% block content %}
<h2>Latest scan</h2>
{% if run %}
<p>Status: <strong>{{ run.status }}</strong> —
   {{ run.resources_seen }} resource(s), {{ run.violation_count }} violation(s),
   {{ run.skips | length }} skip(s)</p>
<p>Compliance: {{ compliance_pct }}%</p>
{% else %}<p>No scans yet.</p>{% endif %}
<h2>Resources by cloud</h2>
<table>
  <tr><th>Cloud</th><th>Count</th></tr>
  {% for cloud, count in by_cloud %}
  <tr><td>{{ cloud }}</td><td>{{ count }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
```

`resources.html`:

```html
{% extends "base.html" %}
{% block content %}
<form method="get">
  <input name="cloud" placeholder="cloud" value="{{ cloud }}">
  <input name="rtype" placeholder="type" value="{{ rtype }}">
  <button>Filter</button>
</form>
<table>
  <tr><th>Cloud</th><th>Scope</th><th>Region</th><th>Type</th><th>Name</th><th>Tags</th></tr>
  {% for r in rows %}
  <tr><td>{{ r.cloud }}</td><td>{{ r.scope_id }}</td><td>{{ r.region }}</td>
      <td>{{ r.rtype }}</td><td>{{ r.name }}</td><td>{{ r.tags }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
```

`violations.html`:

```html
{% extends "base.html" %}
{% block content %}
<table>
  <tr><th>Cloud</th><th>Resource</th><th>Rule</th><th>Value</th><th>Issue</th></tr>
  {% for v, res in rows %}
  <tr><td>{{ res.cloud }}</td><td>{{ res.name }}</td>
      <td>{{ v.rule_key }}</td><td>{{ v.value }}</td><td>{{ v.issue }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
```

`tagmanager/app/ui.py`:

```python
"""
Purpose: Server-rendered read-only UI — dashboard, resource browser,
violation list.
Author(s): John Reed
"""

from fastapi import APIRouter, Request
from sqlalchemy import func

from tagmanager.models.tables import Resource, ScanRun, Violation


def ui_router(templates, session_maker):
    """
    Build the UI router.

    :param templates: Jinja2Templates
    :param session_maker: sessionmaker
    :returns: APIRouter
    """
    router = APIRouter()

    @router.get("/")
    def dashboard(request: Request):
        """Latest scan status + per-cloud counts."""
        session = session_maker()
        try:
            run = session.query(ScanRun).order_by(ScanRun.id.desc()).first()
            by_cloud = (session.query(Resource.cloud, func.count(Resource.id))
                        .group_by(Resource.cloud).all())
            violating = (session.query(func.count(func.distinct(
                Violation.resource_pk))).scalar() or 0)
            compliance = 100
            if run and run.resources_seen:
                compliance = round(100 * (1 - violating / run.resources_seen))
            return templates.TemplateResponse(request, "dashboard.html", {
                "run": run, "by_cloud": by_cloud, "compliance_pct": compliance})
        finally:
            session.close()

    @router.get("/resources")
    def resources(request: Request, cloud: str = "", rtype: str = ""):
        """Filterable resource table."""
        session = session_maker()
        try:
            query = session.query(Resource)
            if cloud:
                query = query.filter(Resource.cloud == cloud)
            if rtype:
                query = query.filter(Resource.rtype == rtype)
            return templates.TemplateResponse(request, "resources.html", {
                "rows": query.all(), "cloud": cloud, "rtype": rtype})
        finally:
            session.close()

    @router.get("/violations")
    def violations(request: Request):
        """All findings joined to their resources."""
        session = session_maker()
        try:
            rows = (session.query(Violation, Resource)
                    .join(Resource, Violation.resource_pk == Resource.id).all())
            return templates.TemplateResponse(request, "violations.html",
                                              {"rows": rows})
        finally:
            session.close()

    return router
```

In `main.py` `create_app`, before `install_auth`:

```python
    templates = Jinja2Templates(
        directory=str(pathlib.Path(__file__).parent / "templates"))
    app.mount("/static", StaticFiles(
        directory=str(pathlib.Path(__file__).parent / "static")), name="static")
    app.include_router(ui_router(templates, session_maker))
```

(with `import pathlib`, `from fastapi.staticfiles import StaticFiles`, `from fastapi.templating import Jinja2Templates`, `from tagmanager.app.ui import ui_router` at top).

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_ui.py tests/test_api.py tests/test_auth.py -v` → PASS; full suite green.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_ui.py
git add tagmanager/app/ tests/test_ui.py
git commit -m "Add read-only web UI: dashboard, resources, violations"
```

---

### Task 12: Scheduler + app entrypoint

**Files:**
- Create: `tagmanager/scheduler.py`, `tagmanager/serve.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `run_scan` (Task 8), Settings (Task 1), models (Task 2), providers (Tasks 5–7).
- Produces: `tagmanager/scheduler.py`: `build_scheduler(settings, session_maker, providers, scopes_loader) -> BackgroundScheduler` — one interval job every `settings.scan_interval_minutes` calling `_scan_job`; `_scan_job(session_maker, providers, scopes_loader)` skips (log + return) when a ScanRun with status `"running"` exists (overlap guard), else runs `run_scan` with a fresh session; `scopes_loader()` returns `list[ScopeConfig]` built from enabled Scope rows (credentials refs resolved from env). `tagmanager/serve.py`: `main()` — builds engine from settings, `create_all`, seeds rules from `canonical.json` when present, builds app + scheduler, starts uvicorn on port 8080 (entry point `tagmanager-serve = "tagmanager.serve:main"` added to pyproject).

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Scheduler tests — job wiring and the running-scan overlap guard.
Author(s): John Reed
"""

from unittest import mock

from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import ScanRun
from tagmanager.scheduler import _scan_job, build_scheduler


def _maker():
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    return session_factory(engine)


def test_build_scheduler_registers_interval_job():
    settings = mock.Mock(scan_interval_minutes=15)
    scheduler = build_scheduler(settings, _maker(), {}, list)
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].trigger.interval.total_seconds() == 15 * 60


def test_scan_job_runs_when_idle():
    maker = _maker()
    with mock.patch("tagmanager.scheduler.run_scan") as run_scan:
        _scan_job(maker, {}, list)
    run_scan.assert_called_once()


def test_scan_job_skips_when_scan_running():
    maker = _maker()
    session = maker()
    session.add(ScanRun(status="running", skips=[]))
    session.commit()
    with mock.patch("tagmanager.scheduler.run_scan") as run_scan:
        _scan_job(maker, {}, list)
    run_scan.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_scheduler.py -v` → FAIL, module not found.

- [ ] **Step 3: Write minimal implementation**

`tagmanager/scheduler.py`:

```python
"""
Purpose: In-process scan scheduling with a single-run overlap guard.
Single app replica assumed in sub-project 1 (see design spec).
Author(s): John Reed
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from tagmanager.models.tables import ScanRun
from tagmanager.scanner import run_scan

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.scheduler")
LOG.setLevel(logging.INFO)


def _scan_job(session_maker, providers, scopes_loader):
    """Run one scan unless one is already running."""
    session = session_maker()
    try:
        running = session.query(ScanRun).filter_by(status="running").count()
        if running:
            LOG.info("scan already running — skipping this tick...")
            return
        run_scan(session, providers, scopes_loader())
    finally:
        session.close()


def build_scheduler(settings, session_maker, providers, scopes_loader):
    """
    Background scheduler with the periodic scan job registered.

    :param settings: Settings
    :param session_maker: sessionmaker
    :param providers: dict of cloud name -> Provider
    :param scopes_loader: callable returning list[ScopeConfig]
    :returns: BackgroundScheduler (not started)
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(_scan_job, "interval",
                      minutes=settings.scan_interval_minutes,
                      args=[session_maker, providers, scopes_loader])
    return scheduler
```

`tagmanager/serve.py`:

```python
"""
Purpose: Container entrypoint — build DB, seed rules, start scheduler and
uvicorn in one process.
Author(s): John Reed
"""

import logging
import os

import uvicorn

from tagmanager.app.main import create_app
from tagmanager.config import get_settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.models.tables import Scope
from tagmanager.providers.aws_provider import AwsProvider
from tagmanager.providers.azure_provider import AzureProvider
from tagmanager.providers.base import ScopeConfig
from tagmanager.providers.gcp_provider import GcpProvider
from tagmanager.rules.engine import seed_rules_from_canonical
from tagmanager.scheduler import build_scheduler

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.serve")
LOG.setLevel(logging.INFO)


def _scopes_loader(session_maker):
    """Build ScopeConfigs from enabled Scope rows; creds come from env."""
    def load():
        session = session_maker()
        try:
            configs = []
            for row in session.query(Scope).filter_by(enabled=True).all():
                creds = {}
                role_env = f"TAGMANAGER_AWS_ROLE_{row.scope_id}"
                if row.cloud == "aws" and os.environ.get(role_env):
                    creds["role_arn"] = os.environ[role_env]
                configs.append(ScopeConfig(cloud=row.cloud, scope_id=row.scope_id,
                                           credentials=creds, regions=row.regions))
            return configs
        finally:
            session.close()
    return load


def main():
    """Boot TagManager: DB, rules seed, scheduler, web server."""
    settings = get_settings()
    LOG.info("starting tagmanager...")
    engine = get_engine(settings.db_url)
    create_all(engine)
    maker = session_factory(engine)

    if os.path.exists("canonical.json"):
        seed_rules_from_canonical(maker(), "canonical.json")

    providers = {"aws": AwsProvider(), "azure": AzureProvider(),
                 "gcp": GcpProvider()}
    scheduler = build_scheduler(settings, maker, providers,
                                _scopes_loader(maker))
    scheduler.start()

    app = create_app(settings, maker)
    LOG.info("tagmanager up... http://0.0.0.0:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
```

Add to `pyproject.toml` `[project.scripts]`: `tagmanager-serve = "tagmanager.serve:main"`, reinstall editable.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_scheduler.py -v` → PASS; full suite green. Smoke: `.venv/bin/tagmanager-serve` boots, `curl localhost:8080/api/health` → `{"status":"ok"}`, Ctrl-C.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_scheduler.py
git add tagmanager/scheduler.py tagmanager/serve.py tests/test_scheduler.py pyproject.toml
git commit -m "Add in-process scheduler with overlap guard and serve entrypoint"
```

---

### Task 13: Container + compose + CI

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- Modify: `.github/workflows/pytest.yml` (run on push/PR, not just dispatch), `README.txt` (platform run instructions), `static_analysis.sh` (add `tagmanager/` to TARGETS)
- Test: `tests/test_container_smoke.py` (build-free smoke: entrypoint importable, app factory boots against SQLite)

**Interfaces:**
- Consumes: everything prior.
- Produces: `docker build -t tagmanager .` → image running `tagmanager-serve` on 8080; compose file with the app + a postgres:16 service (`TAGMANAGER_DB_URL=postgresql+psycopg://tagmanager:tagmanager@db/tagmanager` — add `"psycopg[binary]>=3.1"` dep).

- [ ] **Step 1: Write the failing test**

```python
"""
Purpose: Smoke test — the serve entrypoint wiring boots against SQLite.
Author(s): John Reed
"""

from fastapi.testclient import TestClient

from tagmanager.app.main import create_app
from tagmanager.config import Settings
from tagmanager.models.base import create_all, get_engine, session_factory
from tagmanager.providers.aws_provider import AwsProvider
from tagmanager.providers.azure_provider import AzureProvider
from tagmanager.providers.gcp_provider import GcpProvider
from tagmanager.serve import _scopes_loader


def test_full_wiring_boots_and_serves():
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    maker = session_factory(engine)
    providers = {"aws": AwsProvider(), "azure": AzureProvider(),
                 "gcp": GcpProvider()}
    assert set(providers) == {"aws", "azure", "gcp"}
    assert _scopes_loader(maker)() == []
    client = TestClient(create_app(Settings(auth_mode="none"), maker))
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_container_smoke.py -v` → FAIL only if wiring above is broken; if it passes immediately, that is acceptable here — this task's deliverable is the container files, and this test pins the wiring the Dockerfile depends on. (Coverage-pinning exception, same as the S3 upload contract tests.)

- [ ] **Step 3: Write the container files**

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.txt ./
COPY tagmanager/ tagmanager/
COPY aws.py aws_tag_manager.py canonical.json ./
RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["tagmanager-serve"]
```

`.dockerignore`:

```
.venv
.git
__pycache__
*.egg-info
tests
docs
.cairn
```

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: tagmanager
      POSTGRES_PASSWORD: tagmanager
      POSTGRES_DB: tagmanager
  app:
    build: .
    ports: ["8080:8080"]
    environment:
      TAGMANAGER_DB_URL: postgresql+psycopg://tagmanager:tagmanager@db/tagmanager
    depends_on: [db]
```

Add `"psycopg[binary]>=3.1"` to dependencies. Update `.github/workflows/pytest.yml` `on:` block to:

```yaml
on:
  push:
    branches: [master]
  pull_request:
  workflow_dispatch: {}
```

Update `static_analysis.sh` `TARGETS="aws.py aws_tag_manager.py tagmanager"` and README.txt with a `## Platform (web UI)` section: `docker compose up` → http://localhost:8080, env var reference (`TAGMANAGER_DB_URL`, `TAGMANAGER_AUTH_MODE`, `TAGMANAGER_OIDC_*`, `TAGMANAGER_SCAN_INTERVAL_MINUTES`).

- [ ] **Step 4: Verify**

Run: `.venv/bin/python -m pytest tests/ -q` → all green. `docker build -t tagmanager .` succeeds; `docker compose up` then `curl localhost:8080/api/health` → ok (requires Docker locally; note result honestly if unavailable).

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m pylint tagmanager/ && .venv/bin/python -m pycodestyle tagmanager/ tests/test_container_smoke.py
git add Dockerfile docker-compose.yml .dockerignore .github/workflows/pytest.yml static_analysis.sh README.txt tests/test_container_smoke.py pyproject.toml
git commit -m "Add container build, compose stack, CI on push, platform docs"
```

---

## Self-Review Notes

- Spec coverage: architecture/layout (T1–T2, T9, T11–T13), provider interface + 3 clouds (T3, T5–T7), rules + canonical seed (T4), scanner + skip isolation (T8), scheduler + overlap guard (T12), OIDC + dev bypass (T10), read-only UI (T11), container/compose/CI (T13). Not in this plan by design: repo rename (release chore), managed-Postgres deploy guides (post-SP1 docs), Alembic migrations (create_all suffices until first schema change — revisit in SP2).
- Type consistency: `NormalizedResource(cloud, scope_id, region, rtype, resource_id, name, tags)` used identically in T3/T5/T6/T7/T8; `session_factory` returns sessionmaker everywhere; `create_app(settings, session_maker)` consistent in T9/T10/T11/T13.
- The CLI (`aws_tag_manager.py`) is untouched by every task; its 32 tests plus these new ones must all pass at every commit.
