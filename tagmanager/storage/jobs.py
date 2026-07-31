"""
Purpose: Background storage-scan jobs — submit onto the app's APScheduler
(dedicated executor so hour-long walks never starve periodic tag scans),
flush progress in batches, honor cooperative cancellation, and sweep
orphans at boot. Single-replica, in-process by design.
Author(s): John Reed
"""

import datetime
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.exc import IntegrityError

from tagmanager.models.tables import StorageJob, StorageTarget
from tagmanager.storage.services import (ScanCancelled, ScanOptions,
                                         StorageServiceError,
                                         run_storage_scan)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.storage_jobs")
LOG.setLevel(logging.INFO)


# Constants

STORAGE_EXECUTOR = "storage"
STORAGE_EXECUTOR_WORKERS = 2
DEFAULT_FLUSH_OBJECTS = 5000
DEFAULT_FLUSH_SECONDS = 5.0
ACTIVE_STATES = ("queued", "running")


def _utc_now():
    """Timezone-aware UTC now."""
    return datetime.datetime.now(datetime.timezone.utc)


def register_storage_executor(scheduler,
                              max_workers=STORAGE_EXECUTOR_WORKERS):
    """
    Add the dedicated storage-job executor to a (built) scheduler.

    :param scheduler: APScheduler BackgroundScheduler
    :param max_workers: thread count for user-triggered scans
    """
    from apscheduler.executors.pool import ThreadPoolExecutor  # pylint: disable=import-outside-toplevel
    scheduler.add_executor(ThreadPoolExecutor(max_workers),
                           alias=STORAGE_EXECUTOR)


@dataclass
class FlushPolicy:
    """Progress-flush pacing — injectable so tests never sleep."""

    objects: int = DEFAULT_FLUSH_OBJECTS
    seconds: float = DEFAULT_FLUSH_SECONDS
    clock: object = field(default=time.monotonic)


def submit_scan(scheduler, session_maker, target_id, *, provider=None,
                flush=None):
    """
    Queue a scan job for a target and hand it to the scheduler.

    The job row commits BEFORE add_job — the worker thread's fresh
    session must be able to see it. One active job per target is
    enforced by the partial unique index; the losing concurrent submit's
    IntegrityError is the overlap refusal.

    :param scheduler: scheduler exposing add_job (real or test fake)
    :param session_maker: sessionmaker
    :param target_id: StorageTarget id
    :param provider: injected StorageProvider (tests)
    :param flush: FlushPolicy (default pacing when None)
    :returns: job id
    :raises StorageServiceError: unknown/disabled target or active job
    """
    session = session_maker()
    try:
        target = session.get(StorageTarget, target_id)
        if target is None or not target.enabled:
            raise StorageServiceError(
                f"no enabled storage target with id {target_id}")
        job = StorageJob(target_id=target_id)
        session.add(job)
        try:
            session.commit()
        except IntegrityError as err:
            session.rollback()
            raise StorageServiceError(
                "a scan is already queued or running for this target"
            ) from err
        job_id = job.id
    finally:
        session.close()

    scheduler.add_job(run_job, args=[session_maker, job_id],
                      kwargs={"provider": provider, "flush": flush},
                      executor=STORAGE_EXECUTOR,
                      id=f"storage-job-{job_id}",
                      misfire_grace_time=None)
    return job_id


def _target_options(target):
    """ScanOptions from a StorageTarget row snapshot."""
    options = dict(target.options or {})
    return ScanOptions(
        backend=target.backend,
        account_url=target.account_url,
        buckets=tuple(target.buckets or ()),
        prefix=target.prefix,
        age_band_days=list(target.age_band_days) or None,
        rollup_owners=bool(options.get("rollup_owners", False)),
    )


def _progress_hook(session_maker, job_id, flush):
    """
    Per-object hook: batched progress flush + cooperative cancel check.

    Each flush is a short-lived session; the same touch reads
    cancel_requested and raises ScanCancelled when set.
    """
    clock = flush.clock
    state = {"last_count": 0, "last_time": clock()}

    def on_object(count):
        due = (count - state["last_count"] >= flush.objects
               or clock() - state["last_time"] >= flush.seconds)
        if not due:
            return
        state["last_count"] = count
        state["last_time"] = clock()
        session = session_maker()
        try:
            job = session.get(StorageJob, job_id)
            job.objects_seen = count
            cancel = job.cancel_requested
            session.commit()
        finally:
            session.close()
        if cancel:
            raise ScanCancelled()

    return on_object


def run_job(session_maker, job_id, provider=None, flush=None):
    """
    Execute one queued job in the worker thread.

    :param session_maker: sessionmaker (sessions built in-thread)
    :param job_id: StorageJob id
    :param provider: injected StorageProvider (tests)
    :param flush: FlushPolicy (default pacing when None)
    """
    flush = flush or FlushPolicy()
    session = session_maker()
    try:
        job = session.get(StorageJob, job_id)
        if job is None or job.state != "queued":
            LOG.warning("job %s missing or not queued — skipping", job_id)
            return
        job.state = "running"
        job.started_at = _utc_now()
        session.commit()
        opts = _target_options(session.get(StorageTarget, job.target_id))
    finally:
        session.close()

    opts.on_object = _progress_hook(session_maker, job_id, flush)

    final_state, error, run_id, objects = "done", "", None, 0
    try:
        result = run_storage_scan(session_maker, opts, provider=provider)
        run_id = result.run_id
        objects = result.builder.objects_seen
        if result.cancelled:
            final_state = "cancelled"
    except Exception as err:  # pylint: disable=broad-exception-caught
        LOG.error("storage job %s failed: %s", job_id, err)
        final_state, error = "failed", str(err)[:1024]

    session = session_maker()
    try:
        job = session.get(StorageJob, job_id)
        job.state = final_state
        job.error = error
        job.scan_run_id = run_id
        job.objects_seen = max(job.objects_seen or 0, objects)
        job.finished_at = _utc_now()
        session.commit()
    finally:
        session.close()


def request_cancel(session_maker, job_id):
    """
    Flip a job's cancel flag; the walk honors it at the next flush.

    :param session_maker: sessionmaker
    :param job_id: StorageJob id
    :returns: True when the job existed and was active
    """
    session = session_maker()
    try:
        job = session.get(StorageJob, job_id)
        if job is None or job.state not in ACTIVE_STATES:
            return False
        job.cancel_requested = True
        session.commit()
        return True
    finally:
        session.close()


def sweep_orphan_jobs(session):
    """
    Boot-time sweep: queued/running rows are orphans — the threads died
    with the last process. Mark them interrupted.

    :param session: SQLAlchemy session (caller owns lifecycle)
    :returns: number of jobs swept
    """
    orphans = (session.query(StorageJob)
               .filter(StorageJob.state.in_(ACTIVE_STATES)).all())
    for job in orphans:
        job.state = "interrupted"
        job.finished_at = _utc_now()
    session.commit()
    if orphans:
        LOG.info("swept %s orphaned storage job(s) to interrupted.",
                 len(orphans))
    return len(orphans)
