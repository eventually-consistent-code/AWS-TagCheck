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
