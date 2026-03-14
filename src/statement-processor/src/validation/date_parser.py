"""
validation.date_parser
======================
Deterministic date parsing and standardization for stance event dates.

Supported input formats
-----------------------
* ``YYYY-MM-DD`` → precision ``day``
* ``YYYY-MM``    → precision ``month``
* ``YYYY``       → precision ``year``

Unsupported / unparseable dates are treated as errors (not silently accepted).

Design notes
------------
* Uses Python's ``datetime`` module only — no third-party date parsers — so
  the behavior is fully deterministic and dependency-free.
* Returns a ``ParsedDate`` named tuple so callers have typed access to both
  the canonical string and the inferred precision.
* Never raises; always returns a result object that includes an error message
  when parsing fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedDate:
    """Result of parsing a raw date string.

    Attributes
    ----------
    canonical:
        The standardized date string (``YYYY-MM-DD``, ``YYYY-MM``, or
        ``YYYY``), or ``None`` if parsing failed.
    precision:
        Inferred precision (``"day"``, ``"month"``, ``"year"``), or ``None``
        if parsing failed.
    error:
        Human-readable parse failure message, or ``None`` on success.
    """

    canonical: str | None
    precision: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """``True`` iff parsing succeeded."""
        return self.error is None


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Strict YYYY-MM-DD  (no time component)
_RE_DAY = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")
# Strict YYYY-MM
_RE_MONTH = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
# Strict YYYY (4 digits)
_RE_YEAR = re.compile(r"^\d{4}$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_date(raw: str | None) -> ParsedDate:
    """Parse *raw* into a canonical date string and precision.

    Parameters
    ----------
    raw:
        The raw date string from the extractor.  May be ``None``.

    Returns
    -------
    ParsedDate
        A result object with ``canonical``, ``precision``, and ``error``
        attributes.  On success ``error`` is ``None``; on failure
        ``canonical`` and ``precision`` are ``None``.

    Examples
    --------
    >>> parse_date("2024-01-12")
    ParsedDate(canonical='2024-01-12', precision='day', error=None)
    >>> parse_date("2024-01")
    ParsedDate(canonical='2024-01', precision='month', error=None)
    >>> parse_date("2024")
    ParsedDate(canonical='2024', precision='year', error=None)
    >>> parse_date("not-a-date")
    ParsedDate(canonical=None, precision=None, error='...')
    >>> parse_date(None)
    ParsedDate(canonical=None, precision=None, error=None)
    """
    if raw is None:
        return ParsedDate(canonical=None, precision=None, error=None)

    stripped = raw.strip()

    if _RE_DAY.match(stripped):
        # Further validate the calendar day (e.g. reject 2024-02-31)
        try:
            _validate_calendar_day(stripped)
        except ValueError as exc:
            return ParsedDate(
                canonical=None,
                precision=None,
                error=f"Invalid calendar day '{stripped}': {exc}",
            )
        return ParsedDate(canonical=stripped, precision="day", error=None)

    if _RE_MONTH.match(stripped):
        return ParsedDate(canonical=stripped, precision="month", error=None)

    if _RE_YEAR.match(stripped):
        year = int(stripped)
        # The range 1900–2100 is conservative for political stance events.
        # Political figures active in the modern era were born no earlier than
        # the late 1800s, and extraction of future pledges beyond 2100 is
        # implausible.  Extend this range if the corpus requires it.
        if year < 1900 or year > 2100:
            return ParsedDate(
                canonical=None,
                precision=None,
                error=f"Year '{stripped}' is outside the plausible range 1900–2100.",
            )
        return ParsedDate(canonical=stripped, precision="year", error=None)

    return ParsedDate(
        canonical=None,
        precision=None,
        error=(
            f"Unparseable date '{stripped}'. "
            "Expected YYYY-MM-DD, YYYY-MM, or YYYY."
        ),
    )


def validate_precision_match(
    parsed: ParsedDate,
    declared_precision: str | None,
) -> str | None:
    """Check that *declared_precision* is consistent with the parsed date.

    Parameters
    ----------
    parsed:
        The result of :func:`parse_date`.
    declared_precision:
        The ``event_date_precision`` field from the extractor output.

    Returns
    -------
    str | None
        An error message if there is a mismatch, or ``None`` if they agree
        (or if the comparison is not possible because parsing failed or
        ``declared_precision`` is ``None``).
    """
    if not parsed.ok or declared_precision is None:
        return None
    if parsed.precision != declared_precision:
        return (
            f"Date precision mismatch: date '{parsed.canonical}' implies "
            f"precision '{parsed.precision}' but declared precision is "
            f"'{declared_precision}'."
        )
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_calendar_day(date_str: str) -> None:
    """Raise ``ValueError`` if *date_str* is not a valid calendar day.

    Parameters
    ----------
    date_str:
        A string matching ``YYYY-MM-DD`` that should be validated as a real
        calendar date (e.g. not 2024-02-31).
    """
    import datetime  # local import to keep module-level imports clean

    year, month, day = (int(p) for p in date_str.split("-"))
    datetime.date(year, month, day)  # raises ValueError for impossible dates
