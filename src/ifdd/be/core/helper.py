"""Small time helpers shared by the routers and the write path."""

from datetime import datetime, timezone


def ensure_timezone_utc(dt: datetime) -> datetime:
    """Read a naive date-time as UTC; leave an aware one unchanged.

    Args:
        dt: A date-time, with or without time zone.

    Returns:
        ``dt`` with ``tzinfo=UTC`` if it had no time zone, else ``dt``.
    """
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def utc_now() -> datetime:
    """The current time, aware, in UTC."""
    return datetime.now(tz=timezone.utc)
