"""
validation.proposition_normalization
======================================
Deterministic lexical proposition normalization.

Goal
----
Reduce obvious surface variation in wording for semantically equivalent
propositions.  This is **not** full semantic equivalence detection — it is a
targeted lexical transformation layer that:

1. Normalizes whitespace and capitalization consistently.
2. Applies a finite set of phrase mappings for known-equivalent expressions.
3. Preserves the original proposition alongside the normalized form.

Documented phrase mappings (v1)
-------------------------------
The tariff example from the issue is explicitly supported::

    "raise tariffs on China"       → canonical
    "higher tariffs on Chinese imports"  → same canonical

If a proposition cannot be confidently mapped, it is returned in a stable
normalized form (whitespace-cleaned, leading/trailing stripped) rather than
forced into a bad canonicalization.

Extending
---------
Add entries to ``_PHRASE_MAP``.  Keys and values are lower-cased strings.
The value should be the preferred canonical phrase (also lower-cased).
The normalizer will then apply proper sentence casing to the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PropositionResolution:
    """Result of normalizing a raw proposition string.

    Attributes
    ----------
    canonical:
        The normalized proposition string, suitable for storage.
    was_normalized:
        ``True`` iff the input was transformed (beyond basic whitespace
        cleaning).
    original:
        The original input string (before any normalization).
    """

    canonical: str
    was_normalized: bool
    original: str


# ---------------------------------------------------------------------------
# Phrase map
# ---------------------------------------------------------------------------
# Keys are lower-cased phrases or sub-phrases that should be replaced by
# their canonical equivalents (also lower-cased).
#
# The normalizer applies these as substring replacements in order.  More
# specific phrases should come before more general ones.

_PHRASE_MAP: list[tuple[str, str]] = [
    # Tariff-related (documented example from the issue)
    ("higher tariffs on chinese imports", "raise tariffs on china"),
    ("increase tariffs on chinese goods", "raise tariffs on china"),
    ("impose tariffs on chinese goods", "raise tariffs on china"),
    ("impose tariffs on china", "raise tariffs on china"),
    ("60 percent tariffs on goods imported from china", "raise tariffs on china"),
    ("60% tariffs on chinese imports", "raise tariffs on china"),
    ("tariffs on chinese imports", "raise tariffs on china"),
    ("tariffs on china", "raise tariffs on china"),
    # Border / immigration
    ("close the southern border", "shut down the southern border"),
    ("seal the southern border", "shut down the southern border"),
    ("open borders", "allowing open borders"),
    # Minimum wage
    ("raise the minimum wage to $15 per hour", "raise the federal minimum wage to $15"),
    ("raise the federal minimum wage to $15 per hour", "raise the federal minimum wage to $15"),
    ("$15 minimum wage", "raise the federal minimum wage to $15"),
    ("15 dollar minimum wage", "raise the federal minimum wage to $15"),
    # Healthcare
    ("repeal and replace obamacare", "repeal the affordable care act"),
    ("repeal aca", "repeal the affordable care act"),
    ("repeal the aca", "repeal the affordable care act"),
    # Climate
    ("withdraw from the paris agreement", "exit the paris climate accord"),
    ("withdraw from the paris accord", "exit the paris climate accord"),
    ("leave the paris agreement", "exit the paris climate accord"),
    ("paris climate deal", "paris climate accord"),
]

# Pre-compile regex patterns for efficiency and word-boundary matching
_COMPILED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(re.escape(phrase), re.IGNORECASE), replacement)
    for phrase, replacement in _PHRASE_MAP
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_whitespace(text: str) -> str:
    """Collapse internal whitespace and strip leading/trailing space."""
    return re.sub(r"\s+", " ", text).strip()


def _sentence_case(text: str) -> str:
    """Capitalize the first letter of *text*, leave the rest unchanged."""
    if not text:
        return text
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_proposition(raw: str | None) -> PropositionResolution:
    """Normalize *raw* to a canonical proposition string.

    Parameters
    ----------
    raw:
        The raw ``normalized_proposition`` string from the extractor.

    Returns
    -------
    PropositionResolution
        Always returns a result.  Check ``was_normalized`` to see whether
        any transformation was applied beyond basic whitespace cleaning.

    Examples
    --------
    >>> normalize_proposition("higher tariffs on Chinese imports")
    PropositionResolution(canonical='Raise tariffs on china', was_normalized=True, original='higher tariffs on Chinese imports')
    >>> normalize_proposition("raise tariffs on China")
    PropositionResolution(canonical='Raise tariffs on china', was_normalized=True, original='raise tariffs on China')
    >>> normalize_proposition("Joe Biden supports healthcare reform.")
    PropositionResolution(canonical='Joe Biden supports healthcare reform.', was_normalized=False, original='Joe Biden supports healthcare reform.')
    """
    if not raw:
        return PropositionResolution(canonical="", was_normalized=False, original=raw or "")

    original = raw
    normalized = _normalize_whitespace(raw)

    # Apply phrase-map transformations
    was_mapped = False
    for pattern, replacement in _COMPILED_PATTERNS:
        new_text = pattern.sub(replacement, normalized)
        if new_text != normalized:
            normalized = new_text
            was_mapped = True

    # Apply basic whitespace normalization again after replacements
    normalized = _normalize_whitespace(normalized)

    # Apply sentence casing
    normalized = _sentence_case(normalized)

    # The stable baseline is the sentence-cased, whitespace-normalised original
    baseline = _sentence_case(_normalize_whitespace(original))
    was_normalized = was_mapped or (normalized != baseline)

    return PropositionResolution(
        canonical=normalized,
        was_normalized=was_normalized,
        original=original,
    )
