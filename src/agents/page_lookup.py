"""
Page Lookup Agent
Checks speaker profiles in Supabase for relevant figure information.
Uses an LLM to determine if the profile can answer the query directly.
If yes, returns the answer. If not, passes through to downstream agents.
"""

import os
import re
import json
import psycopg2
from dotenv import load_dotenv
from pathlib import Path
from langchain_openai import ChatOpenAI

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip('"')

llm = ChatOpenAI(
    model=os.environ.get("GPT_MODEL", "RPRTHPB-gpt-5-mini"),
    base_url=os.environ.get("BASE_URL", "https://api.llmod.ai/v1"),
    api_key=os.environ.get("OPENAI_API_KEY"),
    temperature=1,
    max_tokens=1500,
)

SPEAKERS = {
    "donald trump": "donald_trump",
    "trump": "donald_trump",
    "hillary clinton": "hillary_clinton",
    "clinton": "hillary_clinton",
    "barack obama": "barack_obama",
    "obama": "barack_obama",
    "bill gates": "bill_gates",
    "gates": "bill_gates",
    "elon musk": "elon_musk",
    "musk": "elon_musk",
    "mark zuckerberg": "mark_zuckerberg",
    "zuckerberg": "mark_zuckerberg",
    "kamala harris": "kamala_harris",
    "harris": "kamala_harris",
    "joe biden": "joe_biden",
    "biden": "joe_biden",
}

_SPEAKER_RE = re.compile(
    "|".join(re.escape(s) for s in sorted(SPEAKERS.keys(), key=len, reverse=True)),
    re.IGNORECASE,
)

PAGE_LOOKUP_PROMPT = """You are a political intelligence assistant. A user asked:

"{query}"

Below is the profile we have on file for this figure. Determine if this profile contains enough information to DIRECTLY and SPECIFICALLY answer the user's question.

Profile:
---
{profile_text}
---

Rules:
- If the profile contains a SPECIFIC, RELEVANT answer to the question, respond with a JSON object: {{"can_answer": true, "answer": "your comprehensive answer based on the profile data"}}
- If the profile does NOT contain specific information about the topic asked, respond with: {{"can_answer": false, "reason": "brief explanation of what's missing"}}
- Do NOT make up information. Only use what's in the profile.
- Do NOT give a generic answer. The answer must be specific to the question asked.
- Be strict: if the profile only tangentially relates to the question, return can_answer=false.

Respond ONLY with valid JSON."""


def _identify_speaker(query: str) -> str | None:
    match = _SPEAKER_RE.search(query)
    if match:
        return SPEAKERS[match.group().lower()]
    return None


def _fetch_profile(speaker_id: str) -> dict | None:
    try:
        conn = psycopg2.connect(SUPABASE_URL, connect_timeout=5)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT profile FROM speaker_profiles WHERE speaker_id = %s",
                (speaker_id,),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            return row[0] if isinstance(row[0], dict) else json.loads(row[0])
    except Exception:
        pass
    return None


def _profile_to_text(profile: dict) -> str:
    """Convert profile dict to a readable text for the LLM."""
    parts = []
    name = profile.get("name", "")
    bio = profile.get("bio", {})

    parts.append(f"Name: {name}")
    parts.append(f"Role: {bio.get('current_role', '')}")
    parts.append(f"Party: {bio.get('party', '')}")

    topics = profile.get("notable_topics", [])
    if topics:
        parts.append("\nNotable Topics:")
        for t in topics:
            parts.append(f"\n- {t.get('topic', '')} [{t.get('category', '')}]")
            parts.append(f"  Stance: {t.get('stance', '')}")
            if t.get("key_statements"):
                for stmt in t["key_statements"]:
                    parts.append(f"  Quote: {stmt}")
            if t.get("evolution"):
                parts.append(f"  Evolution: {t['evolution']}")
            if t.get("controversies"):
                parts.append(f"  Controversies: {t['controversies']}")

    controversies = profile.get("controversies", [])
    if controversies:
        parts.append("\nControversies:")
        for c in controversies:
            parts.append(f"- {c.get('title', '')} ({c.get('year', '')}): {c.get('description', '')}")

    relationships = profile.get("relationships", {})
    if relationships.get("relationship_context"):
        parts.append(f"\nRelationships: {relationships['relationship_context']}")

    return "\n".join(parts)


def lookup_page(query: str, on_token=None) -> dict:
    """
    Search speaker_profiles in Supabase and use LLM to check
    if the profile can answer the query directly.

    Returns:
        dict: {"found": bool, "content": str | None, "figure": str | None}
    """
    speaker_id = _identify_speaker(query)
    if not speaker_id:
        return {"found": False, "content": None, "figure": None}

    profile = _fetch_profile(speaker_id)
    if not profile:
        return {"found": False, "content": None, "figure": speaker_id}

    profile_text = _profile_to_text(profile)

    # Ask LLM if the profile can answer the query
    prompt = PAGE_LOOKUP_PROMPT.format(query=query, profile_text=profile_text[:4000])

    try:
        if on_token:
            content = ""
            for chunk in llm.stream(prompt):
                token = chunk.content or ""
                content += token
                on_token(token)
            content = content.strip()
        else:
            response = llm.invoke(prompt)
            content = response.content.strip()

        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        result = json.loads(content)

        if result.get("can_answer"):
            return {
                "found": True,
                "content": result["answer"],
                "figure": speaker_id,
            }
        else:
            return {
                "found": False,
                "content": None,
                "figure": speaker_id,
            }

    except Exception:
        return {"found": False, "content": None, "figure": speaker_id}
