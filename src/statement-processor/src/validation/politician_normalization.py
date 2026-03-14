"""
validation.politician_normalization
=====================================
Canonical politician name resolution from aliases.

Design principles
-----------------
* Deterministic — same input always produces the same output.
* Extend by adding entries to ``_ALIAS_MAP`` only; no logic changes needed.
* Returns a ``PoliticianResolution`` object so callers know whether the name
  was recognised, normalized, or completely unknown.
* Unknown politicians are not silently accepted as canonical — a warning is
  emitted so downstream code can decide whether to proceed.

Supported politicians (v1)
--------------------------
The initial set covers the major US political figures most likely to appear
in the first version of the pipeline.  Each entry maps every known alias
(lower-cased) to a canonical name string.

Extending
---------
To add a new politician, add a new block to ``_ALIAS_MAP``::

    "new politician": {
        "new politician",
        "politician",
        "np",
        "rep. new politician",
    },

The dict key **must** be the canonical name exactly as stored.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PoliticianResolution:
    """Result of attempting to canonicalise a politician name.

    Attributes
    ----------
    canonical:
        The resolved canonical name, or the original (stripped) name if the
        politician was not recognised.
    was_normalized:
        ``True`` iff the input was an alias that was resolved to a different
        canonical name.
    is_known:
        ``True`` iff the politician appears in the alias map.
    original:
        The original input string (before any normalization).
    """

    canonical: str
    was_normalized: bool
    is_known: bool
    original: str


# ---------------------------------------------------------------------------
# Alias map
# ---------------------------------------------------------------------------
# Keys are *canonical* politician names.
# Values are frozensets of lower-cased aliases (including the canonical name
# itself, lowercased).
#
# When adding entries, be conservative: only add aliases that unambiguously
# refer to the politician and are likely to appear in extracted output.

_ALIAS_MAP: dict[str, frozenset[str]] = {
    "Donald Trump": frozenset(
        {
            "donald trump",
            "trump",
            "president trump",
            "former president trump",
            "former president donald trump",
            "mr. trump",
            "mr trump",
            "donald j. trump",
            "donald j trump",
            "45th president",
            "45",
        }
    ),
    "Joe Biden": frozenset(
        {
            "joe biden",
            "biden",
            "president biden",
            "former president biden",
            "former president joe biden",
            "mr. biden",
            "mr biden",
            "joseph biden",
            "joseph r. biden",
            "joseph r biden",
            "46th president",
            "46",
        }
    ),
    "Kamala Harris": frozenset(
        {
            "kamala harris",
            "harris",
            "vice president harris",
            "vp harris",
            "kamala",
            "kamala d. harris",
            "kamala d harris",
        }
    ),
    "Bernie Sanders": frozenset(
        {
            "bernie sanders",
            "sanders",
            "senator sanders",
            "sen. sanders",
            "sen sanders",
            "bernard sanders",
        }
    ),
    "Alexandria Ocasio-Cortez": frozenset(
        {
            "alexandria ocasio-cortez",
            "aoc",
            "ocasio-cortez",
            "rep. ocasio-cortez",
            "rep ocasio-cortez",
            "alexandria ocasio cortez",
        }
    ),
    "Nancy Pelosi": frozenset(
        {
            "nancy pelosi",
            "pelosi",
            "speaker pelosi",
            "former speaker pelosi",
        }
    ),
    "Mitch McConnell": frozenset(
        {
            "mitch mcconnell",
            "mcconnell",
            "senator mcconnell",
            "sen. mcconnell",
            "sen mcconnell",
            "minority leader mcconnell",
        }
    ),
    "Ron DeSantis": frozenset(
        {
            "ron desantis",
            "desantis",
            "governor desantis",
            "gov. desantis",
            "gov desantis",
        }
    ),
    "Nikki Haley": frozenset(
        {
            "nikki haley",
            "haley",
            "former governor haley",
            "ambassador haley",
        }
    ),
    "Ted Cruz": frozenset(
        {
            "ted cruz",
            "cruz",
            "senator cruz",
            "sen. cruz",
            "sen cruz",
        }
    ),
    "Marco Rubio": frozenset(
        {
            "marco rubio",
            "rubio",
            "senator rubio",
            "sen. rubio",
            "sen rubio",
        }
    ),
    "Elizabeth Warren": frozenset(
        {
            "elizabeth warren",
            "warren",
            "senator warren",
            "sen. warren",
            "sen warren",
        }
    ),
    "Chuck Schumer": frozenset(
        {
            "chuck schumer",
            "schumer",
            "senator schumer",
            "sen. schumer",
            "senate majority leader schumer",
            "majority leader schumer",
        }
    ),
    "Barack Obama": frozenset(
        {
            "barack obama",
            "obama",
            "president obama",
            "former president obama",
            "former president barack obama",
            "44th president",
        }
    ),
}

# Build the reverse look-up: lower-cased alias → canonical name.
# Validate at build time that no alias is shared across different politicians.
_LOOKUP: dict[str, str] = {}
_alias_conflicts: list[str] = []
for _canonical, _aliases in _ALIAS_MAP.items():
    for _alias in _aliases:
        if _alias in _LOOKUP and _LOOKUP[_alias] != _canonical:
            _alias_conflicts.append(
                f"Alias {_alias!r} is mapped to both {_LOOKUP[_alias]!r} and {_canonical!r}."
            )
        _LOOKUP[_alias] = _canonical
if _alias_conflicts:
    raise ValueError(
        "Duplicate aliases detected in politician alias map:\n"
        + "\n".join(_alias_conflicts)
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_politician(raw: str | None) -> PoliticianResolution:
    """Resolve *raw* to a canonical politician name.

    Parameters
    ----------
    raw:
        The politician name as extracted by the LLM.  May be ``None``.

    Returns
    -------
    PoliticianResolution
        Always returns a result.  Check ``is_known`` to determine whether the
        politician was recognised.

    Examples
    --------
    >>> resolve_politician("Trump")
    PoliticianResolution(canonical='Donald Trump', was_normalized=True, is_known=True, original='Trump')
    >>> resolve_politician("Joe Biden")
    PoliticianResolution(canonical='Joe Biden', was_normalized=False, is_known=True, original='Joe Biden')
    >>> resolve_politician("Unknown Person")
    PoliticianResolution(canonical='Unknown Person', was_normalized=False, is_known=False, original='Unknown Person')
    """
    if not raw:
        return PoliticianResolution(
            canonical="",
            was_normalized=False,
            is_known=False,
            original=raw or "",
        )

    stripped = raw.strip()
    lower = stripped.lower()

    canonical = _LOOKUP.get(lower)

    if canonical is None:
        # Not found: return original (stripped) name, mark as unknown
        return PoliticianResolution(
            canonical=stripped,
            was_normalized=False,
            is_known=False,
            original=stripped,
        )

    was_normalized = canonical != stripped
    return PoliticianResolution(
        canonical=canonical,
        was_normalized=was_normalized,
        is_known=True,
        original=stripped,
    )
