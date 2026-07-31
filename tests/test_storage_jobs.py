"""
Purpose: Tests for background storage jobs — submit-to-done with observed
progress flushes, mid-stream cooperative cancel, overlap refusal via the
partial unique index, and the boot orphan sweep. No sleeps: a synchronous
FakeScheduler runs workers inline and flush thresholds are injected.
Author(s): John Reed
"""

import datetime

import pytest

from tagmanager.models.tables import StorageJob, StorageTarget
from tagmanager.storage import jobs, services
from tagmanager.storage.base import StorageObject

NOW = datetime.datetime.now(datetime.timezone.utc)


class FakeScheduler:
    """add_job runs the worker inline (the real one threads it)."""

    def __init__(self, run_inline=True):
        self.run_inline = run_inline
        self.submitted = []

    def add_job(self, func, args=(), kwargs=None, **_meta):
        self.submitted.append((func, args, kwargs or {}))
        if self.run_inline:
            func(*args, **(kwargs or {}))


def _maker(tmp_path, monkeypatch, name="jobs.db"):
    monkeypatch.setenv("TAGMANAGER_DB_URL", f"sqlite:///{tmp_path / name}")
    return services.open_storage_session_maker()


def _add_target(maker, **overrides):
    fields = {"backend": "s3", "buckets": ["bkt"],
              "age_band_days": [90, 365]}
    fields.update(overrides)
    session = maker()
    try:
        target = StorageTarget(**fields)
        session.add(target)
        session.commit()
        return target.id
    finally:
        session.close()


def _objects(count):
    return [StorageObject(backend="s3", container="bkt", key=f"logs/f{i}",
                          size_bytes=1024,
                          last_modified=NOW - datetime.timedelta(days=500))
            for i in range(count)]


class _Provider:
    backend_name = "s3"

    def __init__(self, objs):
        self._objs = objs

    def list_objects(self, container, prefix=""):
        yield from self._objs

    def capabilities(self):
        raise NotImplementedError


def test_submit_runs_to_done_with_flushes(tmp_path, monkeypatch):
    """Inline job finishes done; progress flushed at the injected batch."""
    maker = _maker(tmp_path, monkeypatch)
    target_id = _add_target(maker)

    job_id = jobs.submit_scan(FakeScheduler(), maker, target_id,
                              provider=_Provider(_objects(7)),
                              flush=jobs.FlushPolicy(objects=2,
                                                     seconds=9999))

    session = maker()
    job = session.get(StorageJob, job_id)
    assert job.state == "done"
    assert job.objects_seen == 7
    assert job.scan_run_id is not None
    assert job.started_at is not None and job.finished_at is not None


def test_cancel_mid_stream_at_batch_boundary(tmp_path, monkeypatch):
    """cancel_requested flipped mid-walk stops at the next flush; the run
    persists as cancelled and the job records the cancel."""
    maker = _maker(tmp_path, monkeypatch)
    target_id = _add_target(maker)
    scheduler = FakeScheduler(run_inline=False)
    job_id = jobs.submit_scan(scheduler, maker, target_id,
                              flush=jobs.FlushPolicy(objects=2,
                                                     seconds=9999))

    class _CancellingProvider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            for i, obj in enumerate(_objects(50)):
                if i == 3:
                    assert jobs.request_cancel(maker, job_id)
                yield obj

        def capabilities(self):
            raise NotImplementedError

    func, args, kwargs = scheduler.submitted[0]
    kwargs["provider"] = _CancellingProvider()
    func(*args, **kwargs)

    session = maker()
    job = session.get(StorageJob, job_id)
    assert job.state == "cancelled"
    assert job.objects_seen < 50
    from tagmanager.models.tables import StorageScanRun  # pylint: disable=import-outside-toplevel
    run = session.get(StorageScanRun, job.scan_run_id)
    assert run.status == "cancelled"


def test_overlap_refusal_second_submit(tmp_path, monkeypatch):
    """A queued job blocks a second submit for the same target."""
    maker = _maker(tmp_path, monkeypatch)
    target_id = _add_target(maker)
    idle = FakeScheduler(run_inline=False)

    jobs.submit_scan(idle, maker, target_id)
    with pytest.raises(services.StorageServiceError, match="already queued"):
        jobs.submit_scan(idle, maker, target_id)

    other_target = _add_target(maker)
    jobs.submit_scan(idle, maker, other_target)  # other targets unaffected


