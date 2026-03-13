"""
System B — Interactive Query Graph (LangGraph)

Routes user queries through: page_lookup → router → tweet_agent / news_agent / both.

Usage:
    from src.graphs.query_graph import run_query
    result = run_query("What did Trump say about tariffs?")
"""

import sys
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.page_lookup import lookup_page
from agents.router import route_query
from agents.tweet_agent import run_tweet_agent
from agents.news_agent import run_news_agent


# ── State ────────────────────────────────────────────────────────────────────

class QueryState(TypedDict):
    query: str
    # Page lookup
    page_found: bool
    page_content: str
    # Routing
    route: str            # "tweet_agent" | "news_agent" | "both"
    route_reason: str
    # Agent results
    answer: str
    tweets: list
    articles: list
    agent_used: str       # which agent(s) produced the answer


# ── Nodes ────────────────────────────────────────────────────────────────────

def page_lookup_node(state: QueryState) -> dict:
    """Check cached figure pages first."""
    result = lookup_page(state["query"])
    return {
        "page_found": result["found"],
        "page_content": result["content"] or "",
    }


def router_node(state: QueryState) -> dict:
    """Classify the query and decide routing."""
    result = route_query(state["query"])
    return {
        "route": result["route"],
        "route_reason": result["reason"],
    }


def tweet_agent_node(state: QueryState) -> dict:
    """Run the tweet agent."""
    result = run_tweet_agent(state["query"])
    return {
        "answer": result["answer"],
        "tweets": result["tweets"],
        "articles": [],
        "agent_used": "tweet_agent",
    }


def news_agent_node(state: QueryState) -> dict:
    """Run the news agent."""
    result = run_news_agent(state["query"])
    return {
        "answer": result["answer"],
        "articles": result["articles"],
        "tweets": [],
        "agent_used": "news_agent",
    }


def both_agents_node(state: QueryState) -> dict:
    """Run both agents and merge results."""
    tweet_result = run_tweet_agent(state["query"])
    news_result = run_news_agent(state["query"])

    combined_answer = (
        "## From Tweets (direct statements)\n\n"
        f"{tweet_result['answer']}\n\n"
        "---\n\n"
        "## From News Coverage\n\n"
        f"{news_result['answer']}"
    )

    return {
        "answer": combined_answer,
        "tweets": tweet_result["tweets"],
        "articles": news_result["articles"],
        "agent_used": "both",
    }


def page_answer_node(state: QueryState) -> dict:
    """Answer from cached page data."""
    return {
        "answer": state["page_content"],
        "tweets": [],
        "articles": [],
        "agent_used": "page_cache",
    }


# ── Conditional edges ────────────────────────────────────────────────────────

def after_page_lookup(state: QueryState) -> str:
    """Route based on whether page data was sufficient."""
    if state["page_found"]:
        return "page_answer"
    return "router"


def after_router(state: QueryState) -> str:
    """Route to the appropriate agent."""
    route = state["route"]
    if route == "news_agent":
        return "news_agent"
    elif route == "both":
        return "both_agents"
    return "tweet_agent"  # default


# ── Build graph ──────────────────────────────────────────────────────────────

def build_query_graph() -> StateGraph:
    """Build and compile the query graph."""
    graph = StateGraph(QueryState)

    # Add nodes
    graph.add_node("page_lookup", page_lookup_node)
    graph.add_node("page_answer", page_answer_node)
    graph.add_node("router", router_node)
    graph.add_node("tweet_agent", tweet_agent_node)
    graph.add_node("news_agent", news_agent_node)
    graph.add_node("both_agents", both_agents_node)

    # Edges
    graph.add_edge(START, "page_lookup")
    graph.add_conditional_edges("page_lookup", after_page_lookup)
    graph.add_conditional_edges("router", after_router)
    graph.add_edge("page_answer", END)
    graph.add_edge("tweet_agent", END)
    graph.add_edge("news_agent", END)
    graph.add_edge("both_agents", END)

    return graph.compile()


# Compiled graph instance
query_graph = build_query_graph()


