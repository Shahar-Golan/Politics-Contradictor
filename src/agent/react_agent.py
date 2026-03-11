"""
ReAct Agent Framework
Implements the Reasoning + Acting framework for intelligent tweet analysis.

Supports two modes:
- Rule-based (Step 4): Simple heuristics for decision making
- LLM-powered (Step 5): Intelligent reasoning using OpenAI GPT
"""

from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field
import sys
from pathlib import Path

# Import agent tools
sys.path.insert(0, str(Path(__file__).parent.parent))
from agent_tools.vector_search import vector_search
from agent_tools.web_scraper import web_scraper
from agent_tools.url_extractor import extract_urls

# Import LLM interface (Step 5)
try:
    from .llm_interface import (
        generate_thought_llm,
        generate_action_llm,
        generate_final_answer_llm
    )
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("Warning: LLM interface not available. Using rule-based mode only.")


@dataclass
class AgentState:
    """
    Maintains the state of the agent throughout the ReAct loop.
    """
    user_query: str
    max_iterations: int = 5
    current_iteration: int = 0
    
    # ReAct components
    thoughts: List[str] = field(default_factory=list)
    actions: List[Dict] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    
    # Data collected
    tweets_retrieved: List[Dict] = field(default_factory=list)
    scraped_urls: Set[str] = field(default_factory=set)
    scraped_content: List[Dict] = field(default_factory=list)
    
    # Final output
    final_answer: str = ""
    should_stop: bool = False


def generate_thought(state: AgentState, use_llm: bool = True) -> str:
    """
    Generate a thought about what to do next.
    
    Args:
        state: Current agent state
        use_llm: If True, use LLM-based reasoning (Step 5). If False, use rules (Step 4).
    
    Returns:
        str: Thought about next steps
    """
    # Use LLM if available and requested
    if use_llm and LLM_AVAILABLE:
        return generate_thought_llm(state)
    
    # Fallback to rule-based logic (Step 4)
    iteration = state.current_iteration
    
    # First iteration: always search for tweets
    if iteration == 0:
        return f"I need to search for tweets related to: '{state.user_query}'"
    
    # If we have tweets, check if any have URLs we should scrape
    if state.tweets_retrieved:
        # Find tweets with URLs that haven't been scraped
        tweets_with_unscraped_urls = []
        for tweet in state.tweets_retrieved[:3]:  # Check top 3 tweets
            if tweet['metadata'].get('has_urls'):
                urls = extract_urls(tweet['metadata'].get('text', ''))
                unscraped = [url for url in urls if url not in state.scraped_urls]
                if unscraped:
                    tweets_with_unscraped_urls.append((tweet, unscraped))
        
        if tweets_with_unscraped_urls:
            tweet, urls = tweets_with_unscraped_urls[0]
            return f"Tweet from {tweet['metadata']['author_name']} contains a URL. I should scrape it to get more context: {urls[0]}"
    
    # If we have enough information, finalize
    if state.tweets_retrieved:
        if len(state.scraped_content) > 0:
            return "I have tweets and scraped content. I have enough information to answer the question."
        elif not any(t['metadata'].get('has_urls') for t in state.tweets_retrieved[:3]):
            return "The top tweets don't contain URLs. I have enough information from the tweets alone."
        else:
            return "I have collected sufficient information to provide an answer."
    
    return "I need more information to answer the question adequately."


def decide_action(thought: str, state: AgentState, use_llm: bool = True) -> Dict:
    """
    Decide which action/tool to use based on the current thought and state.
    
    Args:
        thought: Current thought
        state: Current agent state
        use_llm: If True, use LLM-based decision (Step 5). If False, use rules (Step 4).
    
    Returns:
        dict: Action to take with structure:
            {
                "tool": "vector_search" | "web_scraper" | "finalize",
                "parameters": {...},
                "reason": str
            }
    """
    # Use LLM if available and requested
    if use_llm and LLM_AVAILABLE:
        return generate_action_llm(thought, state)
    
    # Fallback to rule-based logic (Step 4)
    # First iteration: search for tweets
    if state.current_iteration == 0:
        return {
            "tool": "vector_search",
            "parameters": {"query": state.user_query, "top_k": 10},
            "reason": "Initial search for relevant tweets"
        }
    
    # Check if we should scrape URLs
    if state.tweets_retrieved:
        for tweet in state.tweets_retrieved[:3]:  # Check top 3 tweets
            if tweet['metadata'].get('has_urls'):
                urls = extract_urls(tweet['metadata'].get('text', ''))
                for url in urls:
                    if url not in state.scraped_urls:
                        return {
                            "tool": "web_scraper",
                            "parameters": {"url": url},
                            "reason": f"Scraping URL from {tweet['metadata']['author_name']}'s tweet for additional context"
                        }
    
    # If we have information, finalize
    if state.tweets_retrieved:
        return {
            "tool": "finalize",
            "parameters": {},
            "reason": "Sufficient information collected to answer the query"
        }
    
    # Fallback: finalize
    return {
        "tool": "finalize",
        "parameters": {},
        "reason": "No more actions available"
    }


