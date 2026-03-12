"""
Unit tests for all API endpoints.
Requires the backend to be running on localhost:5000.
"""

import requests
import time

BASE_URL = "http://localhost:5000/api"


def test_stats():
    """GET /api/stats — should return chunk_size, overlap_ratio, top_k."""
    print("Testing GET /api/stats ...")
    res = requests.get(f"{BASE_URL}/stats")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "chunk_size" in data, "Missing chunk_size"
    assert "overlap_ratio" in data, "Missing overlap_ratio"
    assert "top_k" in data, "Missing top_k"
    print(f"  OK — chunk_size={data['chunk_size']}, top_k={data['top_k']}")


def test_prompt():
    """POST /api/prompt — simple RAG endpoint."""
    print("Testing POST /api/prompt ...")
    res = requests.post(f"{BASE_URL}/prompt", json={"question": "What did Trump say about China?"})
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "response" in data, "Missing response field"
    assert "context" in data, "Missing context field"
    assert "Augmented_prompt" in data, "Missing Augmented_prompt field"
    assert len(data["context"]) > 0, "Context should not be empty"
    print(f"  OK — response length={len(data['response'])}, context items={len(data['context'])}")


def test_prompt_empty():
    """POST /api/prompt with empty question — should return 400."""
    print("Testing POST /api/prompt (empty question) ...")
    res = requests.post(f"{BASE_URL}/prompt", json={"question": ""})
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    print("  OK — returned 400 as expected")


def test_agent_query():
    """POST /api/agent/query — ReAct agent endpoint."""
    print("Testing POST /api/agent/query ...")
    res = requests.post(f"{BASE_URL}/agent/query", json={"query": "What did Obama say about healthcare?"})
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "answer" in data, "Missing answer field"
    assert "mode" in data, "Missing mode field"
    assert "iterations" in data, "Missing iterations field"
    assert "tweets_found" in data, "Missing tweets_found field"
    print(f"  OK — mode={data['mode']}, iterations={data['iterations']}, tweets={data['tweets_found']}")


def test_agent_query_empty():
    """POST /api/agent/query with empty query — should return 400."""
    print("Testing POST /api/agent/query (empty query) ...")
    res = requests.post(f"{BASE_URL}/agent/query", json={"query": ""})
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    print("  OK — returned 400 as expected")


def test_v2_query_tweet_route():
    """POST /api/v2/query — should route to tweet_agent."""
    print("Testing POST /api/v2/query (tweet route) ...")
    res = requests.post(f"{BASE_URL}/v2/query", json={"query": "What did Trump say about Biden?"})
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "answer" in data, "Missing answer field"
    assert "route" in data, "Missing route field"
    assert "route_reason" in data, "Missing route_reason field"
    assert "agent_used" in data, "Missing agent_used field"
    assert "tweets" in data, "Missing tweets field"
    assert "articles" in data, "Missing articles field"
    assert data["route"] in ("tweet_agent", "news_agent", "both"), f"Unexpected route: {data['route']}"
    print(f"  OK — route={data['route']}, agent={data['agent_used']}, tweets={len(data['tweets'])}, articles={len(data['articles'])}")


def test_v2_query_news_route():
    """POST /api/v2/query — should route to news_agent."""
    print("Testing POST /api/v2/query (news route) ...")
    res = requests.post(f"{BASE_URL}/v2/query", json={"query": "How did local newspapers cover Obama's healthcare policy?"})
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "answer" in data, "Missing answer field"
    assert data["route"] in ("tweet_agent", "news_agent", "both"), f"Unexpected route: {data['route']}"
    print(f"  OK — route={data['route']}, agent={data['agent_used']}, tweets={len(data['tweets'])}, articles={len(data['articles'])}")


def test_v2_query_both_route():
    """POST /api/v2/query — should route to both agents."""
    print("Testing POST /api/v2/query (both route) ...")
    res = requests.post(f"{BASE_URL}/v2/query", json={"query": "Compare Trump's tweets about tariffs with news coverage"})
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert "answer" in data, "Missing answer field"
    assert data["route"] in ("tweet_agent", "news_agent", "both"), f"Unexpected route: {data['route']}"
    print(f"  OK — route={data['route']}, agent={data['agent_used']}, tweets={len(data['tweets'])}, articles={len(data['articles'])}")


def test_v2_query_empty():
    """POST /api/v2/query with empty query — should return 400."""
    print("Testing POST /api/v2/query (empty query) ...")
    res = requests.post(f"{BASE_URL}/v2/query", json={"query": ""})
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    print("  OK — returned 400 as expected")


if __name__ == "__main__":
    tests = [
        test_stats,
        test_prompt,
        test_prompt_empty,
        test_agent_query,
        test_agent_query_empty,
        test_v2_query_tweet_route,
        test_v2_query_news_route,
        test_v2_query_both_route,
        test_v2_query_empty,
    ]

    passed = 0
    failed = 0
    errors = []

    print(f"\n{'='*60}")
    print("Running endpoint tests against http://localhost:5000")
    print(f"{'='*60}\n")

    for test in tests:
        try:
            start = time.time()
            test()
            elapsed = time.time() - start
            print(f"  Time: {elapsed:.1f}s\n")
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"  FAILED: {e}\n")

    print(f"{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if errors:
        print("\nFailures:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print(f"{'='*60}")