def run_query(query: str) -> dict:
    """
    Run a user query through the full graph.

    Args:
        query: User's question

    Returns:
        dict with: query, answer, route, route_reason, agent_used, tweets, articles
    """
    initial_state = {
        "query": query,
        "page_found": False,
        "page_content": "",
        "route": "",
        "route_reason": "",
        "answer": "",
        "tweets": [],
        "articles": [],
        "agent_used": "",
    }

    result = query_graph.invoke(initial_state)
    return result


def run_query_stream(query: str):
    """
    Stream query execution as SSE events.
    Yields JSON strings: node_start, node_end, token, done.

    Uses a thread+queue pattern so LLM tokens stream in real-time
    while agent functions run in a background thread.
    """
    import json
    import queue
    import threading

    q = queue.Queue()
    SENTINEL = "__DONE__"

    def emit(event):
        q.put(json.dumps(event))

    def on_token(token):
        q.put(json.dumps({"type": "token", "content": token}))

    def run_pipeline():
        try:
            # 1. Page Lookup
            emit({"type": "node_start", "node": "page_lookup"})
            page_result = lookup_page(query)
            emit({"type": "node_end", "node": "page_lookup"})

            if page_result["found"]:
                emit({"type": "done", "data": {
                    "answer": page_result["content"],
                    "route": "page_cache", "route_reason": "Found in cache",
                    "agent_used": "page_cache", "tweets": [], "articles": [],
                }})
                return

            # 2. Router
            emit({"type": "node_start", "node": "router"})
            route_result = route_query(query, on_token=on_token)
            emit({"type": "node_end", "node": "router", "data": route_result})

            route = route_result.get("route", "tweet_agent")
            reason = route_result.get("reason", "")
            final = {"route": route, "route_reason": reason,
                      "tweets": [], "articles": [], "answer": "", "agent_used": route}

            # 3. Agent(s)
            if route == "tweet_agent":
                emit({"type": "node_start", "node": "tweet_agent"})
                result = run_tweet_agent(query, on_token=on_token)
                emit({"type": "node_end", "node": "tweet_agent"})
                final["answer"] = result["answer"]
                final["tweets"] = result["tweets"]

            elif route == "news_agent":
                emit({"type": "node_start", "node": "news_agent"})
                result = run_news_agent(query, on_token=on_token)
                emit({"type": "node_end", "node": "news_agent"})
                final["answer"] = result["answer"]
                final["articles"] = result["articles"]

            elif route == "both":
                emit({"type": "node_start", "node": "both"})

                emit({"type": "node_start", "node": "tweet_agent"})
                on_token("## From Tweets (direct statements)\n\n")
                tweet_result = run_tweet_agent(query, on_token=on_token)
                emit({"type": "node_end", "node": "tweet_agent"})

                on_token("\n\n---\n\n## From News Coverage\n\n")

                emit({"type": "node_start", "node": "news_agent"})
                news_result = run_news_agent(query, on_token=on_token)
                emit({"type": "node_end", "node": "news_agent"})

                emit({"type": "node_end", "node": "both"})

                final["answer"] = (
                    "## From Tweets (direct statements)\n\n"
                    + tweet_result["answer"] + "\n\n---\n\n"
                    + "## From News Coverage\n\n"
                    + news_result["answer"]
                )
                final["tweets"] = tweet_result["tweets"]
                final["articles"] = news_result["articles"]
                final["agent_used"] = "both"

            emit({"type": "done", "data": final})
        except Exception as e:
            emit({"type": "error", "message": str(e)})
        finally:
            q.put(SENTINEL)

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()

    while True:
        item = q.get()
        if item == SENTINEL:
            break
        yield item


if __name__ == "__main__":
    # Test the query graph
    test_queries = [
        "What did Trump say about Biden?",
        "How did local newspapers cover Obama's healthcare policy?",
        "Compare Trump's tweets about tariffs with news coverage",
    ]

    for q in test_queries:
        print(f"\n{'='*70}")
        print(f"QUERY: {q}")
        print(f"{'='*70}")

        result = run_query(q)

        print(f"Route: {result['route']} ({result['route_reason']})")
        print(f"Agent used: {result['agent_used']}")
        print(f"Tweets: {len(result['tweets'])}")
        print(f"Articles: {len(result['articles'])}")
        print(f"\nAnswer:\n{result['answer'][:500]}...")