def test_submit_rejects_unknown_or_disabled_target(tmp_path, monkeypatch):
    maker = _maker(tmp_path, monkeypatch)
    with pytest.raises(services.StorageServiceError, match="no enabled"):
        jobs.submit_scan(FakeScheduler(), maker, 999)
    disabled = _add_target(maker, enabled=False)
    with pytest.raises(services.StorageServiceError, match="no enabled"):
        jobs.submit_scan(FakeScheduler(), maker, disabled)


def test_failed_job_captures_error(tmp_path, monkeypatch):
    """A provider blowing up mid-walk leaves state=failed with the error."""
    maker = _maker(tmp_path, monkeypatch)
    target_id = _add_target(maker, backend="azure")  # no account_url -> boom

    job_id = jobs.submit_scan(FakeScheduler(), maker, target_id)

    session = maker()
    job = session.get(StorageJob, job_id)
    assert job.state == "failed"
    assert "account-url" in job.error


def test_flush_seconds_arm_with_injected_clock(tmp_path, monkeypatch):
    """The time arm flushes (and picks up cancel) without the object arm."""
    maker = _maker(tmp_path, monkeypatch)
    target_id = _add_target(maker)
    scheduler = FakeScheduler(run_inline=False)

    ticks = {"now": 0.0}

    def clock():
        ticks["now"] += 3.0  # every check advances fake time
        return ticks["now"]

    job_id = jobs.submit_scan(
        scheduler, maker, target_id,
        flush=jobs.FlushPolicy(objects=10_000, seconds=5.0, clock=clock))

    class _CancellingProvider:
        backend_name = "s3"

        def list_objects(self, container, prefix=""):
            for i, obj in enumerate(_objects(20)):
                if i == 2:
                    assert jobs.request_cancel(maker, job_id)
                yield obj

        def capabilities(self):
            raise NotImplementedError

    func, args, kwargs = scheduler.submitted[0]
    kwargs["provider"] = _CancellingProvider()
    func(*args, **kwargs)

    session = maker()
    job = session.get(StorageJob, job_id)
    assert job.state == "cancelled"
    assert 0 < job.objects_seen < 20


def test_build_scheduler_carries_storage_executor(tmp_path, monkeypatch):
    """Verifier finding: any build_scheduler caller can run storage jobs —
    submit against a bare build_scheduler executes, never silent-queues."""
    from tagmanager.config import Settings  # pylint: disable=import-outside-toplevel
    from tagmanager.scheduler import build_scheduler  # pylint: disable=import-outside-toplevel

    maker = _maker(tmp_path, monkeypatch)
    target_id = _add_target(maker)
    scheduler = build_scheduler(Settings(scan_interval_minutes=9999), maker,
                                {}, lambda: [])
    scheduler.start(paused=False)
    try:
        job_id = jobs.submit_scan(scheduler, maker, target_id,
                                  provider=_Provider(_objects(3)))
        deadline = datetime.datetime.now() + datetime.timedelta(seconds=10)
        state = "queued"
        while datetime.datetime.now() < deadline:
            session = maker()
            state = session.get(StorageJob, job_id).state
            session.close()
            if state not in ("queued", "running"):
                break
        assert state == "done"
    finally:
        scheduler.shutdown(wait=True)


def test_boot_sweep_marks_both_orphan_states(tmp_path, monkeypatch):
    """queued AND running orphans become interrupted at boot."""
    maker = _maker(tmp_path, monkeypatch)
    target_a = _add_target(maker)
    target_b = _add_target(maker)
    session = maker()
    session.add(StorageJob(target_id=target_a, state="queued"))
    session.add(StorageJob(target_id=target_b, state="running"))
    session.add(StorageJob(target_id=target_a, state="done"))
    session.commit()

    assert jobs.sweep_orphan_jobs(session) == 2
    states = [job.state for job in session.query(StorageJob)
              .order_by(StorageJob.id)]
    assert states == ["interrupted", "interrupted", "done"]
