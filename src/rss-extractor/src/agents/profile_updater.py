"""
agents.profile_updater
======================
LLM-powered speaker profile updater for the RSS ingestion pipeline.

After new articles are ingested, this module:

1. Groups articles by the politicians they mention.
2. For each politician, fetches their current profile from the Supabase
   ``speaker_profiles`` table.
3. Calls an LLM to detect any new substantive information in the articles
   (bio, roles, policy positions, controversies, relationships, etc.).
4. Merges new information into the existing profile.
5. Upserts the merged profile back to Supabase.

Profile schema
--------------
The profile JSON matches the schema consumed by the ``SpeakerProfile`` React
component in ``frontend/src/components/SpeakerProfile.jsx``.

Usage
-----
Collect articles grouped by politician during Stage 3 of the pipeline, then
call :func:`update_speaker_profiles` after the Supabase article push::

    from src.agents.profile_updater import (
        ArticleForProfile,
        update_speaker_profiles,
    )

    articles_by_politician: dict[str, tuple[str, list[ArticleForProfile]]] = {
        "donald-trump": ("Donald Trump", [ArticleForProfile(...)]),
    }
    result = update_speaker_profiles(
        articles_by_politician=articles_by_politician,
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_key=os.environ["SUPABASE_KEY"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        gpt_model=os.environ.get("GPT_MODEL", "gpt-4o-mini"),
    )
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default profile schema (mirrors SpeakerProfile.jsx)
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE_SCHEMA: dict[str, Any] = {
    "name": "",
    "bio": {
        "full_name": "",
        "born": "",
        "party": "",
        "current_role": "",
        "net_worth_estimate": "",
        "previous_roles": [],
        "education": [],
    },
    "notable_topics": [
        {
            "topic": "",
            "category": "",
            "stance": "",
            "key_statements": [],
            "evolution": "",
            "controversies": "",
        }
    ],
    "timeline_highlights": [{"year": "", "event": "", "significance": ""}],
    "controversies": [
        {"title": "", "year": "", "description": "", "outcome": "", "impact": ""}
    ],
    "relationships": {
        "allies": [],
        "opponents": [],
        "co_mentioned_figures": {},
        "relationship_context": "",
    },
    "public_perception": {
        "approval_trend": "",
        "base_support": "",
        "opposition": "",
        "key_narratives": [],
    },
    "media_profile": {
        "coverage_volume": "",
        "top_covering_states": {},
        "media_narrative": "",
        "sentiment_trend": "",
    },
    "dataset_insights": {
        "total_articles": 0,
        "date_range": "",
        "top_title_keywords": {},
        "geographic_focus": "",
    },
}

# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_PROFILE_UPDATE_PROMPT = """\
You are a political intelligence analyst updating a speaker profile database.

Politician: {politician_name}

Current profile (empty object if no profile exists yet):
---
{profile_json}
---

Newly ingested news articles about this politician:
---
{articles_text}
---

Your task:
1. Review the new articles for SUBSTANTIVE new information about {politician_name}
   that is NOT already reflected in the current profile.
2. Substantive information includes: new roles or titles, policy position changes,
   new controversies or legal developments, new biographical facts, notable
   statements, or significant relationship changes.
3. If you find substantive new information, return a complete updated profile that
   merges the new information into the existing profile while preserving all
   existing data.
4. If there is nothing substantively new beyond what the profile already contains,
   return {{"updated": false}}.

The profile must follow this schema:
{schema}

