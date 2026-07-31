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
from tagmanager.scanner import reap_stale_runs
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
    """
    Boot TagManager: DB, rules seed, stale-run reap, scheduler, web server.

    The stale-run reap runs once at boot, before the scheduler starts —
    safe only under the single-replica assumption (see
    scanner.reap_stale_runs), since two replicas booting at once could
    otherwise reap a run that's genuinely in progress on the other one.
    """
    settings = get_settings()
    LOG.info("starting tagmanager...")
    engine = get_engine(settings.db_url)
    create_all(engine)
    maker = session_factory(engine)

    if os.path.exists("canonical.json"):
        session = maker()
        try:
            seed_rules_from_canonical(session, "canonical.json")
        finally:
            session.close()

    session = maker()
    try:
        reap_stale_runs(session)
    finally:
        session.close()

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
