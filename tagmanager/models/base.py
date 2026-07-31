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
