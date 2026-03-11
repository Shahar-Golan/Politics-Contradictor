"""
URL Extractor Tool
Extracts URLs from tweet text.
"""

import re
from typing import List


def extract_urls(tweet_text: str) -> List[str]:
    """
    Extract URLs from tweet text.
    
    Args:
        tweet_text (str): The tweet text to extract URLs from
    
    Returns:
        List[str]: List of unique URLs found in the tweet
    
    Examples:
        >>> extract_urls("Check this out https://example.com and https://test.com")
        ['https://example.com', 'https://test.com']
        
        >>> extract_urls("No URLs here!")
        []
    """
    if not tweet_text:
        return []
    
    # URL pattern - matches http:// and https:// URLs
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    
    # Find all URLs
    urls = re.findall(url_pattern, tweet_text)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        # Clean up trailing punctuation that might be part of sentence
        url = url.rstrip('.,;:!?)')
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls


def has_urls(tweet_text: str) -> bool:
    """
    Check if tweet text contains any URLs.
    
    Args:
        tweet_text (str): The tweet text to check
    
    Returns:
        bool: True if URLs are found, False otherwise
    """
    return len(extract_urls(tweet_text)) > 0


def count_urls(tweet_text: str) -> int:
    """
    Count the number of unique URLs in tweet text.
    
    Args:
        tweet_text (str): The tweet text to analyze
    
    Returns:
        int: Number of unique URLs found
    """
    return len(extract_urls(tweet_text))


def extract_twitter_shortened_urls(tweet_text: str) -> List[str]:
    """
    Extract specifically Twitter shortened (t.co) URLs from tweet text.
    
    Args:
        tweet_text (str): The tweet text to extract from
    
    Returns:
        List[str]: List of t.co URLs found
    """
    if not tweet_text:
        return []
    
    # Pattern for t.co URLs
    tco_pattern = r'https?://t\.co/[a-zA-Z0-9]+'
    
    urls = re.findall(tco_pattern, tweet_text)
    
    # Remove duplicates
    return list(set(urls))


if __name__ == "__main__":
    # Test the URL extractor
    test_tweets = [
        "Check out this article https://example.com about climate change!",
        "Multiple links: https://example.com and https://test.com #news",
        "Shortened Twitter link: https://t.co/abc123XYZ",
        "No links in this tweet!",
        "Link with punctuation at end https://example.com.",
        "Same link twice https://example.com and https://example.com"
    ]
    
    print("Testing URL Extractor")
    print("=" * 60)
    
    for i, tweet in enumerate(test_tweets, 1):
        print(f"\nTest {i}: {tweet}")
        urls = extract_urls(tweet)
        print(f"   URLs found: {urls}")
        print(f"   Has URLs: {has_urls(tweet)}")
        print(f"   Count: {count_urls(tweet)}")
        
        tco_urls = extract_twitter_shortened_urls(tweet)
        if tco_urls:
            print(f"   Twitter shortened: {tco_urls}")
