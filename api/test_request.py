import requests
import json

# Test Render deployment
url = "https://politics-contradictor.onrender.com/api/prompt"

# Multiple test queries
test_queries = [
    "What did Donald Trump say?",
    "immigration",
]

for query in test_queries:
    payload = {"question": query}
    try:
        print(f"\n{'='*60}")
        print(f"QUERY: {query}")
        print(f"{'='*60}")
        print("Waiting for Render (may take 50+ seconds if service is sleeping)...")
        response = requests.post(url, json=payload, timeout=90)

        if response.status_code == 200:
            result = response.json()
            print(f"\nRESPONSE: {result['response']}")
            print(f"\nCONTEXT COUNT: {len(result['context'])} tweets")
            if result['context']:
                print("\nTOP 3 TWEETS RETRIEVED:")
                for i, tweet in enumerate(result['context'][:3], 1):
                    print(f"  {i}. {tweet['author_name']} (score: {tweet['score']:.4f})")
                    print(f"     {tweet['text'][:100]}...")
        else:
            print(f"Error (Status {response.status_code}):", response.text)

    except Exception as e:
        print(f"Failed to connect: {e}")
        print("Make sure the Flask server is running (python api/index.py)")
        break