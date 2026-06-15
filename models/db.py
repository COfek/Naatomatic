"""Database engine, session factory, and declarative base.

The SQLite file is the single source of truth (see DESIGN.md §12). Use
``get_engine`` / ``create_session`` to obtain connections; pass ``":memory:"``
as the path for an isolated in-memory database (used by tests).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "naatomatic.db"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite ignores foreign keys unless explicitly enabled per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(db_path: str | Path = DEFAULT_DB_PATH, *, echo: bool = False) -> Engine:
    """Return an engine for the given SQLite path (or ':memory:')."""
    if str(db_path) == ":memory:":
        url = "sqlite:///:memory:"
    else:
        url = f"sqlite:///{Path(db_path).as_posix()}"
    return create_engine(url, echo=echo)


def create_all(engine: Engine) -> None:
    """Create every table defined on the declarative base."""
    # Import the ORM tables so they register on Base.metadata before create_all.
    from models import tables  # noqa: F401

    Base.metadata.create_all(engine)


def create_session(engine: Engine) -> Session:
    """Return a new session bound to the engine."""
    return sessionmaker(bind=engine)()
