"""
validation.topic_normalization
================================
Surface-form topic mapping to the controlled vocabulary.

Design principles
-----------------
* Deterministic — same input always produces the same output.
* All known topic values from the controlled vocabulary pass through unchanged.
* Surface forms that clearly map to a canonical topic are normalized.
* Ambiguous or out-of-scope topics are mapped to ``"other"`` (with a warning)
  rather than rejected, so that broadly valid events are not discarded for a
  topic that doesn't fit neatly.
* Unknown topics that cannot be mapped at all are also mapped to ``"other"``
  with a specific warning so callers can decide how to handle them.

Extending
---------
Add entries to ``_SURFACE_MAP``.  The values must be valid canonical topic
strings from ``contracts.vocab.TOPIC_VALUES``.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.vocab import TOPIC_VALUES


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicResolution:
    """Result of normalising a raw topic string.

    Attributes
    ----------
    canonical:
        The resolved canonical topic from the controlled vocabulary.
    was_normalized:
        ``True`` iff the input was mapped from a surface form to a different
        canonical value.
    mapped_to_other:
        ``True`` iff the topic was unknown and mapped to ``"other"``.
    original:
        The original input string (before any normalization).
    """

    canonical: str
    was_normalized: bool
    mapped_to_other: bool
    original: str


# ---------------------------------------------------------------------------
# Surface-form map
# ---------------------------------------------------------------------------
# Keys are lower-cased surface forms.
# Values are canonical topic strings (must be in TOPIC_VALUES).

_SURFACE_MAP: dict[str, str] = {
    # --- immigration ---
    "immigration": "immigration",
    "border": "immigration",
    "border security": "immigration",
    "border wall": "immigration",
    "asylum": "immigration",
    "deportation": "immigration",
    "undocumented immigrants": "immigration",
    "illegal immigration": "immigration",
    "refugees": "immigration",
    "migrant": "immigration",
    "migrants": "immigration",
    # --- trade ---
    "trade": "trade",
    "tariffs": "trade",
    "tariff": "trade",
    "trade policy": "trade",
    "trade war": "trade",
    "trade deal": "trade",
    "trade agreement": "trade",
    "nafta": "trade",
    "usmca": "trade",
    "chinese imports": "trade",
    "trade deficit": "trade",
    "protectionism": "trade",
    "free trade": "trade",
    "import duties": "trade",
    "export controls": "trade",
    # --- foreign_policy ---
    "foreign policy": "foreign_policy",
    "foreign_policy": "foreign_policy",
    "nato": "foreign_policy",
    "ukraine": "foreign_policy",
    "israel": "foreign_policy",
    "middle east": "foreign_policy",
    "china relations": "foreign_policy",
    "russia": "foreign_policy",
    "diplomacy": "foreign_policy",
    "international relations": "foreign_policy",
    "military aid": "foreign_policy",
    "sanctions": "foreign_policy",
    # --- abortion ---
    "abortion": "abortion",
    "reproductive rights": "abortion",
    "roe v. wade": "abortion",
    "roe vs wade": "abortion",
    "pro-choice": "abortion",
    "pro-life": "abortion",
    "pro choice": "abortion",
    "pro life": "abortion",
    # --- healthcare ---
    "healthcare": "healthcare",
    "health care": "healthcare",
    "medicare": "healthcare",
    "medicaid": "healthcare",
    "obamacare": "healthcare",
    "aca": "healthcare",
    "affordable care act": "healthcare",
    "prescription drugs": "healthcare",
    "drug prices": "healthcare",
    "public option": "healthcare",
    "insurance": "healthcare",
    # --- economy ---
    "economy": "economy",
    "economic policy": "economy",
    "jobs": "economy",
    "employment": "economy",
    "unemployment": "economy",
    "inflation": "economy",
    "gdp": "economy",
    "economic growth": "economy",
    "minimum wage": "economy",
    "wages": "economy",
    "labor": "economy",
    "labour": "economy",
    "deficit": "economy",
    "debt": "economy",
    "national debt": "economy",
    "spending": "economy",
    "stimulus": "economy",
    # --- taxation ---
    "taxation": "taxation",
    "taxes": "taxation",
    "tax": "taxation",
    "tax cuts": "taxation",
    "tax policy": "taxation",
    "corporate tax": "taxation",
    "income tax": "taxation",
    "wealth tax": "taxation",
    "irs": "taxation",
    # --- crime ---
    "crime": "crime",
    "criminal justice": "crime",
    "law enforcement": "crime",
    "police": "crime",
    "policing": "crime",
    "gun control": "crime",
    "gun violence": "crime",
    "guns": "crime",
    "second amendment": "crime",
    "drugs": "crime",
    "opioid": "crime",
    # --- climate ---
    "climate": "climate",
    "climate change": "climate",
    "global warming": "climate",
    "environment": "climate",
    "environmental policy": "climate",
    "paris agreement": "climate",
    "paris accord": "climate",
    "greenhouse gas": "climate",
    "carbon emissions": "climate",
    "clean energy": "climate",
    # --- energy ---
    "energy": "energy",
    "energy policy": "energy",
    "oil": "energy",
    "fossil fuels": "energy",
    "natural gas": "energy",
    "renewable energy": "energy",
    "nuclear energy": "energy",
    "fracking": "energy",
    "keystone pipeline": "energy",
    "pipeline": "energy",
    # --- elections ---
    "elections": "elections",
    "election": "elections",
    "voting": "elections",
    "voter id": "elections",
    "voter fraud": "elections",
    "election integrity": "elections",
    "electoral college": "elections",
    "campaign finance": "elections",
    "redistricting": "elections",
    "gerrymandering": "elections",
    # --- democracy ---
    "democracy": "democracy",
    "democratic norms": "democracy",
    "rule of law": "democracy",
    "separation of powers": "democracy",
    "constitution": "democracy",
    "impeachment": "democracy",
    "january 6": "democracy",
    "jan. 6": "democracy",
    "jan 6": "democracy",
    # --- other ---
    "other": "other",
    # housing (out of main vocabulary → other)
    "housing": "other",
    "affordable housing": "other",
    "education": "other",
    "infrastructure": "other",
    "social security": "other",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_topic(raw: str | None) -> TopicResolution:
    """Normalize *raw* topic to a canonical vocabulary value.

    Parameters
    ----------
    raw:
        The topic string as extracted by the LLM.  May be ``None``.

    Returns
    -------
    TopicResolution
        Always returns a result.  Check ``was_normalized`` and
        ``mapped_to_other`` for normalization details.

    Examples
    --------
    >>> normalize_topic("tariffs")
    TopicResolution(canonical='trade', was_normalized=True, mapped_to_other=False, original='tariffs')
    >>> normalize_topic("trade")
    TopicResolution(canonical='trade', was_normalized=False, mapped_to_other=False, original='trade')
    >>> normalize_topic("housing")
    TopicResolution(canonical='other', was_normalized=True, mapped_to_other=True, original='housing')
    >>> normalize_topic("economy")
    TopicResolution(canonical='economy', was_normalized=False, mapped_to_other=False, original='economy')
    """
    if not raw:
        return TopicResolution(
            canonical="other",
            was_normalized=True,
            mapped_to_other=True,
            original=raw or "",
        )

    stripped = raw.strip()

    # Already a valid canonical value — pass through unchanged
    if stripped in TOPIC_VALUES:
        return TopicResolution(
            canonical=stripped,
            was_normalized=False,
            mapped_to_other=False,
            original=stripped,
        )

    # Try surface-form map (case-insensitive)
    lower = stripped.lower()
    canonical = _SURFACE_MAP.get(lower)

    if canonical is not None:
        was_normalized = canonical != stripped
        # mapped_to_other is True only when the original topic was genuinely
        # unknown (not just a differently-cased canonical value like "Other")
        mapped_to_other = canonical == "other" and stripped.lower() not in TOPIC_VALUES
        return TopicResolution(
            canonical=canonical,
            was_normalized=was_normalized,
            mapped_to_other=mapped_to_other,
            original=stripped,
        )

    # Unknown: map to "other" with a note
    return TopicResolution(
        canonical="other",
        was_normalized=True,
        mapped_to_other=True,
        original=stripped,
    )
