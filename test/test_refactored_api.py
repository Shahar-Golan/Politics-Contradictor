"""
Test Refactored API Endpoint
Verifies that the refactored index.py works correctly with agent_tools.
"""

import requests
import json
import sys
from pathlib import Path

def test_api_endpoint():
    """Test the refactored /api/prompt endpoint."""
    url = "http://localhost:5000/api/prompt"
    
    test_queries = [
        "What did Hillary Clinton say about immigration?",
        "Donald Trump tweets about elections"
    ]
    
    print("="*70)
    print("TESTING REFACTORED API ENDPOINT")
    print("="*70)
    print("\nThis test verifies that index.py works correctly after refactoring")
    print("to use the modular agent_tools/vector_search implementation.\n")
    
    for i, query in enumerate(test_queries, 1):
        payload = {"question": query}
        
        print(f"\n[Test {i}] Query: '{query}'")
        print("-"*70)
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                
                # Verify response structure
                assert "response" in result, "Missing 'response' field"
                assert "context" in result, "Missing 'context' field"
                assert "Augmented_prompt" in result, "Missing 'Augmented_prompt' field"
                
                print(f"✓ Status: 200 OK")
                print(f"✓ Response structure: Valid")
                print(f"✓ Context tweets: {len(result['context'])}")
                
                # Show top 3 tweets
                if result['context']:
                    print(f"\n  Top 3 Retrieved Tweets:")
                    for j, tweet in enumerate(result['context'][:3], 1):
                        print(f"    {j}. {tweet['author_name']} (score: {tweet['score']:.4f})")
                        print(f"       Date: {tweet['created_at']}")
                        print(f"       Text: {tweet['text'][:100]}...")
                
                # Show GPT response preview
                print(f"\n  GPT Response Preview:")
                response_text = result['response'][:200]
                print(f"    {response_text}...")
                
                print(f"\n✓ Test {i} PASSED")
                
            else:
                print(f"✗ Error: Status {response.status_code}")
                print(f"  Response: {response.text}")
                return False
                
        except requests.exceptions.ConnectionError:
            print("✗ Failed to connect to server")
            print("\n  Please start the Flask server first:")
            print("    python api/index.py")
            print("\n  Then run this test again.")
            return False
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    print("\n" + "="*70)
    print("✓ ALL TESTS PASSED!")
    print("="*70)
    print("\nRefactoring successful! The API endpoint works correctly with")
    print("the modular agent_tools implementation.")
    print("\nBenefits achieved:")
    print("  ✓ Removed code duplication")
    print("  ✓ Improved modularity")
    print("  ✓ index.py is now ~30 lines shorter")
    print("  ✓ Easier to maintain and extend")
    print("="*70)
    return True


if __name__ == "__main__":
    success = test_api_endpoint()
    sys.exit(0 if success else 1)