def execute_action(action: Dict, state: AgentState) -> str:
    """
    Execute the decided action and return observation.
    
    Args:
        action (dict): The action to execute
        state (AgentState): Current agent state
    
    Returns:
        str: Observation from executing the action
    """
    tool = action['tool']
    params = action['parameters']
    
    if tool == 'vector_search':
        # Execute vector search
        query = params['query']
        top_k = params.get('top_k', 5)
        
        result = vector_search(query, top_k=top_k)
        
        if result['success']:
            state.tweets_retrieved = result['results']
            count = result['count']
            
            # Build observation
            observation = f"Found {count} relevant tweets. Top 3:\n"
            for i, tweet in enumerate(result['results'][:3], 1):
                author = tweet['metadata'].get('author_name', 'Unknown')
                has_urls = tweet['metadata'].get('has_urls', False)
                text_preview = tweet['metadata'].get('text', '')[:100]
                observation += f"{i}. {author} (has_urls: {has_urls}): {text_preview}...\n"
            
            return observation
        else:
            return f"Search failed: {result['error']}"
    
    elif tool == 'web_scraper':
        # Execute web scraper
        url = params['url']
        
        result = web_scraper(url, timeout=15, expand_shortened=True)
        
        if result['success']:
            state.scraped_urls.add(url)
            state.scraped_content.append(result)
            
            observation = f"Successfully scraped {url}\n"
            observation += f"Title: {result['title']}\n"
            observation += f"Word count: {result['word_count']}\n"
            observation += f"Has statistics: {result['statistics'].get('has_numbers', False)}\n"
            observation += f"Content preview: {result['content_preview'][:150]}..."
            
            return observation
        else:
            state.scraped_urls.add(url)  # Mark as attempted
            return f"Failed to scrape {url}: {result['error']}"
    
    elif tool == 'finalize':
        state.should_stop = True
        return "Ready to generate final answer."
    
    else:
        return f"Unknown tool: {tool}"


def should_finalize(state: AgentState) -> bool:
    """
    Determine if the agent should stop and generate final answer.
    """
    # Stop if explicitly flagged
    if state.should_stop:
        return True
    
    # Stop if max iterations reached
    if state.current_iteration >= state.max_iterations:
        return True
    
    # Stop if we have tweets and checked all URLs in top tweets
    if state.tweets_retrieved:
        urls_to_check = []
        for tweet in state.tweets_retrieved[:3]:
            if tweet['metadata'].get('has_urls'):
                urls = extract_urls(tweet['metadata'].get('text', ''))
                urls_to_check.extend(urls)
        
        # If all URLs are scraped (or attempted), we can finalize
        if urls_to_check and all(url in state.scraped_urls for url in urls_to_check):
            return True
        
        # If no URLs to scrape, finalize after getting tweets
        if not urls_to_check and state.current_iteration > 0:
            return True
    
    return False


def generate_final_answer(state: AgentState, use_llm: bool = True) -> str:
    """
    Generate the final answer based on collected information.
    
    Args:
        state: Current agent state with all collected data
        use_llm: If True, use LLM synthesis (Step 5). If False, use template (Step 4).
    
    Returns:
        str: Final answer
    """
    # Use LLM if available and requested
    if use_llm and LLM_AVAILABLE:
        return generate_final_answer_llm(state)
    
    # Fallback to template-based answer (Step 4)
    if not state.tweets_retrieved:
        return "I couldn't find any relevant tweets to answer your question."
    
    # Build a simple answer from the collected data
    answer = f"Based on {len(state.tweets_retrieved)} tweets"
    
    if state.scraped_content:
        answer += f" and {len(state.scraped_content)} analyzed web page(s)"
    
    answer += f", here are the key findings:\n\n"
    
    # Add top tweets
    answer += "**Relevant Tweets:**\n"
    for i, tweet in enumerate(state.tweets_retrieved[:3], 1):
        meta = tweet['metadata']
        author = meta.get('author_name', 'Unknown')
        date = meta.get('created_at', 'Unknown')
        text = meta.get('text', '')
        
        answer += f"\n{i}. **{author}** ({date}):\n"
        answer += f"   \"{text[:200]}{'...' if len(text) > 200 else ''}\"\n"
        
        # Add URLs if present
        if meta.get('has_urls'):
            urls = extract_urls(text)
            if urls:
                answer += f"   🔗 Links: {', '.join(urls)}\n"
    
    # Add scraped content summaries
    if state.scraped_content:
        answer += "\n**Additional Context from Web Pages:**\n"
        for i, content in enumerate(state.scraped_content, 1):
            answer += f"\n{i}. **{content['title'] or content['url']}**\n"
            answer += f"   {content['content_preview'][:200]}...\n"
            if content['statistics'].get('has_numbers'):
                answer += f"   📊 Contains statistical data\n"
    
    return answer


