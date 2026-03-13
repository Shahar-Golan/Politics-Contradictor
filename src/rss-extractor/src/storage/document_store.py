"""
storage.document_store
=======================
Document storage interface for raw HTML and extracted article bodies.

Manages the filesystem layout under the configured data directory.
Raw HTML files and extracted text are stored as flat files under
``data/raw/articles/`` and ``data/processed/`` respectively.

Module-level standalone functions are provided for callers that pass
``data_dir`` explicitly.  The :class:`DocumentStore` class is
available for callers that prefer to fix a root data directory once
at construction time.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standalone functions
# ---------------------------------------------------------------------------


def save_raw_html(article_id: str, html: str, data_dir: Path) -> Path:
    """Write raw HTML content to disk and return the file path.

    The file is placed at ``<data_dir>/raw/articles/<article_id>.html``.
    Parent directories are created automatically.

    Args:
        article_id: Unique ID for the article (used as filename).
        html: Raw HTML string to write.
        data_dir: Root data directory.

    Returns:
        Path to the written file.
    """
    path = data_dir / "raw" / "articles" / f"{article_id}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    logger.debug("Saved raw HTML for %s to %s.", article_id, path)
    return path


def load_raw_html(article_id: str, data_dir: Path) -> str | None:
    """Read and return raw HTML for a given article ID.

    Args:
        article_id: Unique ID for the article.
        data_dir: Root data directory.

    Returns:
        HTML string, or ``None`` if the file does not exist.
    """
    path = data_dir / "raw" / "articles" / f"{article_id}.html"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_extracted_text(article_id: str, text: str, data_dir: Path) -> Path:
    """Write extracted article body text to disk and return the file path.

    The file is placed at ``<data_dir>/processed/<article_id>.txt``.
    Parent directories are created automatically.

    Args:
        article_id: Unique ID for the article.
        text: Clean extracted body text.
        data_dir: Root data directory.

    Returns:
        Path to the written file.
    """
    path = data_dir / "processed" / f"{article_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    logger.debug("Saved extracted text for %s to %s.", article_id, path)
    return path


def load_extracted_text(article_id: str, data_dir: Path) -> str | None:
    """Read and return extracted body text for a given article ID.

    Args:
        article_id: Unique ID for the article.
        data_dir: Root data directory.

    Returns:
        Body text string, or ``None`` if the file does not exist.
    """
    path = data_dir / "processed" / f"{article_id}.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# DocumentStore class
# ---------------------------------------------------------------------------


class DocumentStore:
    """Manages file-based storage for raw and processed article documents.

    Args:
        data_dir: Root data directory (e.g. ``Path("./data")``).
    """

    def __init__(self, data_dir: Path) -> None:
        """Initialise the document store and create subdirectories if needed."""
        self._data_dir = data_dir
        self._raw_dir = data_dir / "raw" / "articles"
        self._processed_dir = data_dir / "processed"
        self._failed_dir = data_dir / "failed"

        self._raw_dir.mkdir(parents=True, exist_ok=True)
        self._processed_dir.mkdir(parents=True, exist_ok=True)
        self._failed_dir.mkdir(parents=True, exist_ok=True)

    def save_raw_html(self, article_id: str, html: str) -> Path:
        """Write raw HTML content to disk and return the file path.

        Args:
            article_id: Unique ID for the article (used as filename).
            html: Raw HTML string to write.

        Returns:
            Path to the written file.
        """
        path = self._raw_dir / f"{article_id}.html"
        path.write_text(html, encoding="utf-8")
        logger.debug("Saved raw HTML for %s to %s.", article_id, path)
        return path

    def load_raw_html(self, article_id: str) -> str | None:
        """Read and return raw HTML for a given article ID.

        Args:
            article_id: Unique ID for the article.

        Returns:
            HTML string, or ``None`` if the file does not exist.
        """
        path = self._raw_dir / f"{article_id}.html"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def save_extracted_body(self, article_id: str, body: str) -> Path:
        """Write extracted article body text to disk.

        Args:
            article_id: Unique ID for the article.
            body: Clean extracted body text.

        Returns:
            Path to the written file.
        """
        path = self._processed_dir / f"{article_id}.txt"
        path.write_text(body, encoding="utf-8")
        logger.debug("Saved extracted body for %s to %s.", article_id, path)
        return path

    def save_extracted_text(self, article_id: str, text: str) -> Path:
        """Alias for :meth:`save_extracted_body`.

        Args:
            article_id: Unique ID for the article.
            text: Clean extracted body text.

        Returns:
            Path to the written file.
        """
        return self.save_extracted_body(article_id, text)

    def load_extracted_body(self, article_id: str) -> str | None:
        """Read and return the extracted body text for a given article ID.

        Args:
            article_id: Unique ID for the article.

        Returns:
            Body text string, or ``None`` if the file does not exist.
        """
        path = self._processed_dir / f"{article_id}.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def load_extracted_text(self, article_id: str) -> str | None:
        """Alias for :meth:`load_extracted_body`.

        Args:
            article_id: Unique ID for the article.

        Returns:
            Body text string, or ``None`` if the file does not exist.
        """
        return self.load_extracted_body(article_id)

    def save_failed(self, article_id: str, reason: str) -> Path:
        """Write a failure record for an article that could not be processed.

        Args:
            article_id: Unique ID for the article.
            reason: Human-readable reason for failure.

        Returns:
            Path to the written file.
        """
        path = self._failed_dir / f"{article_id}.txt"
        path.write_text(reason, encoding="utf-8")
        logger.debug("Saved failure record for %s.", article_id)
        return path

    def raw_html_path(self, article_id: str) -> Path:
        """Return the expected path for raw HTML without checking existence.

        Args:
            article_id: Unique article ID.

        Returns:
            Expected ``Path`` for the raw HTML file.
        """
        return self._raw_dir / f"{article_id}.html"

    def extracted_body_path(self, article_id: str) -> Path:
        """Return the expected path for extracted body text without checking existence.

        Args:
            article_id: Unique article ID.

        Returns:
            Expected ``Path`` for the extracted body text file.
        """
        return self._processed_dir / f"{article_id}.txt"
