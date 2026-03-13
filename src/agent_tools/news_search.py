"""
News Search Tool
Searches Pinecone politics-news index for relevant news articles.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI

# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

# Configuration
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PINECONE_NEWS_INDEX = os.environ.get("PINECONE_NEWS_INDEX_NAME", "politics-news")
BASE_URL = os.environ.get("BASE_URL", "https://api.llmod.ai/v1")
EMBEDDING_MODEL = "RPRTHPB-text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1024

# Initialize clients (lazy loading)
_pc_client = None
_index = None
_openai_client = None


def _get_pinecone_client():
    """Lazy initialization of Pinecone client for news index."""
    global _pc_client, _index
    if _pc_client is None:
        _pc_client = Pinecone(api_key=PINECONE_API_KEY)
        _index = _pc_client.Index(PINECONE_NEWS_INDEX)
    return _index


def _get_openai_client():
    """Lazy initialization of OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=BASE_URL
        )
    return _openai_client


def news_search(query: str, top_k: int = 5) -> dict:
    """
    Search Pinecone for relevant news articles based on user query.

    Args:
        query (str): The user's search query
        top_k (int): Number of results to return (default: 5)

    Returns:
        dict: Search results with structure:
            {
                "success": bool,
                "query": str,
                "results": [
                    {
                        "id": str,
                        "score": float,
                        "metadata": {
                            "doc_id": str,
                            "title": str,
                            "text": str,
                            "date": str,
                            "media_name": str,
                            "media_type": str,
                            "state": str,
                            "link": str,
                            "speakers_mentioned": list[str],
                            "type": "news_article"
                        }
                    }
                ],
                "count": int,
                "error": str | None
            }
    """
    try:
        index = _get_pinecone_client()
        client = _get_openai_client()

        # Generate query embedding
        emb_res = client.embeddings.create(
            input=query,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSIONS
        )
        query_vector = emb_res.data[0].embedding

        # Search Pinecone
        search_results = index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True
        )

        # Format results
        formatted_results = []
        for match in search_results['matches']:
            result = {
                "id": match['id'],
                "score": match['score'],
                "metadata": match.get('metadata', {})
            }
            formatted_results.append(result)

        return {
            "success": True,
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results),
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "query": query,
            "results": [],
            "count": 0,
            "error": str(e)
        }


if __name__ == "__main__":
    test_query = "Donald Trump tariff policy"
    print(f"Testing news_search with query: '{test_query}'")
    print("=" * 60)

    result = news_search(test_query, top_k=3)

    if result["success"]:
        print(f"Found {result['count']} results\n")
        for i, article in enumerate(result['results'], 1):
            meta = article['metadata']
            print(f"{i}. Score: {article['score']:.4f}")
            print(f"   Title: {meta.get('title', 'N/A')[:80]}")
            print(f"   Source: {meta.get('media_name', 'N/A')} ({meta.get('state', 'N/A')})")
            print(f"   Date: {meta.get('date', 'N/A')}")
            print(f"   Speakers: {meta.get('speakers_mentioned', [])}")
            print()
    else:
        print(f"Error: {result['error']}")