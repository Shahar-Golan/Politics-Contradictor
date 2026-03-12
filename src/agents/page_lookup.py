"""
Page Lookup Agent
Checks pre-built figure pages in Supabase for cached answers.
Stub implementation until Phase 4 (Page Builder).
"""


def lookup_page(query: str) -> dict:
    """
    Search figure_pages in Supabase for a cached answer.

    Returns:
        dict: {"found": bool, "content": str | None, "figure": str | None}
    """
    # Phase 4 stub — always returns insufficient
    # Will be replaced with real Supabase lookup when figure_pages table exists
    return {
        "found": False,
        "content": None,
        "figure": None,
    }
