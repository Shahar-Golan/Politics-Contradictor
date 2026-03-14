"""
Router Agent
Classifies user queries and routes to the appropriate agent.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

llm = ChatOpenAI(
    model=os.environ.get("GPT_MODEL", "RPRTHPB-gpt-5-mini"),
    base_url=os.environ.get("BASE_URL", "https://api.llmod.ai/v1"),
    api_key=os.environ.get("OPENAI_API_KEY"),
    temperature=1,
    max_tokens=500,
)

ROUTER_PROMPT = """You are a query router for a political intelligence system.

You have access to two expert agents:
1. **tweet_agent** — Expert in politicians' direct statements, short takes, rivalry,
   back-and-forth exchanges, and personal opinions from social media (Twitter/X).
   Best for: "What did X say about Y?", "Did X and Y clash?", "X's reaction to..."

2. **news_agent** — Expert in detailed news coverage, comprehensive analysis,
   regional reporting, and in-depth articles from local US newspapers, radio, and TV.
   Best for: "How did news cover X?", "What's the coverage on X's policy?",
   "What do newspapers say about...?"

Given the user's query, decide which agent should handle it.
If the query could benefit from both perspectives, choose "both".
{page_context_section}
Respond ONLY with valid JSON:
{{"route": "tweet_agent" | "news_agent" | "both", "reason": "brief explanation"}}

User query: {query}"""


def route_query(query: str, on_token=None, page_context: str = "") -> dict:
    """
    Classify query and return routing decision.

    Returns:
        dict: {"route": "tweet_agent"|"news_agent"|"both", "reason": str}
    """
    try:
        page_section = ""
        if page_context:
            page_section = (
                "\nYou also have background context on this figure from our database. "
                "Use it to make a better routing decision:\n"
                f"---\n{page_context[:1000]}\n---\n"
            )

        prompt = ROUTER_PROMPT.format(
            query=query,
            page_context_section=page_section,
        )

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

        # Parse JSON from response
        result = json.loads(content)
        if result.get("route") not in ("tweet_agent", "news_agent", "both"):
            result["route"] = "tweet_agent"  # safe default
        return result

    except Exception as e:
        return {"route": "tweet_agent", "reason": f"Routing error, defaulting: {e}"}
