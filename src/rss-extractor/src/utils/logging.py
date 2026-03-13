"""
utils.logging
=============
Application-wide logging configuration for the Politician Tracker.

Provides a single ``configure_logging`` function that sets up a consistent
log format and level. Call this once at application startup (e.g. from
``cli.py``) before any other code runs.
"""

from __future__ import annotations

import logging
import os

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DEFAULT_LEVEL = "INFO"


def configure_logging(
    level: str | None = None,
    fmt: str = _DEFAULT_FORMAT,
) -> None:
    """Configure the root logger for the application.

    Reads the log level from:
    1. The ``level`` argument (if provided).
    2. The ``LOG_LEVEL`` environment variable.
    3. The default value of ``INFO``.

    Args:
        level: Log level string (e.g. ``"DEBUG"``, ``"INFO"``).
               If ``None``, falls back to the ``LOG_LEVEL`` env var.
        fmt: Log format string. Defaults to a timestamp + level + logger name format.
    """
    resolved_level = level or os.environ.get("LOG_LEVEL", _DEFAULT_LEVEL)
    numeric_level = getattr(logging, resolved_level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format=fmt,
    )
    # Explicitly set the root logger level so repeated calls and calls after
    # pytest (which pre-installs handlers) take effect immediately.
    logging.getLogger().setLevel(numeric_level)
    # Suppress noisy third-party loggers at WARNING unless debug mode
    if numeric_level > logging.DEBUG:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("feedparser").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger by name.

    A thin convenience wrapper so that modules don't need to import ``logging``
    directly just to get a logger.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A ``logging.Logger`` instance.
    """
    return logging.getLogger(name)
