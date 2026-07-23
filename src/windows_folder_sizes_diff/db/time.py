"""UTC timestamp helpers."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return a naive UTC timestamp for SQLite storage."""

    return datetime.now(UTC).replace(tzinfo=None)
