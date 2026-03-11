"""
Quick test for Agent API endpoint
Run this after starting the Flask server: python api/index.py
"""
import requests
import json

# Configuration
API_URL = "http://localhost:5000/api/agent/query"

def test_agent_api():
    """Test the /api/agent/query endpoint"""
    
    print("=" * 70)
    print("TESTING AGENT API ENDPOINT")
    print("=" * 70)
    
    # Test query
    query = "What did Obama say about healthcare?"
    print(f"\nQuery: {query}")
    print("\nSending request to API...")
    
    try:
        response = requests.post(
            API_URL,
            json={"query": query},
            timeout=120  # Agent with LLM can take 60-90 seconds
        )
        
        if response.status_code == 200:
            data = response.json()
            
            print("\n" + "=" * 70)
            print("RESPONSE:")
            print("=" * 70)
            print(f"Mode: {data.get('mode')}")
            print(f"Iterations: {data.get('iterations')}")
            print(f"Tweets found: {data.get('tweets_found')}")
            print(f"URLs analyzed: {len(data.get('urls_analyzed', []))}")
            
            print(f"\nThought Process:")
            for i, thought in enumerate(data.get('thought_process', [])[:3], 1):
                print(f"  {i}. {thought[:100]}...")
            
            print(f"\nAnswer:")
            print(data.get('answer')[:500] + "...")
            
            print("\n" + "=" * 70)
            print("[PASSED] Agent API endpoint works!")
            print("=" * 70)
            return True
            
        else:
            print(f"\n[FAILED] Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Cannot connect to API!")
        print("Make sure Flask server is running:")
        print("  python api/index.py")
        return False
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False


if __name__ == "__main__":
    success = test_agent_api()
    exit(0 if success else 1)
