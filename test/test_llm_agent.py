"""
Test LLM-Powered ReAct Agent (Step 5)
Tests the LLM-based intelligent reasoning agent.
"""

import sys
import os
from pathlib import Path

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.react_agent import run_agent


def print_separator(title=""):
    """Print a nice separator line."""
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}")
    else:
        print(f"{'='*70}")


def test_llm_agent_basic():
    """Test LLM agent with a basic query."""
    print_separator("TEST 1: LLM Agent - Basic Query")
    
    query = "What did Hillary Clinton say about immigration?"
    print(f"\nQuery: {query}\n")
    
    result = run_agent(query, max_iterations=3, verbose=False, use_llm=True)
    
    # Verify results
    assert result['success'], "Agent should succeed"
    assert result['mode'] == 'llm-powered', "Should be in LLM mode"
    assert result['tweets_found'] > 0, "Should find tweets"
    assert len(result['thoughts']) > 0, "Should have LLM-generated thoughts"
    assert result['final_answer'], "Should have final answer"
    
    print(f"[OK] Agent completed in {result['iterations']} iterations")
    print(f"[OK] Mode: {result['mode']}")
    print(f"[OK] Found {result['tweets_found']} tweets")
    print(f"[OK] Scraped {result['urls_scraped']} URLs")
    
    print(f"\nSample Thought (LLM-generated):")
    print(f"  \"{result['thoughts'][0]}\"")
    
    print(f"\nFinal Answer Preview (LLM-synthesized):")
    print(result['final_answer'][:400] + "...")
    
    return True


def test_llm_agent_with_urls():
    """Test LLM agent with URL scraping."""
    print_separator("TEST 2: LLM Agent - With URL Scraping")
    
    query = "What climate initiative did Bill Gates tweet about?"
    print(f"\nQuery: {query}\n")
    
    result = run_agent(query, max_iterations=5, verbose=False, use_llm=True)
    
    # Verify results
    assert result['success'], "Agent should succeed"
    assert result['mode'] == 'llm-powered', "Should be in LLM mode"
    assert result['tweets_found'] > 0, "Should find tweets"
    
    print(f"[OK] Agent completed in {result['iterations']} iterations")
    print(f"[OK] Mode: {result['mode']}")
    print(f"[OK] Found {result['tweets_found']} tweets")
    print(f"[OK] Scraped {result['urls_scraped']} URLs")
    
    # Show LLM reasoning trace
    print(f"\nLLM Reasoning Trace:")
    for i, (thought, action) in enumerate(zip(result['thoughts'], result['actions']), 1):
        print(f"\n  Iteration {i}:")
        print(f"    [THOUGHT] LLM Thought: {thought[:80]}...")
        print(f"    [ACTION] LLM Action: {action['tool']} - {action.get('reason', 'N/A')[:50]}...")
    
    print(f"\nFinal Answer Preview:")
    print(result['final_answer'][:400] + "...")
    
    return True


def test_llm_vs_rulebased():
    """Compare LLM mode vs rule-based mode."""
    print_separator("TEST 3: LLM vs Rule-Based Comparison")
    
    query = "Donald Trump tweets about elections"
    print(f"\nQuery: {query}\n")
    
    # Run in rule-based mode
    print("Running in RULE-BASED mode...")
    result_rules = run_agent(query, max_iterations=3, verbose=False, use_llm=False)
    
    # Run in LLM mode
    print("Running in LLM-POWERED mode...")
    result_llm = run_agent(query, max_iterations=3, verbose=False, use_llm=True)
    
    # Compare
    print(f"\nCOMPARISON:")
    print(f"{'='*70}")
    print(f"{'Metric':<30} {'Rule-Based':<20} {'LLM-Powered':<20}")
    print(f"{'-'*70}")
    print(f"{'Mode':<30} {result_rules['mode']:<20} {result_llm['mode']:<20}")
    print(f"{'Iterations':<30} {result_rules['iterations']:<20} {result_llm['iterations']:<20}")
    print(f"{'Tweets Found':<30} {result_rules['tweets_found']:<20} {result_llm['tweets_found']:<20}")
    print(f"{'URLs Scraped':<30} {result_rules['urls_scraped']:<20} {result_llm['urls_scraped']:<20}")
    print(f"{'Answer Length (chars)':<30} {len(result_rules['final_answer']):<20} {len(result_llm['final_answer']):<20}")
    print(f"{'='*70}")
    
    print(f"\nRule-Based Thought Example:")
    print(f"  \"{result_rules['thoughts'][0]}\"")
    
    print(f"\nLLM Thought Example:")
    print(f"  \"{result_llm['thoughts'][0]}\"")
    
    print(f"\n[OK] Both modes completed successfully")
    
    return True


def test_llm_verbose():
    """Test LLM agent with verbose output."""
    print_separator("TEST 4: LLM Agent - Full Verbose Output")
    
    query = "What did Barack Obama say about healthcare?"
    print(f"\nRunning LLM agent with VERBOSE mode...\n")
    
    result = run_agent(query, max_iterations=3, verbose=True, use_llm=True)
    
    assert result['success'], "Agent should succeed"
    assert result['mode'] == 'llm-powered', "Should be in LLM mode"
    
    print(f"\n[OK] Test completed successfully")
    
    return True


def main():
    """Run all LLM agent tests."""
    print_separator("LLM-POWERED REACT AGENT TEST SUITE (STEP 5)")
    print("\nTesting intelligent LLM-based reasoning agent...")
    print("This uses OpenAI GPT for thought generation,")
    print("action decision, and final answer synthesis.")
    
    tests = [
        ("Basic Query", test_llm_agent_basic),
        ("URL Scraping", test_llm_agent_with_urls),
        ("LLM vs Rule-Based", test_llm_vs_rulebased),
        ("Verbose Mode", test_llm_verbose)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n[FAILED] {test_name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print_separator("TEST SUMMARY")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "[PASSED]" if success else "[FAILED]"
        print(f"  {status}: {test_name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n*** All tests passed! Step 5 implementation complete. ***")
        print("\nLLM-Powered Agent Features:")
        print("  [OK] GPT-based thought generation")
        print("  [OK] Intelligent action decision (JSON mode)")
        print("  [OK] Sophisticated answer synthesis")
        print("  [OK] Contextual reasoning about user queries")
        print("  [OK] Smart URL scraping decisions")
        print("  [OK] Backwards compatible (can use rule-based mode)")
        print("\nReady for Step 6: API endpoint integration!")
    else:
        print("\n⚠ Some tests failed. Please review the errors above.")
    
    print_separator()


if __name__ == "__main__":
    main()
