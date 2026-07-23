"""Database engine and session factory setup."""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from windows_folder_sizes_diff.constants import PROJECT_ROOT


def resolve_database_path(path: Path | str) -> Path:
    database_path = Path(path).expanduser()
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    return database_path


def database_url_from_path(path: Path | str) -> str:
    database_path = resolve_database_path(path)
    return f"sqlite:///{database_path.as_posix()}"


def create_database_engine(database_path: Path | str) -> Engine:
    resolved = resolve_database_path(database_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url_from_path(resolved), future=True)
    _install_sqlite_pragmas(engine)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def _install_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        if not isinstance(dbapi_connection, SQLiteConnection):
            return
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()
