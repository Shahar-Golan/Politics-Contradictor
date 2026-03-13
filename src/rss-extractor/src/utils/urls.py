"""
utils.urls
==========
URL normalisation and canonicalisation helpers.

Provides deterministic URL cleaning so that equivalent article URLs
produce the same fingerprint for deduplication purposes.
"""

from __future__ import annotations

from urllib.parse import ParseResult, parse_qs, urlencode, urlparse, urlunparse

# Query string parameters that are purely for tracking and can be dropped
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
    }
)


def normalize_url(url: str) -> str:
    """Normalise a URL for consistent comparison and deduplication.

    Steps:
    1. Parse the URL.
    2. Lower-case the scheme and host.
    3. Remove default ports (80 for http, 443 for https).
    4. Remove trailing slash from path only if there is no path component.
    5. Remove tracking query parameters.
    6. Sort remaining query parameters for determinism.
    7. Drop empty fragment.

    Args:
        url: Raw URL string.

    Returns:
        Normalised URL string.
    """
    parsed: ParseResult = urlparse(url.strip())

    scheme = parsed.scheme.lower()
    netloc = _normalize_netloc(parsed.netloc, scheme)
    path = parsed.path or "/"
    query = _normalize_query(parsed.query)
    fragment = ""  # Drop fragments

    return urlunparse((scheme, netloc, path, "", query, fragment))


def _normalize_netloc(netloc: str, scheme: str) -> str:
    """Lower-case host and remove default port."""
    netloc = netloc.lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    return netloc


def _normalize_query(query: str) -> str:
    """Remove tracking parameters and sort remaining query parameters."""
    if not query:
        return ""
    params = parse_qs(query, keep_blank_values=False)
    filtered = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
    if not filtered:
        return ""
    return urlencode(sorted(filtered.items()), doseq=True)


def is_valid_http_url(url: str) -> bool:
    """Return True if the string is a valid http or https URL.

    Args:
        url: String to validate.

    Returns:
        ``True`` if ``url`` has a valid http/https scheme and a non-empty host.
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

#: British-spelling alias for :func:`normalize_url`.
normalise_url = normalize_url

#: Shorter alias for :func:`is_valid_http_url`.
is_valid_url = is_valid_http_url
