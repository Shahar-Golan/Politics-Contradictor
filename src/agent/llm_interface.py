"""
LLM Interface for ReAct Agent
Handles all communication with OpenAI for intelligent reasoning.
"""

import os
import json
from typing import Dict, Optional
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

from .prompts import (
    SYSTEM_PROMPT,
    get_thought_prompt,
    get_action_prompt,
    get_final_answer_prompt
)

# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

# Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BASE_URL = os.environ.get("BASE_URL", "https://api.llmod.ai/v1")
GPT_MODEL = os.environ.get("GPT_MODEL", "RPRTHPB-gpt-5-mini")

# Initialize OpenAI client (lazy loading)
_openai_client = None


def _get_openai_client():
    """Lazy initialization of OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=BASE_URL
        )
    return _openai_client


def generate_thought_llm(state) -> str:
    """
    Use LLM to generate a thought about what to do next.
    
    This replaces the rule-based thought generation from Step 4.
    
    Args:
        state: AgentState object with current state
    
    Returns:
        str: The LLM's thought about next steps
    """
    client = _get_openai_client()
    
    # Get the thought prompt
    user_prompt = get_thought_prompt(state)
    
    # Call LLM
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=1,  # GPT-5 only supports temperature=1
            max_tokens=1000  # GPT-5 uses ~500 reasoning tokens, needs extra for output
        )
        
        thought = response.choices[0].message.content.strip()
        return thought
        
    except Exception as e:
        # Fallback to simple thought if LLM fails
        return f"Error generating thought: {e}. Proceeding with available information."


def generate_action_llm(thought: str, state) -> Dict:
    """
    Use LLM to decide which action to take based on the thought.
    
    This replaces the rule-based action decision from Step 4.
    
    Args:
        thought (str): The current thought
        state: AgentState object
    
    Returns:
        dict: Action to take with structure:
            {
                "tool": "vector_search" | "web_scraper" | "finalize",
                "parameters": {...},
                "reason": str
            }
    """
    client = _get_openai_client()
    
    # Get the action prompt
    user_prompt = get_action_prompt(thought, state)
    
    # Call LLM with JSON mode for structured output
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs valid JSON."},
                {"role": "user", "content": user_prompt}
            ],
            temperature=1,  # GPT-5 only supports temperature=1
            max_tokens=800,  # GPT-5 uses ~400 reasoning tokens, needs extra for JSON output,
            response_format={"type": "json_object"}
        )        
        action_json = response.choices[0].message.content
        
        # Debug: Check if content is empty
        if not action_json or action_json.strip() == '':
            raise ValueError(f"Empty response from LLM. Finish reason: {response.choices[0].finish_reason}, Usage: {response.usage}")
        
        action_json = action_json.strip()
        action = json.loads(action_json)
        
        # Validate action structure
        if "tool" not in action:
            raise ValueError("Action must contain 'tool' field")
        if "parameters" not in action:
            action["parameters"] = {}
        if "reason" not in action:
            action["reason"] = "No reason provided"
        
        return action
        
    except Exception as e:
        # Fallback to safe action if LLM fails
        print(f"Warning: LLM action generation failed: {e}")
        
        # Smart fallback based on state
        if not state.tweets_retrieved:
            return {
                "tool": "vector_search",
                "parameters": {"query": state.user_query, "top_k": 10},
                "reason": "Fallback: Initial search"
            }
        else:
            return {
                "tool": "finalize",
                "parameters": {},
                "reason": "Fallback: Finalize with available data"
            }


def generate_final_answer_llm(state) -> str:
    """
    Use LLM to generate a comprehensive final answer.
    
    This replaces the simple template-based answer from Step 4.
    
    Args:
        state: AgentState object with all collected information
    
    Returns:
        str: Comprehensive final answer synthesized by LLM
    """
    client = _get_openai_client()
    
    # Get the final answer prompt
    user_prompt = get_final_answer_prompt(state)
    
    # Call LLM for synthesis
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=1,  # GPT-5 only supports temperature=1
            max_tokens=3000  # GPT-5 uses ~1000+ reasoning tokens for complex synthesis
        )
        
        final_answer = response.choices[0].message.content.strip()
        return final_answer
        
    except Exception as e:
        # Fallback to basic answer if LLM fails
        return f"Error generating answer: {e}\n\nBased on {len(state.tweets_retrieved)} tweets collected, the information is available but could not be synthesized. Please review the raw tweet data."


# Backwards compatibility - export functions with original names
def generate_thought(state) -> str:
    """Wrapper for backwards compatibility."""
    return generate_thought_llm(state)


def generate_action(thought: str, state) -> Dict:
    """Wrapper for backwards compatibility."""
    return generate_action_llm(thought, state)


def generate_final_answer(state) -> str:
    """Wrapper for backwards compatibility."""
    return generate_final_answer_llm(state)


if __name__ == "__main__":
    # Test LLM interface
    print("Testing LLM Interface...")
    print("=" * 70)
    
    # Test 1: Test client initialization
    try:
        client = _get_openai_client()
        print("✓ OpenAI client initialized successfully")
    except Exception as e:
        print(f"✗ Failed to initialize client: {e}")
    
    # Test 2: Test basic LLM call
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "user", "content": "Say 'test successful' if you can read this."}
            ],
            max_tokens=10
        )
        result = response.choices[0].message.content
        print(f"✓ LLM communication successful: {result}")
    except Exception as e:
        print(f"✗ LLM communication failed: {e}")
    
    # Test 3: Test JSON mode
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": "You output valid JSON."},
                {"role": "user", "content": 'Output this JSON: {"test": "success", "number": 42}'}
            ],
            response_format={"type": "json_object"},
            max_tokens=50
        )
        result = response.choices[0].message.content
        parsed = json.loads(result)
        print(f"✓ JSON mode successful: {parsed}")
    except Exception as e:
        print(f"✗ JSON mode failed: {e}")
    
    print("=" * 70)
    print("\nLLM Interface tests completed!")
