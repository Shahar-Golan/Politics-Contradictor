"""
extractor.cleaner
=================
Text cleaning and normalisation for extracted article bodies.

Removes common extraction artefacts such as excess whitespace, Unicode
noise, and boilerplate phrases. Returns clean, human-readable text.
"""

from __future__ import annotations

import re
import unicodedata


def clean_text(text: str) -> str:
    """Clean and normalise raw extracted article text.

    Steps applied:
    1. Normalise Unicode (NFC form).
    2. Replace non-breaking spaces and other whitespace variants.
    3. Collapse repeated blank lines.
    4. Strip leading/trailing whitespace from each paragraph.
    5. Strip leading/trailing whitespace from the whole result.

    Args:
        text: Raw extracted text from an article.

    Returns:
        Cleaned text suitable for downstream processing.
    """
    text = unicodedata.normalize("NFC", text)
    text = _replace_unicode_whitespace(text)
    text = _collapse_inline_whitespace(text)
    text = _collapse_blank_lines(text)
    text = _strip_paragraphs(text)
    return text.strip()


def _replace_unicode_whitespace(text: str) -> str:
    """Replace non-breaking and other special whitespace characters with ASCII equivalents."""
    # Replace non-breaking space (U+00A0) and related variants
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")   # zero-width space
    text = text.replace("\u200c", "")   # zero-width non-joiner
    text = text.replace("\ufeff", "")   # BOM
    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _collapse_inline_whitespace(text: str) -> str:
    """Collapse consecutive spaces and tabs on the same line to a single space."""
    return re.sub(r"[ \t]+", " ", text)


def _collapse_blank_lines(text: str) -> str:
    """Reduce runs of three or more blank lines to a single blank line."""
    return re.sub(r"\n{3,}", "\n\n", text)


def _strip_paragraphs(text: str) -> str:
    """Strip whitespace from the start and end of each paragraph."""
    paragraphs = text.split("\n\n")
    return "\n\n".join(p.strip() for p in paragraphs if p.strip())
