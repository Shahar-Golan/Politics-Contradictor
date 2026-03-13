"""
utils.hashing
=============
Deterministic content fingerprinting helpers.

Provides stable, short hash identifiers for URLs and text content,
used to deduplicate feed items and articles across pipeline runs.
"""

from __future__ import annotations

import hashlib

from src.utils.urls import normalize_url


def hash_url(url: str) -> str:
    """Return a deterministic SHA-256 hex digest for a normalised URL.

    The URL is normalised before hashing so that equivalent URLs
    (e.g. with and without tracking parameters) produce the same hash.

    Args:
        url: Raw URL string.

    Returns:
        64-character lowercase hex string.
    """
    normalised = normalize_url(url)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def hash_content(text: str) -> str:
    """Return a deterministic SHA-256 hex digest for arbitrary text content.

    Args:
        text: Text content to hash.

    Returns:
        64-character lowercase hex string.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_hash(text: str, length: int = 16) -> str:
    """Return a truncated hex digest, suitable for short IDs.

    Args:
        text: Text content to hash.
        length: Number of hex characters to return (max 64).

    Returns:
        Hex string of the requested length.
    """
    return hash_content(text)[:length]


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

#: Alias for :func:`hash_content` matching the roadmap spec name.
content_hash = hash_content

#: Alias for :func:`hash_url` matching the roadmap spec name.
url_hash = hash_url
