"""
Purpose: Persist storage rollups — write a RollupBuilder's aggregates as one
StorageScanRun plus its StoragePrefixStat rows. Latest-run scoping applies:
readers query the newest complete run, never mix runs.
Author(s): John Reed
"""

import datetime

from sqlalchemy import inspect

from tagmanager.models.tables import StoragePrefixStat, StorageScanRun


def _utc_now():
    """
    Return current UTC time with timezone awareness.

    :returns: timezone-aware datetime.datetime in UTC
    """
    return datetime.datetime.now(datetime.timezone.utc)


def persist_rollups(session, builder, backend, skips=None):
    """
    Write one scan's aggregates and mark the run complete.

    :param session: SQLAlchemy session (caller owns commit/rollback)
    :param builder: RollupBuilder after the scan stream is exhausted
    :param backend: backend name string ("s3", ...)
    :param skips: optional list of per-container failure records
    :returns: the persisted StorageScanRun
    """
    run = StorageScanRun(
        backend=backend,
        objects_seen=builder.objects_seen,
        bytes_seen=builder.bytes_seen,
        age_band_days=list(builder.age_band_days),
        skips=list(skips or []),
    )
    session.add(run)
    session.flush()

    for (container, prefix, storage_class, band), stat in builder.rollups().items():
        session.add(StoragePrefixStat(
            scan_run_id=run.id,
            backend=backend,
            container=container,
            prefix=prefix,
            storage_class=storage_class,
            age_band=band,
            object_count=stat.object_count,
            total_bytes=stat.total_bytes,
            oldest_last_modified=stat.oldest_last_modified,
            small_object_count=stat.small_object_count,
            small_object_bytes=stat.small_object_bytes,
        ))

    run.status = "complete" if not skips else "partial"
    run.finished_at = _utc_now()
    session.flush()
    return run


def schema_current(engine):
    """
    Check the live DB carries the columns this code writes/reads.

    create_all never ALTERs existing tables, so an old dev DB fails later
    with a bare OperationalError — this turns that into a clean early exit.

    :param engine: SQLAlchemy engine
    :returns: True when storage_prefix_stats has the current columns
    """
    columns = {col["name"] for col in
               inspect(engine).get_columns("storage_prefix_stats")}
    return {"small_object_count", "small_object_bytes"}.issubset(columns)


def stats_for_run(session, run_id):
    """
    Every aggregate cell persisted for one scan run.

    :param session: SQLAlchemy session
    :param run_id: StorageScanRun id
    :returns: list of StoragePrefixStat
    """
    return (session.query(StoragePrefixStat)
            .filter(StoragePrefixStat.scan_run_id == run_id)
            .order_by(StoragePrefixStat.container, StoragePrefixStat.prefix)
            .all())


def latest_complete_run(session, backend=None):
    """
    Fetch the newest finished storage scan run (complete or partial).

    :param session: SQLAlchemy session
    :param backend: optional backend name filter
    :returns: StorageScanRun or None
    """
    query = session.query(StorageScanRun).filter(
        StorageScanRun.status.in_(["complete", "partial"]))
    if backend:
        query = query.filter(StorageScanRun.backend == backend)
    return query.order_by(StorageScanRun.id.desc()).first()
