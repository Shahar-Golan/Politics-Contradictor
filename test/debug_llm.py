"""
Debug script to test LLM API calls directly
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BASE_URL = os.environ.get("BASE_URL", "https://api.llmod.ai/v1")
GPT_MODEL = os.environ.get("GPT_MODEL", "RPRTHPB-gpt-5-mini")

print("=" * 70)
print("LLM API DEBUG TEST")
print("=" * 70)
print(f"Model: {GPT_MODEL}")
print(f"Base URL: {BASE_URL}")
print()

client = OpenAI(api_key=OPENAI_API_KEY, base_url=BASE_URL)

# Test 1: Simple completion
print("TEST 1: Simple completion (no temperature specified)")
print("-" * 70)
try:
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "user", "content": "Say 'Hello, I am working!' if you receive this."}
        ],
        max_tokens=800  # GPT-5 uses reasoning tokens
    )
    print(f"Finish reason: {response.choices[0].finish_reason}")
    print(f"Usage: {response.usage}")
    result = response.choices[0].message.content
    print(f"✓ Content: '{result}'")
    print(f"  Length: {len(result) if result else 0}")
except Exception as e:
    print(f"✗ Failed: {e}")

print()

# Test 2: With temperature=1
print("TEST 2: Simple completion (temperature=1)")
print("-" * 70)
try:
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "user", "content": "Say 'Temperature 1 works!' if you receive this."}
        ],
        temperature=1,
        max_tokens=800
    )
    result = response.choices[0].message.content
    print(f"✓ Success: {result}")
except Exception as e:
    print(f"✗ Failed: {e}")

print()

# Test 3: JSON mode with temperature=1
print("TEST 3: JSON mode (temperature=1)")
print("-" * 70)
try:
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": "You output valid JSON."},
            {"role": "user", "content": 'Return this JSON: {"status": "success", "message": "JSON mode works"}'}
        ],
        temperature=1,
        max_tokens=800,
        response_format={"type": "json_object"}
    )
    result = response.choices[0].message.content
    parsed = json.loads(result)
    print(f"✓ Success: {result}")
    print(f"  Parsed: {parsed}")
except json.JSONDecodeError as e:
    print(f"✗ JSON Parse Error: {e}")
    print(f"  Raw response: '{result}'")
except Exception as e:
    print(f"✗ Failed: {e}")

print()

# Test 4: Action decision prompt (our actual use case)
print("TEST 4: Action decision prompt (our actual use case)")
print("-" * 70)
action_prompt = """You are a ReAct agent. Based on the thought below, decide which action to take.

CURRENT SITUATION:
- User Query: What did Obama say about healthcare?
- Tweets Retrieved: 0
- URLs Scraped: 0

THOUGHT: I need to search for tweets to answer the query.

AVAILABLE ACTIONS:
1. vector_search - Search Pinecone for relevant tweets
2. web_scraper - Scrape content from a URL
3. finalize - Generate final answer

Output a JSON object with this structure:
{
  "tool": "vector_search" | "web_scraper" | "finalize",
  "parameters": {"query": "...", "top_k": 10} or {"url": "..."},
  "reason": "explanation"
}"""

try:
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that outputs valid JSON."},
            {"role": "user", "content": action_prompt}
        ],
        temperature=1,
        max_tokens=800,
        response_format={"type": "json_object"}
    )
    result = response.choices[0].message.content
    parsed = json.loads(result)
    print(f"✓ Success!")
    print(f"  Raw: {result}")
    print(f"  Parsed: {json.dumps(parsed, indent=2)}")
except json.JSONDecodeError as e:
    print(f"✗ JSON Parse Error: {e}")
    print(f"  Raw response: '{result}'")
    print(f"  Response length: {len(result)}")
    print(f"  First 100 chars: {result[:100]}")
except Exception as e:
    print(f"✗ Failed: {e}")

print()
print("=" * 70)
print("Debug tests completed!")
print("=" * 70)
