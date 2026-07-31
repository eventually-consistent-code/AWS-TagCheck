"""
Purpose: TagManager tables — resources, scan runs, violations, rules, scopes.
Author(s): John Reed
"""

import datetime

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, ForeignKey,
                        Integer, String, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from tagmanager.models.base import Base


def _utc_now():
    """
    Return current UTC time with timezone awareness.

    :returns: timezone-aware datetime.datetime in UTC
    """
    return datetime.datetime.now(datetime.timezone.utc)


class Resource(Base):  # pylint: disable=too-few-public-methods
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


class ScanRun(Base):  # pylint: disable=too-few-public-methods
    """One scheduled or manual scan execution."""

    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_utc_now)
    finished_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    resources_seen: Mapped[int] = mapped_column(Integer, default=0)
    violation_count: Mapped[int] = mapped_column(Integer, default=0)
    skips: Mapped[list] = mapped_column(JSON, default=list)


class Violation(Base):  # pylint: disable=too-few-public-methods
    """One rule finding against one resource in one scan."""

    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    resource_pk: Mapped[int] = mapped_column(ForeignKey("resources.id"))
    rule_key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(512), default="")
    issue: Mapped[str] = mapped_column(String(32))


class RuleRow(Base):  # pylint: disable=too-few-public-methods
    """One required-tag rule (allowed values, optional cloud/type scoping)."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128))
    allowed_values: Mapped[list] = mapped_column(JSON, default=list)
    applies_cloud: Mapped[str] = mapped_column(String(16), nullable=True)
    applies_type: Mapped[str] = mapped_column(String(128), nullable=True)


class StorageScanRun(Base):  # pylint: disable=too-few-public-methods
    """One mass-storage inventory scan execution."""

    __tablename__ = "storage_scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_utc_now)
    finished_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    backend: Mapped[str] = mapped_column(String(16))
    objects_seen: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_seen: Mapped[int] = mapped_column(BigInteger, default=0)
    age_band_days: Mapped[list] = mapped_column(JSON, default=list)
    skips: Mapped[list] = mapped_column(JSON, default=list)


class StoragePrefixStat(Base):  # pylint: disable=too-few-public-methods
    """One aggregate cell: container + prefix + storage class + age band."""

    __tablename__ = "storage_prefix_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("storage_scan_runs.id"))
    backend: Mapped[str] = mapped_column(String(16))
    container: Mapped[str] = mapped_column(String(256))
    prefix: Mapped[str] = mapped_column(String(1024), default="")
    storage_class: Mapped[str] = mapped_column(String(64), default="STANDARD")
    age_band: Mapped[str] = mapped_column(String(32))
    object_count: Mapped[int] = mapped_column(BigInteger, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    oldest_last_modified: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=True)


class Scope(Base):  # pylint: disable=too-few-public-methods
    """One configured account / subscription / project to scan."""

    __tablename__ = "scopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cloud: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    regions: Mapped[list] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
