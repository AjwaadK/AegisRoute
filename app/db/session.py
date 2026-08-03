"""Synchronous SQLAlchemy database configuration."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import load_project_environment


load_project_environment()


def get_database_url() -> str:
    """Return the configured database URL without exposing credentials."""

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required for database access")
    return database_url


def create_database_engine() -> Engine:
    """Create a synchronous SQLAlchemy engine without opening a connection eagerly."""

    return create_engine(get_database_url())


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Create a configured SQLAlchemy session factory."""

    bind = engine if engine is not None else create_database_engine()
    return sessionmaker(bind=bind, autoflush=False, expire_on_commit=False)
