"""
Agent Prompts
System and user prompts for the ReAct agent's LLM interface.
"""

# System prompt for the ReAct agent
SYSTEM_PROMPT = """You are an X-Platform Intelligence Agent analyzing tweets and their linked content.

Your role is to help users understand what public figures have said on social media by intelligently searching tweets and investigating linked content.

AVAILABLE TOOLS:
1. vector_search(query, top_k) - Search Pinecone vector database for relevant tweets
   - Use this to find tweets related to the user's question
   - Returns: tweets with metadata (id, text, author_name, created_at, has_urls)

2. web_scraper(url) - Extract and analyze content from URLs found in tweets
   - Use this when tweets contain URLs (has_urls=true) and you need the full context
   - Returns: page title, content, statistics found
   - IMPORTANT: Don't scrape the same URL twice!

3. finalize() - Stop reasoning and generate final answer
   - Use when you have sufficient information to answer the user's query

DATA STRUCTURE:
- Tweets contain: id, text, author_name, created_at, has_urls (boolean)
- When has_urls=true, the tweet text contains URLs that may provide additional context
- You can use the extract_urls function to get URLs from tweet text

REACT FRAMEWORK:
You follow the ReAct (Reasoning + Acting) framework:
1. THOUGHT: Analyze the current situation and decide what information you need
2. ACTION: Choose which tool to use and with what parameters
3. OBSERVATION: Review the results from your action
4. REPEAT steps 1-3 if needed, or proceed to FINAL ANSWER

GUIDELINES:
- Always start by searching for relevant tweets using vector_search
- If tweets contain URLs (has_urls=true) and the query asks for details/content/statistics, scrape those URLs
- Don't scrape the same URL twice - check the scraped_urls list
- Balance thoroughness with efficiency - don't scrape unnecessary URLs
- Generate concise, evidence-based answers with proper attribution
- Include clickable URLs in your final answer when relevant
- If information is insufficient, acknowledge limitations rather than speculating

Remember: You are analyzing real tweets from public figures. Be accurate and cite your sources clearly."""


# Thought generation prompt template
THOUGHT_PROMPT_TEMPLATE = """You are in iteration {iteration} of analyzing the user's query.

USER QUERY: {user_query}

CURRENT STATE:
- Tweets retrieved: {tweets_count}
- URLs scraped: {urls_scraped_count}
- Scraped URLs list: {scraped_urls}

PREVIOUS THOUGHTS AND ACTIONS:
{history}

LATEST OBSERVATION:
{latest_observation}

Based on this information, what should you do next? Think step by step:
1. Do you have enough information to answer the query?
2. If not, what additional information do you need?
3. Which tool should you use next?

Provide your reasoning in 2-3 sentences."""


# Action decision prompt template
ACTION_PROMPT_TEMPLATE = """Based on your thought: "{thought}"

Current state:
- Tweets retrieved: {tweets_count}
- Tweets with URLs: {tweets_with_urls}
- URLs already scraped: {scraped_urls}

Available actions:
1. vector_search - Search for tweets (if not done yet or need different search)
2. web_scraper - Scrape a URL from a tweet (if has_urls=true and URL not yet scraped)
3. finalize - Generate final answer (if you have sufficient information)

Choose your next action and respond in valid JSON format:
{{
    "tool": "vector_search" | "web_scraper" | "finalize",
    "parameters": {{"query": "search query", "top_k": 10}} OR {{"url": "https://..."}} OR {{}},
    "reason": "Brief explanation of why you chose this action"
}}

IMPORTANT: 
- Respond ONLY with valid JSON
- For vector_search, include "query" and "top_k" in parameters
- For web_scraper, include "url" in parameters
- For finalize, parameters should be empty {{}}
- Don't scrape URLs that are already in the scraped list"""


