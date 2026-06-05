"""SQL engine and session management for LoopCloser.

Supports any SQLAlchemy-compatible database (SQLite, PostgreSQL, MySQL, etc.)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from src.models.models_sql import Base


class SQLService:
    """Manage SQL database engine and sessions via SQLAlchemy.

    Automatically detects database type from connection URL and configures
    appropriately. Supports SQLite, PostgreSQL, MySQL, and other SQLAlchemy dialects.
    """

    def __init__(self, db_path: str | None = None) -> None:
        db_url = db_path or os.getenv("DATABASE_URL", "sqlite:///loopcloser.db")
        assert db_url is not None, "DATABASE_URL must be set"
        is_sqlite = db_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        # pool_pre_ping validates a pooled connection before use, transparently
        # reconnecting if it's dead. Without it, serverless Postgres (e.g. Neon)
        # closes idle connections and the next reuse fails with
        # "SSL connection has been closed unexpectedly". pool_recycle proactively
        # drops connections older than the idle window. (No-ops for SQLite.)
        if is_sqlite:
            self.engine = create_engine(
                db_url,
                future=True,
                echo=False,
                connect_args=connect_args,
                pool_pre_ping=True,
            )
        else:
            self.engine = create_engine(
                db_url,
                future=True,
                echo=False,
                connect_args=connect_args,
                pool_pre_ping=True,
                pool_recycle=300,
            )
        Base.metadata.create_all(self.engine)
        self._session_factory = scoped_session(
            sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        )

    def get_session(self) -> Any:
        return self._session_factory()

    def remove_session(self) -> None:
        self._session_factory.remove()

    @contextmanager
    def session_scope(self) -> Iterator[Any]:
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        """Dispose of the engine and connection pool."""
        self._session_factory.remove()
        self.engine.dispose()