Respond ONLY with valid JSON in one of these two formats — no markdown fences,
no explanation:
- No update needed : {{"updated": false}}
- Update required  : {{"updated": true, "profile": <complete updated profile JSON>}}
"""


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass
class ArticleForProfile:
    """Lightweight article record used for profile and news analysis.

    Attributes:
        doc_id: Unique article identifier (SHA-256 fingerprint).
        title: Article headline.
        body: Cleaned article body text.
        date: Publication date (ISO 8601 string) or ``None``.
        link: Canonical article URL.
    """

    doc_id: str
    title: str
    body: str
    date: str | None
    link: str


@dataclass
class ProfileUpdateResult:
    """Summary of a :func:`update_speaker_profiles` run.

    Attributes:
        politicians_processed: Number of politicians whose articles were analysed.
        profiles_updated: Number of profiles where the LLM detected substantive new
            information and a full profile upsert was performed.
        datasets_only_updated: Number of profiles where the LLM found no new
            substantive information, but ``dataset_insights`` (article count,
            date range) was still updated in Supabase.
        profiles_skipped: Number of politicians where the LLM found no new
            information or who had no articles.
        errors: Number of politicians that encountered an error during processing.
    """

    politicians_processed: int = 0
    profiles_updated: int = 0
    datasets_only_updated: int = 0
    profiles_skipped: int = 0
    errors: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _update_dataset_insights(
    profile: dict[str, Any],
    articles: list[ArticleForProfile],
) -> dict[str, Any]:
    """Return a deep copy of *profile* with ``dataset_insights`` refreshed.

    Increments ``total_articles`` by the number of newly ingested articles and
    extends ``date_range`` to span the earliest and latest publication dates
    seen across both the existing dataset and the new batch.

    Articles without a parseable date are counted but do not affect the range.

    Args:
        profile: Existing profile dict (may be an empty dict for new speakers).
        articles: Newly ingested articles to incorporate.

    Returns:
        A new profile dict with refreshed ``dataset_insights``.
    """
    updated: dict[str, Any] = copy.deepcopy(profile)
    if not isinstance(updated.get("dataset_insights"), dict):
        updated["dataset_insights"] = {
            "total_articles": 0,
            "date_range": "",
            "top_title_keywords": {},
            "geographic_focus": "",
        }

    di = updated["dataset_insights"]
    di["total_articles"] = int(di.get("total_articles") or 0) + len(articles)

    article_dates = sorted(a.date for a in articles if a.date)
    if article_dates:
        new_min, new_max = article_dates[0], article_dates[-1]
        existing_range = str(di.get("date_range") or "")
        sep = " – "
        if sep in existing_range:
            parts = existing_range.split(sep, 1)
            ex_min, ex_max = parts[0].strip(), parts[1].strip()
            final_min = min(ex_min, new_min) if ex_min else new_min
            final_max = max(ex_max, new_max) if ex_max else new_max
        else:
            existing = existing_range.strip()
            final_min = min(existing, new_min) if existing else new_min
            final_max = max(existing, new_max) if existing else new_max
        di["date_range"] = f"{final_min}{sep}{final_max}"

    return updated


def _normalize_speaker_id(politician_id: str) -> str:
    """Normalize a pipeline politician ID to the ``speaker_profiles`` key format.

    Replaces hyphens with underscores so that ``"donald-trump"`` becomes
    ``"donald_trump"``, matching the IDs used in the Supabase table.

    Args:
        politician_id: Politician ID from ``config/politicians.yaml``.

    Returns:
        Normalized speaker ID string.
    """
    return politician_id.replace("-", "_")


def _fetch_profile(
    client: Any,
    speaker_id: str,
    profiles_table: str,
) -> dict[str, Any] | None:
    """Fetch an existing speaker profile from Supabase.

    Args:
        client: Initialised Supabase Python client.
        speaker_id: Speaker ID to look up in the ``speaker_profiles`` table.
        profiles_table: Name of the Supabase table storing speaker profiles.

    Returns:
        Profile dict if a matching row is found, otherwise ``None``.
    """
    try:
        response = (
            client.table(profiles_table)
            .select("profile")
            .eq("speaker_id", speaker_id)
            .execute()
        )
        rows = response.data or []
        if rows:
            raw = rows[0]["profile"]
            return raw if isinstance(raw, dict) else json.loads(raw)
    except Exception:
        logger.exception(
            "Failed to fetch profile for speaker_id=%s.", speaker_id
        )
    return None


def _upsert_profile(
    client: Any,
    speaker_id: str,
    name: str,
    profile: dict[str, Any],
    profiles_table: str,
) -> None:
    """Upsert a speaker profile to Supabase.

    Uses ``on_conflict="speaker_id"`` so the row is inserted on first run and
    updated on subsequent runs.

    The ``name``, ``party``, and ``current_role`` columns are sent on every
    upsert so that the dedicated table columns stay in sync with the profile
    JSON.  ``name`` is NOT NULL; ``party`` and ``current_role`` are nullable
    and are omitted from the payload when absent from the profile.

    Args:
        client: Initialised Supabase Python client.
        speaker_id: Speaker ID used as the upsert key.
        name: Canonical display name of the politician (e.g. ``"Donald Trump"``).
        profile: Full profile dict to serialise and store.
        profiles_table: Name of the Supabase table storing speaker profiles.
    """
    bio: dict[str, Any] = profile.get("bio") or {}
    row: dict[str, Any] = {
        "speaker_id": speaker_id,
        "name": name,
        "profile": json.dumps(profile),
    }
    party = bio.get("party")
    if party:
        row["party"] = party
    current_role = bio.get("current_role")
    if current_role:
        row["current_role"] = current_role
    client.table(profiles_table).upsert(row, on_conflict="speaker_id").execute()


def build_articles_text(
    articles: list[ArticleForProfile],
    max_chars: int = 12_000,
) -> str:
    """Render a list of articles as plain text for an LLM prompt.

    Each article is formatted as a numbered block with its headline, date,
    URL and (truncated) body.  The total output is capped at *max_chars* to
    avoid exceeding context-window limits.

    Args:
        articles: Articles to render.
        max_chars: Maximum total character count for the rendered output.

    Returns:
        A multi-article text string ready for injection into an LLM prompt.
    """
    parts: list[str] = []
    chars_used = 0
    n = len(articles)
    for i, article in enumerate(articles, 1):
        header = (
            f"[{i}] {article.title}"
            f" ({article.date or 'no date'}) — {article.link}\n"
        )
        # Distribute the remaining character budget equally across remaining articles.
        remaining = n - i + 1
        body_budget = max(200, (max_chars - chars_used - len(header)) // remaining)
        body_excerpt = article.body[:body_budget]
        entry = header + body_excerpt + "\n"
        if chars_used + len(entry) > max_chars:
            break
        parts.append(entry)
        chars_used += len(entry)
    return "\n".join(parts)


def _call_llm_for_profile_update(
    llm: Any,
    politician_name: str,
    existing_profile: dict[str, Any] | None,
    articles: list[ArticleForProfile],
) -> dict[str, Any] | None:
    """Call the LLM to detect and return profile-worthy updates from new articles.

    Args:
        llm: A ``ChatOpenAI``-compatible LLM instance.
        politician_name: Canonical name of the politician being analysed.
        existing_profile: Current profile dict, or ``None`` if none exists yet.
        articles: Newly ingested articles to analyse.

    Returns:
        An updated profile dict if new substantive information was found, or
        ``None`` if the LLM determined no update is needed.
    """
    profile_json = (
        json.dumps(existing_profile, indent=2) if existing_profile else "{}"
    )
    articles_text = build_articles_text(articles)
    schema_json = json.dumps(_DEFAULT_PROFILE_SCHEMA, indent=2)

    prompt = _PROFILE_UPDATE_PROMPT.format(
        politician_name=politician_name,
        # Truncate very long existing profiles to stay within context limits.
        profile_json=profile_json[:4_000],
        articles_text=articles_text,
        schema=schema_json,
    )

    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        # Strip Markdown code fences if the LLM wraps the JSON.
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[: content.rfind("```")]
            content = content.strip()
        result: dict[str, Any] = json.loads(content)
        if result.get("updated") and isinstance(result.get("profile"), dict):
            return result["profile"]
    except json.JSONDecodeError as exc:
        logger.warning(
            "LLM returned malformed JSON for profile update of %s (char %d); "
            "falling back to dataset_insights-only update. Error: %s",
            politician_name,
            exc.pos,
            exc.msg,
        )
    except Exception:
        logger.exception(
            "LLM call failed during profile update for %s.", politician_name
        )
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_speaker_profiles(
    articles_by_politician: dict[str, tuple[str, list[ArticleForProfile]]],
    supabase_url: str,
    supabase_key: str,
    openai_api_key: str,
    base_url: str,
    gpt_model: str,
    profiles_table: str = "speaker_profiles",
    dry_run: bool = False,
    recent_news_by_politician: dict[str, list[dict[str, Any]]] | None = None,
) -> ProfileUpdateResult:
    """Update speaker profiles in Supabase based on newly ingested articles.

    For each politician with new articles, this function:

    1. Normalises the politician ID to the ``speaker_profiles`` key format.
    2. Fetches the existing profile from Supabase (``None`` if absent).
    3. **Always** refreshes ``dataset_insights`` (``total_articles``,
       ``date_range``) from the new batch — even when the LLM finds no
       substantive new information.
    4. Calls an LLM to determine whether the new articles contain substantive
       profile-worthy information (new roles, controversies, positions, etc.).
    5. Merges any ``recent_news`` items for this politician into the final
       profile under the ``recent_news`` key (replacing any previous value).
    6. Upserts the profile back to Supabase:
       - Full LLM-merged profile if substantive new info was found.
       - Dataset-insights-only update otherwise.
       Both paths always include the refreshed ``recent_news`` section.

    Args:
        articles_by_politician: Mapping of ``politician_id`` (from
            ``config/politicians.yaml``) to a tuple of
            ``(politician_name, articles_list)``.
        supabase_url: Supabase project URL (``SUPABASE_URL``).
        supabase_key: Supabase API key (``SUPABASE_KEY``).
        openai_api_key: OpenAI-compatible API key (``OPENAI_API_KEY``).
        base_url: LLM API base URL (e.g. ``https://api.openai.com/v1``).
        gpt_model: LLM model identifier (e.g. ``"gpt-4o-mini"``).
        profiles_table: Name of the Supabase table that stores speaker profiles.
            Defaults to ``"speaker_profiles"``.
        dry_run: When ``True``, all stages run (including LLM calls) but the
            final Supabase upsert is skipped.
        recent_news_by_politician: Optional mapping of ``politician_id`` to a
            list of serialised :class:`~recent_news_builder.RecentNewsItem`
            dicts (each with ``"point"`` and ``"article_refs"`` keys).  When
            provided and an entry exists for the current politician, the list
            is stored under the ``recent_news`` key in the profile before
            upsert, replacing any previously stored value.

    Returns:
        A :class:`ProfileUpdateResult` summarising counts of politicians
        processed, profiles updated/skipped, and errors encountered.

    Raises:
        RuntimeError: If the ``langchain-openai`` or ``supabase`` packages are
            not installed.
    """
    try:
        from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]
        from supabase import create_client  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            f"Required package not installed: {exc}. "
            "Install 'langchain-openai' and 'supabase'."
        ) from exc

    llm = ChatOpenAI(
        model=gpt_model,
        base_url=base_url,
        api_key=openai_api_key,
        temperature=0,
        max_tokens=2_000,
    )
    client = create_client(supabase_url, supabase_key)
    result = ProfileUpdateResult()

    for politician_id, (politician_name, articles) in articles_by_politician.items():
        if not articles:
            continue

        result.politicians_processed += 1
        speaker_id = _normalize_speaker_id(politician_id)

        logger.info(
            "Analysing %d article(s) for profile update: %s (speaker_id=%s).",
            len(articles),
            politician_name,
            speaker_id,
        )

        existing_profile = _fetch_profile(client, speaker_id, profiles_table)

        # Always refresh dataset_insights regardless of what the LLM decides.
        profile_with_counts = _update_dataset_insights(
            existing_profile or dict(_DEFAULT_PROFILE_SCHEMA),
            articles,
        )

        updated_profile = _call_llm_for_profile_update(
            llm, politician_name, existing_profile, articles
        )

        if updated_profile is not None:
            # Full LLM update — carry over the freshly computed dataset_insights.
            updated_profile["dataset_insights"] = profile_with_counts[
                "dataset_insights"
            ]
            final_profile = updated_profile
            result.profiles_updated += 1
            logger.info("New substantive information found for %s.", politician_name)
        else:
            # No new substantive info — still upsert the refreshed dataset_insights.
            final_profile = profile_with_counts
            result.datasets_only_updated += 1
            result.profiles_skipped += 1
            logger.info(
                "No new substantive profile information for %s; "
                "updating dataset_insights only.",
                politician_name,
            )

        # Merge recent_news into the profile so it is stored inside the
        # speaker_profiles.profile JSON column in Supabase.
        if recent_news_by_politician is not None:
            news_items = recent_news_by_politician.get(politician_id)
            if news_items is not None:
                final_profile["recent_news"] = news_items
                logger.info(
                    "Merged %d recent-news item(s) into profile for %s.",
                    len(news_items),
                    politician_name,
                )

        if dry_run:
            logger.info(
                "DRY RUN: Would upsert profile for %s (speaker_id=%s).",
                politician_name,
                speaker_id,
            )
        else:
            try:
                _upsert_profile(client, speaker_id, politician_name, final_profile, profiles_table)
                logger.info("Upserted profile for %s.", politician_name)
            except Exception:
                logger.exception(
                    "Failed to upsert profile for %s.", politician_name
                )
                # Roll back the increment that was already applied above.
                if updated_profile is not None:
                    result.profiles_updated -= 1
                else:
                    result.datasets_only_updated -= 1
                result.errors += 1

    return result