# Final answer generation prompt template
FINAL_ANSWER_PROMPT_TEMPLATE = """You have completed your investigation. Now synthesize all the information you've gathered into a comprehensive answer.

USER QUERY: {user_query}

TWEETS RETRIEVED ({tweets_count} total):
{tweets_summary}

SCRAPED WEB CONTENT ({scraped_count} total):
{scraped_summary}

Generate a well-structured final answer that:
1. Directly answers the user's query
2. Cites specific tweets with author names and dates
3. Incorporates information from scraped web pages when relevant
4. Includes clickable URLs for the user to verify sources
5. Is concise but comprehensive (3-5 paragraphs)
6. Uses markdown formatting for readability

Format your answer with:
- **Bold** for emphasis on key points
- Direct quotes from tweets when applicable
- 🔗 emoji before URLs
- Clear attribution (Author - Date: "quote")

If the information is insufficient or ambiguous, acknowledge this clearly."""


def get_thought_prompt(state) -> str:
    """
    Generate the prompt for thought generation.
    
    Args:
        state: AgentState object
    
    Returns:
        str: Formatted prompt for the LLM
    """
    # Build history
    history = ""
    for i, (thought, action, obs) in enumerate(zip(
        state.thoughts, state.actions, state.observations
    ), 1):
        history += f"\nIteration {i}:\n"
        history += f"  Thought: {thought}\n"
        history += f"  Action: {action['tool']} - {action.get('reason', '')}\n"
        history += f"  Observation: {obs[:150]}...\n"
    
    if not history:
        history = "This is the first iteration. No previous actions taken."
    
    latest_obs = state.observations[-1] if state.observations else "No observations yet."
    
    return THOUGHT_PROMPT_TEMPLATE.format(
        iteration=state.current_iteration + 1,
        user_query=state.user_query,
        tweets_count=len(state.tweets_retrieved),
        urls_scraped_count=len(state.scraped_urls),
        scraped_urls=list(state.scraped_urls) if state.scraped_urls else "None",
        history=history,
        latest_observation=latest_obs
    )


def get_action_prompt(thought: str, state) -> str:
    """
    Generate the prompt for action decision.
    
    Args:
        thought (str): The current thought
        state: AgentState object
    
    Returns:
        str: Formatted prompt for the LLM
    """
    # Count tweets with URLs
    tweets_with_urls = []
    for tweet in state.tweets_retrieved[:5]:  # Check top 5
        if tweet['metadata'].get('has_urls'):
            tweets_with_urls.append(tweet['metadata']['author_name'])
    
    return ACTION_PROMPT_TEMPLATE.format(
        thought=thought,
        tweets_count=len(state.tweets_retrieved),
        tweets_with_urls=", ".join(tweets_with_urls) if tweets_with_urls else "None",
        scraped_urls=list(state.scraped_urls) if state.scraped_urls else "None"
    )


def get_final_answer_prompt(state) -> str:
    """
    Generate the prompt for final answer synthesis.
    
    Args:
        state: AgentState object
    
    Returns:
        str: Formatted prompt for the LLM
    """
    # Format tweets summary
    tweets_summary = ""
    for i, tweet in enumerate(state.tweets_retrieved[:7], 1):
        meta = tweet['metadata']
        tweets_summary += f"\n{i}. {meta.get('author_name')} ({meta.get('created_at')}):\n"
        tweets_summary += f"   \"{meta.get('text', '')[:200]}...\"\n"
        tweets_summary += f"   Score: {tweet['score']:.4f}, Has URLs: {meta.get('has_urls', False)}\n"
    
    # Format scraped content summary
    scraped_summary = ""
    if state.scraped_content:
        for i, content in enumerate(state.scraped_content, 1):
            scraped_summary += f"\n{i}. URL: {content['url']}\n"
            scraped_summary += f"   Title: {content['title']}\n"
            scraped_summary += f"   Preview: {content['content_preview'][:200]}...\n"
            if content['statistics'].get('has_numbers'):
                scraped_summary += f"   Contains statistics: Yes\n"
    else:
        scraped_summary = "No web content was scraped."
    
    return FINAL_ANSWER_PROMPT_TEMPLATE.format(
        user_query=state.user_query,
        tweets_count=len(state.tweets_retrieved),
        tweets_summary=tweets_summary,
        scraped_count=len(state.scraped_content),
        scraped_summary=scraped_summary
    )
