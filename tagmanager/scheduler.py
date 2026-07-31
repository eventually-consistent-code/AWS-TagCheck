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
