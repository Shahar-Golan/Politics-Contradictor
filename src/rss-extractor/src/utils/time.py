"""
utils.time
==========
Timestamp parsing and normalisation helpers.

Converts the various timestamp formats encountered in RSS/Atom feeds and
HTML metadata into timezone-aware UTC ``datetime`` objects.
"""

from __future__ import annotations

import calendar
import time
from datetime import datetime, timezone

from dateutil import parser as dateutil_parser  # type: ignore[import]


def parse_feed_timestamp(time_struct: time.struct_time) -> datetime:
    """Convert a feedparser ``time.struct_time`` to a UTC-aware ``datetime``.

    feedparser stores parsed timestamps as ``time.struct_time`` in UTC.

    Args:
        time_struct: A ``time.struct_time`` tuple as returned by feedparser.

    Returns:
        A timezone-aware ``datetime`` in UTC.

    Raises:
        TypeError: If ``time_struct`` is not a valid struct_time.
        ValueError: If the struct_time contains out-of-range values.
        OverflowError: If the timestamp is out of representable range.
    """
    timestamp = calendar.timegm(time_struct)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def parse_datetime_string(raw: str) -> datetime:
    """Parse a datetime string into a timezone-aware UTC ``datetime``.

    Accepts a wide variety of formats including ISO 8601, RFC 2822,
    and common date strings. Uses ``python-dateutil`` for flexible parsing.

    Args:
        raw: Raw datetime string.

    Returns:
        A timezone-aware ``datetime`` in UTC. If the parsed value is naive,
        it is assumed to be UTC.

    Raises:
        ValueError: If the string cannot be parsed.
        TypeError: If ``raw`` is not a string.
    """
    dt = dateutil_parser.parse(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware ``datetime``.

    Returns:
        Current time in UTC with timezone info set.
    """
    return datetime.now(tz=timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    """Parse a datetime string, returning ``None`` for unparseable or absent input.

    Accepts a wide variety of formats including ISO 8601 and RFC 2822.
    Returns ``None`` rather than raising on failure, making it safe to use
    when the timestamp may be absent or malformed.

    Args:
        value: Raw datetime string, or ``None``.

    Returns:
        A timezone-aware ``datetime`` in UTC, or ``None`` if parsing fails.
    """
    if value is None:
        return None
    try:
        return parse_datetime_string(value)
    except (ValueError, TypeError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

#: Alias for :func:`utcnow` matching the roadmap spec name.
utc_now = utcnow
