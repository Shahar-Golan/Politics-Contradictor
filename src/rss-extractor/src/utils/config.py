"""
utils.config
============
Typed configuration loaders for the Politician Tracker pipeline.

Reads YAML configuration files from the ``config/`` directory and returns
validated Python objects. Raises ``ValueError`` with a descriptive message
if required fields are missing or malformed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from os import PathLike

import yaml

from src.scout.models import FeedSource


# ---------------------------------------------------------------------------
# Domain config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PoliticianConfig:
    """Configuration for a single tracked politician.

    Attributes:
        id: Unique slug identifier (matches ``config/politicians.yaml``).
        name: Canonical full name.
        aliases: List of name variants and nicknames used for text matching.
        party: Political party affiliation.
        role: Current or most recent known role.
        enabled: Whether tracking is active for this politician.
        notes: Optional free-text notes for maintainers.
    """

    id: str
    name: str
    aliases: list[str]
    party: str
    role: str
    enabled: bool = True
    notes: str | None = None


@dataclass
class HttpSettings:
    """HTTP client configuration.

    Attributes:
        user_agent: User-agent string for outbound requests.
        timeout_seconds: Request timeout in seconds.
        max_retries: Maximum number of retry attempts.
        retry_backoff_seconds: Seconds to wait between retries.
        respect_robots_txt: Whether to honour robots.txt rules.
    """

    user_agent: str = "PoliticianTracker/0.1 (research bot)"
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_backoff_seconds: int = 2
    respect_robots_txt: bool = True


@dataclass
class PollingSettings:
    """Feed polling configuration.

    Attributes:
        default_interval_minutes: Default gap between polls (can be overridden per feed).
        max_concurrent_polls: Maximum number of concurrent feed polls.
    """

    default_interval_minutes: int = 30
    max_concurrent_polls: int = 5


@dataclass
class DedupSettings:
    """Deduplication configuration.

    Attributes:
        fingerprint_fields: Fields used to compute a deduplication fingerprint.
    """

    fingerprint_fields: list[str] = field(default_factory=lambda: ["url", "title"])


@dataclass
class ExtractionSettings:
    """Article extraction configuration.

    Attributes:
        min_body_length: Minimum character count for a valid article body.
        preferred_backend: Preferred extraction library name.
    """

    min_body_length: int = 200
    preferred_backend: str = "trafilatura"


@dataclass
class RelevanceSettings:
    """Relevance scoring configuration.

    Attributes:
        min_score: Minimum score (0.0–1.0) for an article to be considered relevant.
    """

    min_score: float = 0.3


@dataclass
class StorageSettings:
    """Storage and persistence configuration.

    Attributes:
        data_dir: Base directory for raw and processed data artefacts.
        database_url: Database connection string.
    """

    data_dir: str = "./data"
    database_url: str = "sqlite:///./data/tracker.db"


@dataclass
class LoggingSettings:
    """Logging configuration.

    Attributes:
        level: Root log level string (e.g. ``"INFO"``).
        format: Log format string.
    """

    level: str = "INFO"
    format: str = "%(asctime)s %(levelname)s %(name)s: %(message)s"


@dataclass
class AppSettings:
    """Top-level application configuration assembled from ``config/settings.yaml``.

    Attributes:
        http: HTTP client settings.
        polling: Feed polling settings.
        dedup: Deduplication settings.
        extraction: Article extraction settings.
        relevance: Relevance scoring settings.
        storage: Storage and persistence settings.
        logging: Logging settings.
    """

    http: HttpSettings = field(default_factory=HttpSettings)
    polling: PollingSettings = field(default_factory=PollingSettings)
    dedup: DedupSettings = field(default_factory=DedupSettings)
    extraction: ExtractionSettings = field(default_factory=ExtractionSettings)
    relevance: RelevanceSettings = field(default_factory=RelevanceSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_feeds(path: str | PathLike[str] | Path) -> list[FeedSource]:
    """Load and validate the feeds configuration file.

    Parses ``config/feeds.yaml`` and returns a list of ``FeedSource`` objects.

    Args:
        path: Path to the feeds YAML file.

    Returns:
        A list of ``FeedSource`` instances.

    Raises:
        ValueError: If the file is malformed or a required field is missing.
        FileNotFoundError: If ``path`` does not exist.
    """
    config_path = _to_path(path)
    raw = _load_yaml(config_path)
    feeds_data = _require_list(raw, "feeds", config_path)
    feeds: list[FeedSource] = []
    for i, entry in enumerate(feeds_data):
        _require_fields(entry, ("id", "name", "url"), context=f"feeds[{i}] in {config_path}")
        feeds.append(
            FeedSource(
                id=entry["id"],
                name=entry["name"],
                url=entry["url"],
                enabled=bool(entry.get("enabled", True)),
                tags=list(entry.get("tags") or []),
                poll_interval_minutes=int(entry.get("poll_interval_minutes", 30)),
            )
        )
    return feeds


def load_politicians(path: str | PathLike[str] | Path) -> list[PoliticianConfig]:
    """Load and validate the politicians configuration file.

    Parses ``config/politicians.yaml`` and returns a list of
    ``PoliticianConfig`` objects.

    Args:
        path: Path to the politicians YAML file.

    Returns:
        A list of ``PoliticianConfig`` instances.

    Raises:
        ValueError: If the file is malformed or a required field is missing.
        FileNotFoundError: If ``path`` does not exist.
    """
    config_path = _to_path(path)
    raw = _load_yaml(config_path)
    politicians_data = _require_list(raw, "politicians", config_path)
    politicians: list[PoliticianConfig] = []
    for i, entry in enumerate(politicians_data):
        _require_fields(
            entry,
            ("id", "name", "aliases", "party", "role"),
            context=f"politicians[{i}] in {config_path}",
        )
        politicians.append(
            PoliticianConfig(
                id=entry["id"],
                name=entry["name"],
                aliases=list(entry["aliases"]),
                party=entry["party"],
                role=entry["role"],
                enabled=bool(entry.get("enabled", True)),
                notes=entry.get("notes"),
            )
        )
    return politicians


def load_settings(path: str | PathLike[str] | Path) -> AppSettings:
    """Load and validate the application settings file.

    Parses ``config/settings.yaml`` and returns an ``AppSettings`` object.
    Missing sections fall back to their dataclass defaults.

    Args:
        path: Path to the settings YAML file.

    Returns:
        An ``AppSettings`` instance.

    Raises:
        ValueError: If the file is malformed.
        FileNotFoundError: If ``path`` does not exist.
    """
    config_path = _to_path(path)
    raw = _load_yaml(config_path)
    if not isinstance(raw, dict):
        raise ValueError(
            f"Settings file must be a YAML mapping, got {type(raw).__name__}: {config_path}"
        )

    http_raw = raw.get("http") or {}
    polling_raw = raw.get("polling") or {}
    dedup_raw = raw.get("dedup") or {}
    extraction_raw = raw.get("extraction") or {}
    relevance_raw = raw.get("relevance") or {}
    storage_raw = raw.get("storage") or {}
    logging_raw = raw.get("logging") or {}

    return AppSettings(
        http=HttpSettings(
            user_agent=str(http_raw.get("user_agent", "PoliticianTracker/0.1 (research bot)")),
            timeout_seconds=int(http_raw.get("timeout_seconds", 30)),
            max_retries=int(http_raw.get("max_retries", 3)),
            retry_backoff_seconds=int(http_raw.get("retry_backoff_seconds", 2)),
            respect_robots_txt=bool(http_raw.get("respect_robots_txt", True)),
        ),
        polling=PollingSettings(
            default_interval_minutes=int(polling_raw.get("default_interval_minutes", 30)),
            max_concurrent_polls=int(polling_raw.get("max_concurrent_polls", 5)),
        ),
        dedup=DedupSettings(
            fingerprint_fields=list(dedup_raw.get("fingerprint_fields", ["url", "title"])),
        ),
        extraction=ExtractionSettings(
            min_body_length=int(extraction_raw.get("min_body_length", 200)),
            preferred_backend=str(extraction_raw.get("preferred_backend", "trafilatura")),
        ),
        relevance=RelevanceSettings(
            min_score=float(relevance_raw.get("min_score", 0.3)),
        ),
        storage=StorageSettings(
            data_dir=str(storage_raw.get("data_dir", "./data")),
            database_url=str(storage_raw.get("database_url", "sqlite:///./data/tracker.db")),
        ),
        logging=LoggingSettings(
            level=str(logging_raw.get("level", "INFO")),
            format=str(
                logging_raw.get(
                    "format",
                    "%(asctime)s %(levelname)s %(name)s: %(message)s",
                )
            ),
        ),
    )


def load_topics(path: str | PathLike[str] | Path) -> dict[str, list[str]]:
    """Load and validate the topics configuration file.

    Parses ``config/topics.yaml`` and returns a mapping from topic ID to
    its list of keywords.

    Args:
        path: Path to the topics YAML file.

    Returns:
        A ``dict`` mapping topic ``id`` → list of keyword strings.

    Raises:
        ValueError: If the file is malformed or a required field is missing.
        FileNotFoundError: If ``path`` does not exist.
    """
    config_path = _to_path(path)
    raw = _load_yaml(config_path)
    topics_data = _require_list(raw, "topics", config_path)
    result: dict[str, list[str]] = {}
    for i, entry in enumerate(topics_data):
        _require_fields(entry, ("id", "keywords"), context=f"topics[{i}] in {config_path}")
        result[entry["id"]] = list(entry["keywords"])
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _to_path(path: str | PathLike[str] | Path) -> Path:
    """Normalize path-like values to ``Path`` for loader helpers."""
    return Path(path)


def _load_yaml(path: str | PathLike[str] | Path) -> object:
    """Read and parse a YAML file, returning the top-level Python object."""
    yaml_path = _to_path(path)
    try:
        with yaml_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML file {yaml_path}: {exc}") from exc


def _require_list(data: object, key: str, path: Path) -> list[object]:
    """Extract a list from a mapping, raising ``ValueError`` if absent or wrong type."""
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a YAML mapping at the top level of {path}, got {type(data).__name__}"
        )
    value = data.get(key)
    if value is None:
        raise ValueError(f"Required key '{key}' is missing in {path}")
    if not isinstance(value, list):
        raise ValueError(
            f"Expected '{key}' to be a list in {path}, got {type(value).__name__}"
        )
    return value  # type: ignore[return-value]


def _require_fields(
    entry: object,
    fields: tuple[str, ...],
    context: str,
) -> None:
    """Raise ``ValueError`` if any required field is absent from a mapping entry."""
    if not isinstance(entry, dict):
        raise ValueError(f"Expected a mapping at {context}, got {type(entry).__name__}")
    for field_name in fields:
        if field_name not in entry or entry[field_name] is None:
            raise ValueError(
                f"Required field '{field_name}' is missing or null at {context}"
            )
