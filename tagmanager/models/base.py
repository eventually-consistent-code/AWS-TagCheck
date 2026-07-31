"""
Purpose: SQLAlchemy engine/session plumbing and declarative base.
Author(s): John Reed
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """Declarative base for all TagManager tables."""


def get_engine(db_url):
    """
    Build an engine for the given database URL.

    SQLite engines get WAL journaling and a busy timeout — the storage
    job runner's flush writes share the file with periodic tag scans,
    and default journaling invites SQLITE_BUSY.

    :param db_url: SQLAlchemy database URL
    :returns: Engine
    """
    engine = create_engine(db_url)
    if db_url.startswith("sqlite"):
        from sqlalchemy import event  # pylint: disable=import-outside-toplevel

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    return engine


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
