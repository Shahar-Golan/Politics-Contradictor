"""
Vector Search Tool
Searches Pinecone for relevant tweets based on user query.
"""

import os
import re
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
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "politics")
BASE_URL = os.environ.get("BASE_URL", "https://api.llmod.ai/v1")
EMBEDDING_MODEL = "RPRTHPB-text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1024

# Initialize clients (lazy loading)
_pc_client = None
_index = None
_openai_client = None


def _clean_tweet_text(text: str) -> str:
    """
    Remove common encoding artifacts from tweet text.

    In this dataset, corrupted characters often appear as repeated question marks
    (e.g., "??????") inside quoted text. We remove these runs while preserving
    normal punctuation.
    """
    if not isinstance(text, str) or not text:
        return text

    cleaned = text.replace("\ufffd", "")
    cleaned = re.sub(r"\?{2,}", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _get_pinecone_client():
    """Lazy initialization of Pinecone client."""
    global _pc_client, _index
    if _pc_client is None:
        _pc_client = Pinecone(api_key=PINECONE_API_KEY)
        _index = _pc_client.Index(PINECONE_INDEX_NAME)
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


def vector_search(query: str, top_k: int = 5) -> dict:
    """
    Search Pinecone for relevant tweets based on user query.
    
    Args:
        query (str): The user's search query
        top_k (int): Number of results to return (default: 5)
    
    Returns:
        dict: Search results with the following structure:
            {
                "success": bool,
                "query": str,
                "results": [
                    {
                        "id": str,
                        "score": float,
                        "metadata": {
                            "text": str,
                            "author_name": str,
                            "created_at": str,
                            "has_urls": bool,
                            "account_id": str
                        }
                    }
                ],
                "count": int,
                "error": str | None
            }
    """
    try:
        # Get clients
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
            metadata = match.get('metadata', {})
            if isinstance(metadata, dict) and 'text' in metadata:
                metadata = dict(metadata)
                metadata['text'] = _clean_tweet_text(metadata.get('text', ''))

            result = {
                "id": match['id'],
                "score": match['score'],
                "metadata": metadata
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
    # Test the vector search
    test_query = "What did Hillary Clinton say about immigration?"
    print(f"Testing vector_search with query: '{test_query}'")
    print("=" * 60)
    
    result = vector_search(test_query, top_k=3)
    
    if result["success"]:
        print(f"✓ Found {result['count']} results\n")
        for i, tweet in enumerate(result['results'], 1):
            print(f"{i}. Score: {tweet['score']:.4f}")
            print(f"   Author: {tweet['metadata'].get('author_name', 'Unknown')}")
            print(f"   Text: {tweet['metadata'].get('text', '')[:100]}...")
            print(f"   Has URLs: {tweet['metadata'].get('has_urls', False)}")
            print()
    else:
        print(f"✗ Error: {result['error']}")
