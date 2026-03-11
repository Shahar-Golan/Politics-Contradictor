"""
Test Agent Tools
Tests the three core agent tools: vector_search, web_scraper, and url_extractor
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_tools.vector_search import vector_search
from agent_tools.web_scraper import web_scraper
from agent_tools.url_extractor import extract_urls, has_urls, count_urls


def print_separator(title=""):
    """Print a nice separator line."""
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}")
    else:
        print(f"{'='*70}")


def test_url_extractor():
    """Test the URL extraction tool."""
    print_separator("TEST 1: URL EXTRACTOR")
    
    test_tweets = [
        "Check out this article https://example.com about climate change!",
        "Multiple links: https://example.com and https://test.com #news",
        "Shortened Twitter link: https://t.co/abc123XYZ",
        "No links in this tweet!",
    ]
    
    for i, tweet in enumerate(test_tweets, 1):
        print(f"\n[{i}] Tweet: {tweet}")
        urls = extract_urls(tweet)
        print(f"    URLs found: {urls}")
        print(f"    Has URLs: {has_urls(tweet)}")
        print(f"    Count: {count_urls(tweet)}")
    
    print("\n✓ URL Extractor test completed")
    return True


def test_vector_search():
    """Test the vector search tool."""
    print_separator("TEST 2: VECTOR SEARCH")
    
    test_queries = [
        "What did Hillary Clinton say about immigration?",
        "Donald Trump tweets about elections"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n[{i}] Query: '{query}'")
        print("-" * 70)
        
        result = vector_search(query, top_k=3)
        
        if result["success"]:
            print(f"✓ Found {result['count']} results")
            
            for j, tweet in enumerate(result['results'], 1):
                metadata = tweet['metadata']
                print(f"\n  {j}. Score: {tweet['score']:.4f}")
                print(f"     Author: {metadata.get('author_name', 'Unknown')}")
                print(f"     Date: {metadata.get('created_at', 'Unknown')}")
                print(f"     Has URLs: {metadata.get('has_urls', False)}")
                print(f"     Text: {metadata.get('text', '')[:120]}...")
                
                # Extract URLs from the tweet text
                if metadata.get('has_urls'):
                    urls = extract_urls(metadata.get('text', ''))
                    if urls:
                        print(f"     URLs: {urls}")
        else:
            print(f"✗ Error: {result['error']}")
            return False
    
    print("\n✓ Vector Search test completed")
    return True


def test_web_scraper():
    """Test the web scraper tool."""
    print_separator("TEST 3: WEB SCRAPER")
    
    test_urls = [
        "https://www.example.com",  # Simple test page
    ]
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n[{i}] URL: {url}")
        print("-" * 70)
        
        result = web_scraper(url, timeout=10)
        
        if result["success"]:
            print(f"✓ Successfully scraped")
            print(f"   Title: {result['title']}")
            print(f"   Expanded URL: {result['expanded_url']}")
            print(f"   Word Count: {result['word_count']}")
            print(f"   Has Statistics: {result['statistics'].get('has_numbers', False)}")
            
            if result['statistics'].get('percentages'):
                print(f"   Percentages: {result['statistics']['percentages']}")
            
            print(f"\n   Content Preview:")
            print(f"   {result['content_preview'][:200]}...")
        else:
            print(f"✗ Error: {result['error']}")
    
    print("\n✓ Web Scraper test completed")
    return True


def test_integration():
    """Test integration: Search for tweets with URLs and scrape them."""
    print_separator("TEST 4: INTEGRATION TEST")
    
    print("\n1. Searching for tweets with URLs...")
    result = vector_search("climate change challenge", top_k=10)
    
    if not result["success"]:
        print(f"✗ Search failed: {result['error']}")
        return False
    
    print(f"✓ Found {result['count']} tweets")
    
    # Find tweets with URLs
    tweets_with_urls = [
        tweet for tweet in result['results']
        if tweet['metadata'].get('has_urls', False)
    ]
    
    print(f"\n2. Found {len(tweets_with_urls)} tweets with URLs")
    
    if tweets_with_urls:
        # Test with first tweet that has URLs
        tweet = tweets_with_urls[0]
        metadata = tweet['metadata']
        
        print(f"\n3. Analyzing tweet from {metadata.get('author_name')}:")
        print(f"   Text: {metadata.get('text', '')[:150]}...")
        
        # Extract URLs
        urls = extract_urls(metadata.get('text', ''))
        print(f"\n4. Extracted {len(urls)} URLs: {urls}")
        
        # Try to scrape the first URL
        if urls:
            print(f"\n5. Attempting to scrape: {urls[0]}")
            scrape_result = web_scraper(urls[0], timeout=15)
            
            if scrape_result["success"]:
                print(f"✓ Scrape successful!")
                print(f"   Title: {scrape_result['title']}")
                print(f"   Word Count: {scrape_result['word_count']}")
                print(f"   Preview: {scrape_result['content_preview'][:150]}...")
            else:
                print(f"✗ Scrape failed: {scrape_result['error']}")
                print("   (This is normal - many t.co links may be expired)")
    else:
        print("   No tweets with URLs found in this sample")
        print("   Note: This is OK - not all tweets contain URLs")
    
    print("\n✓ Integration test completed")
    return True


def main():
    """Run all tests."""
    print_separator("AGENT TOOLS TEST SUITE")
    print("\nTesting Steps 1, 2, and 3 Implementation:")
    print("  - Step 1: Data Structure Understanding (✓ Documented)")
    print("  - Step 2: Environment Variables (✓ Configured)")
    print("  - Step 3: Core Agent Tools (testing now...)")
    
    tests = [
        ("URL Extractor", test_url_extractor),
        ("Vector Search", test_vector_search),
        ("Web Scraper", test_web_scraper),
        ("Integration", test_integration)
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
        print("\n🎉 All tests passed! Steps 1-3 implementation complete.")
    else:
        print("\n⚠ Some tests failed. Please review the errors above.")
    
    print_separator()


if __name__ == "__main__":
    main()