def run_agent(user_query: str, max_iterations: int = 5, verbose: bool = True, use_llm: bool = True) -> Dict:
    """
    Run the ReAct agent to answer a user query.
    
    Args:
        user_query (str): The user's question
        max_iterations (int): Maximum number of ReAct iterations
        verbose (bool): Whether to print progress
        use_llm (bool): If True, use LLM-powered reasoning (Step 5). If False, use rules (Step 4).
    
    Returns:
        dict: Complete agent result with structure:
            {
                "query": str,
                "final_answer": str,
                "iterations": int,
                "thoughts": List[str],
                "actions": List[dict],
                "observations": List[str],
                "tweets_found": int,
                "urls_scraped": int,
                "mode": str,  # "llm" or "rule-based"
                "success": bool
            }
    """
    # Initialize agent state
    state = AgentState(user_query=user_query, max_iterations=max_iterations)
    
    mode = "llm-powered" if (use_llm and LLM_AVAILABLE) else "rule-based"
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"REACT AGENT STARTING ({mode.upper()} MODE)")
        print(f"Query: {user_query}")
        print(f"{'='*70}\n")
    
    # ReAct Loop
    for iteration in range(max_iterations):
        state.current_iteration = iteration
        
        if verbose:
            print(f"--- Iteration {iteration + 1} ---\n")
        
        # THOUGHT: Analyze situation
        thought = generate_thought(state, use_llm=use_llm)
        state.thoughts.append(thought)
        
        if verbose:
            print(f"💭 THOUGHT: {thought}\n")
        
        # ACTION: Decide what to do
        action = decide_action(thought, state, use_llm=use_llm)
        state.actions.append(action)
        
        if verbose:
            print(f"🔧 ACTION: {action['tool']}")
            print(f"   Reason: {action['reason']}")
            print(f"   Parameters: {action['parameters']}\n")
        
        # OBSERVATION: Execute and observe
        observation = execute_action(action, state)
        state.observations.append(observation)
        
        if verbose:
            print(f"👁️  OBSERVATION: {observation}\n")
        
        # Check if we should stop
        if should_finalize(state):
            if verbose:
                print(f"✓ Agent has sufficient information to answer.\n")
            break
    
    # Generate final answer
    if verbose:
        print(f"{'='*70}")
        print(f"GENERATING FINAL ANSWER...")
        print(f"{'='*70}\n")
    
    final_answer = generate_final_answer(state, use_llm=use_llm)
    state.final_answer = final_answer
    
    if verbose:
        print(f"📝 FINAL ANSWER:\n")
        print(final_answer)
        print(f"\n{'='*70}\n")
    
    # Return comprehensive result
    return {
        "query": user_query,
        "final_answer": final_answer,
        "iterations": state.current_iteration + 1,
        "thoughts": state.thoughts,
        "actions": state.actions,
        "observations": state.observations,
        "tweets_found": len(state.tweets_retrieved),
        "urls_scraped": len(state.scraped_content),
        "tweets": state.tweets_retrieved,
        "scraped_content": state.scraped_content,
        "mode": mode,
        "success": True
    }


if __name__ == "__main__":
    # Test the agent
    test_query = "What did Bill Gates say about climate change?"
    result = run_agent(test_query, max_iterations=5, verbose=True)
    
    print(f"\n{'='*70}")
    print(f"AGENT SUMMARY")
    print(f"{'='*70}")
    print(f"Query: {result['query']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Tweets found: {result['tweets_found']}")
    print(f"URLs scraped: {result['urls_scraped']}")
    print(f"Success: {result['success']}")
    print(f"{'='*70}\n")
