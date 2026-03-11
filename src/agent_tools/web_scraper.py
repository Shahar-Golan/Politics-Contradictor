"""
Web Scraper Tool
Fetches and extracts content from URLs found in tweets.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import re
from typing import Optional


def expand_twitter_url(short_url: str, timeout: int = 10) -> str:
    """
    Expand shortened URLs (like t.co links).
    
    Args:
        short_url (str): The shortened URL
        timeout (int): Request timeout in seconds
    
    Returns:
        str: The expanded URL or original if expansion fails
    """
    try:
        response = requests.head(
            short_url,
            allow_redirects=True,
            timeout=timeout,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        return response.url
    except Exception:
        return short_url


def clean_html_to_text(html_content: str) -> str:
    """
    Convert HTML to clean text with minimal formatting.
    
    Args:
        html_content (str): Raw HTML content
    
    Returns:
        str: Cleaned text content
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()
    
    # Get text
    text = soup.get_text(separator='\n')
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return text


def extract_statistics(text: str) -> dict:
    """
    Extract numerical statistics from text.
    
    Args:
        text (str): Text to analyze
    
    Returns:
        dict: Dictionary with statistics found
    """
    stats = {
        "has_numbers": False,
        "percentages": [],
        "numbers_with_units": [],
        "dates": []
    }
    
    # Find percentages
    percentages = re.findall(r'\d+(?:\.\d+)?%', text)
    if percentages:
        stats["percentages"] = percentages[:5]  # Limit to 5
        stats["has_numbers"] = True
    
    # Find numbers with common units
    numbers_with_units = re.findall(
        r'\d+(?:,\d{3})*(?:\.\d+)?\s*(?:million|billion|thousand|trillion|dollars?|\$|€|£|people|users|votes)',
        text,
        re.IGNORECASE
    )
    if numbers_with_units:
        stats["numbers_with_units"] = numbers_with_units[:5]
        stats["has_numbers"] = True
    
    # Find dates
    dates = re.findall(r'\b\d{4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b', text)
    if dates:
        stats["dates"] = dates[:3]
    
    return stats


def web_scraper(url: str, timeout: int = 15, expand_shortened: bool = True) -> dict:
    """
    Fetch and extract content from a URL.
    
    Args:
        url (str): The URL to scrape
        timeout (int): Request timeout in seconds (default: 15)
        expand_shortened (bool): Whether to expand shortened URLs (default: True)
    
    Returns:
        dict: Scraped content with the following structure:
            {
                "success": bool,
                "url": str,  # Original URL
                "expanded_url": str,  # Expanded URL (if applicable)
                "title": str,
                "content": str,  # Main text content
                "content_preview": str,  # First 500 chars
                "statistics": dict,  # Extracted statistics
                "word_count": int,
                "error": str | None
            }
    """
    result = {
        "success": False,
        "url": url,
        "expanded_url": url,
        "title": "",
        "content": "",
        "content_preview": "",
        "statistics": {},
        "word_count": 0,
        "error": None
    }
    
    try:
        # Expand shortened URLs if requested
        if expand_shortened and ('t.co' in url or 'bit.ly' in url or 'tinyurl' in url):
            result["expanded_url"] = expand_twitter_url(url, timeout=5)
        
        # Fetch the page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(
            result["expanded_url"],
            timeout=timeout,
            headers=headers,
            allow_redirects=True
        )
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            result["title"] = title_tag.get_text().strip()
        
        # Try to find main content (look for article, main, or body)
        main_content = None
        for tag in ['article', 'main', '[role="main"]', '.content', '#content']:
            main_content = soup.select_one(tag)
            if main_content:
                break
        
        if not main_content:
            main_content = soup.find('body')
        
        # Extract and clean text
        if main_content:
            html_str = str(main_content)
            result["content"] = clean_html_to_text(html_str)
        else:
            result["content"] = clean_html_to_text(response.text)
        
        # Limit content length (keep first 5000 chars)
        if len(result["content"]) > 5000:
            result["content"] = result["content"][:5000] + "... [truncated]"
        
        # Content preview
        result["content_preview"] = result["content"][:500] + "..." if len(result["content"]) > 500 else result["content"]
        
        # Word count
        result["word_count"] = len(result["content"].split())
        
        # Extract statistics
        result["statistics"] = extract_statistics(result["content"])
        
        result["success"] = True
        
    except requests.exceptions.Timeout:
        result["error"] = f"Request timed out after {timeout} seconds"
    except requests.exceptions.HTTPError as e:
        result["error"] = f"HTTP error: {e.response.status_code}"
    except requests.exceptions.RequestException as e:
        result["error"] = f"Request failed: {str(e)}"
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
    
    return result


if __name__ == "__main__":
    # Test the web scraper
    test_urls = [
        "https://www.example.com",  # Simple test
        "https://www.wikipedia.org/wiki/Climate_change"  # Real content
    ]
    
    for url in test_urls:
        print(f"\nTesting web_scraper with URL: {url}")
        print("=" * 60)
        
        result = web_scraper(url, timeout=10)
        
        if result["success"]:
            print(f"✓ Successfully scraped")
            print(f"   Title: {result['title']}")
            print(f"   Word Count: {result['word_count']}")
            print(f"   Statistics Found: {result['statistics']['has_numbers']}")
            print(f"   Preview: {result['content_preview'][:150]}...")
        else:
            print(f"✗ Error: {result['error']}")
