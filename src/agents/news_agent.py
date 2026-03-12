"""
News Agent
Expert in detailed opinions and comprehensive responses from news coverage.
Searches the politics-news Pinecone index for relevant articles.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent_tools.news_search import news_search

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

llm = ChatOpenAI(
    model=os.environ.get("GPT_MODEL", "RPRTHPB-gpt-5-mini"),
    base_url=os.environ.get("BASE_URL", "https://api.llmod.ai/v1"),
    api_key=os.environ.get("OPENAI_API_KEY"),
    temperature=1,
    max_tokens=2000,
)

NEWS_SYSTEM_PROMPT = """You are a political news analyst. You specialize in analyzing
local US news coverage of public figures — how newspapers, radio, and TV report on
politicians' actions, policies, and controversies.

Given the user's question and relevant news articles retrieved from the database,
provide a detailed, comprehensive answer. Follow these rules:

- Cite specific articles: include the media outlet name, state, and date
- Provide in-depth analysis drawing from multiple articles when possible
- Highlight regional differences in coverage if evident
- Note which public figures are mentioned and how they are portrayed
- Use ONLY the provided article data — do not use external knowledge
- If articles are not relevant: "I don't have news coverage addressing this topic."
- Structure your response with clear sections for readability"""


def run_news_agent(query: str, top_k: int = 7) -> dict:
    """
    Search for news articles and synthesize a response.

    Returns:
        dict: {"answer": str, "articles": list, "agent": "news_agent"}
    """
    # Search for news articles
    search_result = news_search(query, top_k=top_k)

    if not search_result["success"]:
        return {
            "answer": f"News search failed: {search_result['error']}",
            "articles": [],
            "agent": "news_agent",
        }

    articles = search_result["results"]

    if not articles:
        return {
            "answer": "No relevant news articles found for this query.",
            "articles": [],
            "agent": "news_agent",
        }

    # Build context from articles (sorted by date)
    sorted_articles = sorted(articles, key=lambda a: a["metadata"].get("date", ""))
    context = ""
    for a in sorted_articles[:5]:
        meta = a["metadata"]
        context += (
            f"Title: {meta.get('title', 'N/A')}\n"
            f"Source: {meta.get('media_name', 'Unknown')} ({meta.get('state', '')})\n"
            f"Date: {meta.get('date', 'Unknown')}\n"
            f"Type: {meta.get('media_type', 'Unknown')}\n"
            f"Speakers mentioned: {', '.join(meta.get('speakers_mentioned', []))}\n"
            f"Text: {meta.get('text', '')}\n\n"
        )

    # Synthesize answer
    messages = [
        {"role": "system", "content": NEWS_SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
    ]

    try:
        response = llm.invoke(messages)
        answer = response.content.strip()
    except Exception as e:
        answer = f"Error generating news analysis: {e}"

    return {
        "answer": answer,
        "articles": sorted_articles[:5],
        "agent": "news_agent",
    }
