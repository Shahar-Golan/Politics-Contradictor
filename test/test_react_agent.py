"""
Test ReAct Agent Framework (Step 4)
Tests the rule-based ReAct agent implementation.
"""

import sys
from pathlib import Path

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


def test_agent_basic_query():
    """Test agent with a basic query (tweets without URLs)."""
    print_separator("TEST 1: Basic Query (Tweets Only)")
    
    query = "What did Hillary Clinton say about immigration?"
    print(f"\nQuery: {query}\n")
    
    result = run_agent(query, max_iterations=3, verbose=False)
    
    # Verify results
    assert result['success'], "Agent should succeed"
    assert result['tweets_found'] > 0, "Should find tweets"
    assert len(result['thoughts']) > 0, "Should have thoughts"
    assert len(result['actions']) > 0, "Should have actions"
    assert len(result['observations']) > 0, "Should have observations"
    assert result['final_answer'], "Should have final answer"
    
    print(f"✓ Agent completed in {result['iterations']} iterations")
    print(f"✓ Found {result['tweets_found']} tweets")
    print(f"✓ Scraped {result['urls_scraped']} URLs")
    print(f"\nFinal Answer Preview:")
    print(result['final_answer'][:300] + "...")
    
    return True


def test_agent_with_urls():
    """Test agent with a query that should trigger URL scraping."""
    print_separator("TEST 2: Query with URL Scraping")
    
    query = "What climate challenge did Bill Gates tweet about?"
    print(f"\nQuery: {query}\n")
    
    result = run_agent(query, max_iterations=5, verbose=False)
    
    # Verify results
    assert result['success'], "Agent should succeed"
    assert result['tweets_found'] > 0, "Should find tweets"
    assert result['iterations'] > 1, "Should take multiple iterations"
    
    print(f"✓ Agent completed in {result['iterations']} iterations")
    print(f"✓ Found {result['tweets_found']} tweets")
    print(f"✓ Scraped {result['urls_scraped']} URLs")
    
    # Show the ReAct trace
    print(f"\nReAct Trace:")
    for i, (thought, action, obs) in enumerate(zip(
        result['thoughts'], 
        result['actions'], 
        result['observations']
    ), 1):
        print(f"\n  Iteration {i}:")
        print(f"    💭 Thought: {thought[:80]}...")
        print(f"    🔧 Action: {action['tool']}")
        print(f"    👁️  Observation: {obs[:80]}...")
    
    print(f"\nFinal Answer Preview:")
    print(result['final_answer'][:300] + "...")
    
    return True


def test_agent_verbose():
    """Test agent with verbose output to see full ReAct loop."""
    print_separator("TEST 3: Full Verbose ReAct Loop")
    
    query = "Donald Trump tweets about elections"
    print(f"\nRunning agent with VERBOSE mode...\n")
    
    result = run_agent(query, max_iterations=3, verbose=True)
    
    assert result['success'], "Agent should succeed"
    
    print(f"\n✓ Test completed successfully")
    
    return True


def test_agent_state():
    """Test that agent state is properly maintained."""
    print_separator("TEST 4: Agent State Management")
    
    query = "What did Barack Obama say about healthcare?"
    
    result = run_agent(query, max_iterations=3, verbose=False)
    
    # Verify state consistency
    assert len(result['thoughts']) == len(result['actions']), \
        "Should have equal thoughts and actions"
    assert len(result['actions']) == len(result['observations']), \
        "Should have equal actions and observations"
    assert result['iterations'] <= 3, \
        "Should not exceed max iterations"
    
    print(f"✓ Agent state properly maintained")
    print(f"  - Thoughts: {len(result['thoughts'])}")
    print(f"  - Actions: {len(result['actions'])}")
    print(f"  - Observations: {len(result['observations'])}")
    print(f"  - Iterations: {result['iterations']}")
    print(f"  - Tweets: {result['tweets_found']}")
    print(f"  - URLs scraped: {result['urls_scraped']}")
    
    return True


def main():
    """Run all agent tests."""
    print_separator("REACT AGENT TEST SUITE (STEP 4)")
    print("\nTesting rule-based ReAct agent framework...")
    print("(Step 5 will add LLM-based thought generation)")
    
    tests = [
        ("Basic Query", test_agent_basic_query),
        ("URL Scraping", test_agent_with_urls),
        ("Verbose Mode", test_agent_verbose),
        ("State Management", test_agent_state)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n✗ {test_name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print_separator("TEST SUMMARY")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"  {status}: {test_name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Step 4 implementation complete.")
        print("\nReAct Agent Features:")
        print("  ✓ AgentState tracks full conversation")
        print("  ✓ Thought generation (rule-based)")
        print("  ✓ Action decision logic")
        print("  ✓ Tool execution (vector_search, web_scraper)")
        print("  ✓ Observation collection")
        print("  ✓ Automatic finalization logic")
        print("  ✓ Final answer synthesis")
        print("\nReady for Step 5: LLM-based thought generation!")
    else:
        print("\n⚠ Some tests failed. Please review the errors above.")
    
    print_separator()


if __name__ == "__main__":
    main()
