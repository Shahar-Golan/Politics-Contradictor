"""
Tweet Agent
Expert in short responses, rivalry between politicians, direct quotes.
Searches the politics Pinecone index for relevant tweets.
"""

import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent_tools.vector_search import vector_search

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

llm = ChatOpenAI(
    model=os.environ.get("GPT_MODEL", "RPRTHPB-gpt-5-mini"),
    base_url=os.environ.get("BASE_URL", "https://api.llmod.ai/v1"),
    api_key=os.environ.get("OPENAI_API_KEY"),
    temperature=1,
    max_tokens=2000,
)

TWEET_SYSTEM_PROMPT = """You are a political tweets analyst. You specialize in analyzing
politicians' direct statements on social media — their opinions, rivalries, reactions,
and public positions.

Given the user's question and relevant tweets retrieved from the database, provide a
concise, evidence-based answer. Follow these rules:

- Write a concise synthesis first (do NOT output a full raw tweet list)
- Mention only the most important 2-4 points
- You may include up to 1-2 short direct quotes inline when helpful
- Omit URLs that appear in tweet text
- Highlight rivalries or contradictions between politicians if evident
- Use ONLY the provided tweet data — do not use external knowledge
- If tweets are not relevant: "I don't have tweets addressing this topic."
- Keep responses focused and readable with bullet points or short paragraphs
- Do NOT include sections/titles like "Tweets", "Sources", "Raw tweets", or "X sources"
- Do NOT repeat full tweet text that will already be shown separately in the UI"""


def _strip_duplicate_source_dump(answer: str) -> str:
    """
    Remove accidental trailing source/tweet dump if the model emits it.

    The frontend already renders tweets in dedicated source cards, so keeping this
    in the answer creates duplicate and noisy output.
    """
    if not answer:
        return answer

    patterns = [
        r"\n(?:Tweets|Tweet Sources|Sources|Raw Tweets?)\s*\n",
        r"\n\d+\s+sources\s*\n",
    ]

    cleaned = answer
    for pattern in patterns:
        parts = re.split(pattern, cleaned, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) > 1:
            cleaned = parts[0].rstrip()

    return cleaned.strip()


def run_tweet_agent(query: str, top_k: int = 10, on_token=None) -> dict:
    """
    Search for tweets and synthesize a response.

    Returns:
        dict: {"answer": str, "tweets": list, "agent": "tweet_agent"}
    """
    # Search for tweets
    search_result = vector_search(query, top_k=top_k)

    if not search_result["success"]:
        return {
            "answer": f"Tweet search failed: {search_result['error']}",
            "tweets": [],
            "agent": "tweet_agent",
        }

    tweets = search_result["results"]

    if not tweets:
        return {
            "answer": "No relevant tweets found for this query.",
            "tweets": [],
            "agent": "tweet_agent",
        }

    # Build context from tweets (sorted chronologically)
    sorted_tweets = sorted(tweets, key=lambda t: t["metadata"].get("created_at", ""))
    context = ""
    for t in sorted_tweets[:7]:
        meta = t["metadata"]
        context += (
            f"Author: {meta.get('author_name', 'Unknown')}\n"
            f"Date: {meta.get('created_at', 'Unknown')}\n"
            f"Tweet: {meta.get('text', '')}\n\n"
        )

    # Synthesize answer
    messages = [
        {"role": "system", "content": TWEET_SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
    ]

    try:
        if on_token:
            answer = ""
            for chunk in llm.stream(messages):
                token = chunk.content or ""
                answer += token
                on_token(token)
            answer = answer.strip()
        else:
            response = llm.invoke(messages)
            answer = response.content.strip()

        answer = _strip_duplicate_source_dump(answer)
    except Exception as e:
        answer = f"Error generating tweet analysis: {e}"

    return {
        "answer": answer,
        "tweets": sorted_tweets[:7],
        "agent": "tweet_agent",
    }
