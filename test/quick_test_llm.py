"""
Quick test of LLM-powered agent - single query
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.react_agent import run_agent

print("="*70)
print("QUICK LLM AGENT TEST")
print("="*70)

query = "What did Obama say about healthcare?"
print(f"\nQuery: {query}\n")

result = run_agent(query, max_iterations=3, verbose=True, use_llm=True)

print("\n" + "="*70)
print("RESULTS:")
print("="*70)
print(f"Success: {result['success']}")
print(f"Mode: {result['mode']}")
print(f"Iterations: {result['iterations']}")
print(f"Tweets found: {result['tweets_found']}")
print(f"URLs scraped: {result['urls_scraped']}")
print(f"\nFinal Answer:")
print(result['final_answer'])
print("="*70)

if result['success'] and result['mode'] == 'llm-powered':
    print("\n[PASSED] LLM agent works!")
else:
    print("\n[FAILED] LLM agent failed")
    sys.exit(1)
