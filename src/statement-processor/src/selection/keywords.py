"""
selection.keywords
==================
Configurable keyword lists and politician alias registry for the
deterministic article selection layer.

All constants are module-level so they are easy to inspect, override in
tests, or extend without touching core logic.

Design notes
------------
- Every list is a ``frozenset`` of lower-cased strings for O(1) membership
  checks and to guarantee no accidental duplicates.
- ``POLITICIAN_ALIASES`` maps a canonical name (as used in the output) to a
  ``frozenset`` of lower-cased name forms that may appear in article text or
  ``speakers_mentioned``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Reporting / stance-bearing verbs (strong positive signal in title)
# ---------------------------------------------------------------------------

REPORTING_VERBS: frozenset[str] = frozenset(
    {
        "said",
        "says",
        "vows",
        "vowed",
        "promises",
        "promised",
        "warns",
        "warned",
        "attacks",
        "attacked",
        "backs",
        "backed",
        "opposes",
        "opposed",
        "supports",
        "supported",
        "plans",
        "planned",
        "signs",
        "signed",
        "announces",
        "announced",
        "calls",
        "called",
        "slams",
        "slammed",
        "pushes",
        "pushed",
        "pledges",
        "pledged",
        "urges",
        "urged",
        "demands",
        "demanded",
        "blasts",
        "blasted",
        "criticizes",
        "criticized",
        "criticises",
        "criticised",
        "defends",
        "defended",
        "rejects",
        "rejected",
        "reverses",
        "reversed",
        "flip-flops",
        "contradicts",
        "contradicted",
        "doubles down",
        "walks back",
        "walked back",
        "proposes",
        "proposed",
        "introduces",
        "introduced",
        "endorses",
        "endorsed",
        "condemns",
        "condemned",
        "decries",
        "decried",
        "accuses",
        "accused",
        "claims",
        "claimed",
        "argues",
        "argued",
        "insists",
        "insisted",
        "denies",
        "denied",
        "admits",
        "admitted",
    }
)

# ---------------------------------------------------------------------------
# Quote markers — presence suggests direct speech near politician name
# ---------------------------------------------------------------------------

QUOTE_MARKERS: frozenset[str] = frozenset(
    {
        '"',
        "\u201c",  # left double quotation mark "
        "\u201d",  # right double quotation mark "
        "\u2018",  # left single quotation mark '
        "\u2019",  # right single quotation mark '
        "said that",
        "stated that",
        "declared that",
        "confirmed that",
        "revealed that",
    }
)

# ---------------------------------------------------------------------------
# Policy topic keywords (broad positive signal in title or text)
# ---------------------------------------------------------------------------

POLICY_TOPICS: frozenset[str] = frozenset(
    {
        # Domestic policy
        "immigration",
        "border",
        "healthcare",
        "health care",
        "medicare",
        "medicaid",
        "obamacare",
        "affordable care act",
        "abortion",
        "gun control",
        "gun rights",
        "second amendment",
        "taxes",
        "tax cut",
        "tax reform",
        "infrastructure",
        "climate change",
        "climate crisis",
        "green new deal",
        "clean energy",
        "renewable energy",
        "minimum wage",
        "student debt",
        "student loans",
        "social security",
        "drug prices",
        "prescription drugs",
        "crime",
        "policing",
        "law enforcement",
        "criminal justice",
        "voting rights",
        "election integrity",
        "budget",
        "deficit",
        "spending",
        "trade",
        "tariff",
        "tariffs",
        "sanctions",
        # Foreign policy
        "ukraine",
        "russia",
        "china",
        "nato",
        "iran",
        "north korea",
        "israel",
        "gaza",
        "middle east",
        "afghanistan",
        "iraq",
        "troops",
        "military",
        "foreign aid",
        "diplomacy",
        "allies",
        # Economy
        "economy",
        "inflation",
        "recession",
        "jobs",
        "unemployment",
        "gdp",
        "wall street",
        "federal reserve",
        "interest rates",
        "debt ceiling",
        # Other high-signal terms
        "executive order",
        "veto",
        "legislation",
        "bill",
        "amendment",
        "supreme court",
        "constitution",
        "impeachment",
    }
)

# ---------------------------------------------------------------------------
# Negative / low-priority signals
# ---------------------------------------------------------------------------

LOW_PRIORITY_SIGNALS: frozenset[str] = frozenset(
    {
        "poll",
        "polling",
        "approval rating",
        "favorability",
        "horse race",
        "horse-race",
        "electability",
        "fundraising",
        "campaign donations",
        "endorsement race",
        "primary race",
        "general election odds",
        "betting odds",
        "prediction market",
        "who will win",
        "chances of winning",
        "celebrity",
        "entertainment",
        "sports",
        "obituary",
        "weather",
        "horoscope",
    }
)

# Minimum article text length (in characters) below which the article is
# considered too short to contain meaningful stance content.
MIN_TEXT_LENGTH: int = 150

# ---------------------------------------------------------------------------
# Politician alias registry
# ---------------------------------------------------------------------------
# Maps a canonical politician name (used in selection output) to a frozenset
# of lower-cased name forms that may appear in news text or
# speakers_mentioned.  Add new politicians by extending this dict.

POLITICIAN_ALIASES: dict[str, frozenset[str]] = {
    "Trump": frozenset(
        {
            "trump",
            "donald trump",
            "president trump",
            "former president trump",
            "trump administration",
            "trump's",
        }
    ),
    "Biden": frozenset(
        {
            "biden",
            "joe biden",
            "president biden",
            "former president biden",
            "vice president biden",
            "biden administration",
            "biden's",
        }
    ),
}
