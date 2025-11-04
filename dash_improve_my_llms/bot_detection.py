"""
Bot detection utilities for identifying AI crawlers.

This module provides functionality to detect and classify different types
of bots (AI training, AI search, traditional search engines) from user agents.
"""

from typing import List

# Comprehensive list of known AI bot user agents
AI_TRAINING_BOTS = [
    "gptbot",  # OpenAI training
    "anthropic-ai",  # Anthropic training
    "claude-web",  # Anthropic training
    "ccbot",  # Common Crawl
    "google-extended",  # Google Gemini training
    "omgili",  # Omgili
    "omgilibot",  # Omgili
    "bytespider",  # ByteDance/TikTok
    "facebookbot",  # Meta AI training
]

AI_SEARCH_BOTS = [
    "chatgpt-user",  # ChatGPT browsing
    "oai-searchbot",  # OpenAI search
    "claudebot",  # Claude search/citation
    "perplexitybot",  # Perplexity search
]

TRADITIONAL_BOTS = [
    "googlebot",  # Google Search
    "bingbot",  # Bing Search
    "slurp",  # Yahoo
    "duckduckbot",  # DuckDuckGo
]


def is_ai_training_bot(user_agent: str) -> bool:
    """
    Check if request is from an AI training crawler.

    Args:
        user_agent: User agent string from request headers

    Returns:
        True if the user agent matches known AI training bots
    """
    ua_lower = user_agent.lower()
    return any(bot in ua_lower for bot in AI_TRAINING_BOTS)


def is_ai_search_bot(user_agent: str) -> bool:
    """
    Check if request is from an AI search/citation crawler.

    Args:
        user_agent: User agent string from request headers

    Returns:
        True if the user agent matches known AI search bots
    """
    ua_lower = user_agent.lower()
    return any(bot in ua_lower for bot in AI_SEARCH_BOTS)


def is_traditional_bot(user_agent: str) -> bool:
    """
    Check if request is from a traditional search engine bot.

    Args:
        user_agent: User agent string from request headers

    Returns:
        True if the user agent matches known traditional search bots
    """
    ua_lower = user_agent.lower()
    return any(bot in ua_lower for bot in TRADITIONAL_BOTS)


def is_any_bot(user_agent: str) -> bool:
    """
    Check if request is from any bot (AI or traditional).

    Args:
        user_agent: User agent string from request headers

    Returns:
        True if the user agent matches any known bot
    """
    ua_lower = user_agent.lower()
    all_bots = AI_TRAINING_BOTS + AI_SEARCH_BOTS + TRADITIONAL_BOTS
    return any(bot in ua_lower for bot in all_bots)


def get_bot_type(user_agent: str) -> str:
    """
    Identify bot type from user agent.

    Args:
        user_agent: User agent string from request headers

    Returns:
        One of: 'training', 'search', 'traditional', or 'unknown'
    """
    if is_ai_training_bot(user_agent):
        return "training"
    elif is_ai_search_bot(user_agent):
        return "search"
    elif is_traditional_bot(user_agent):
        return "traditional"
    return "unknown"


def get_all_bot_lists() -> dict:
    """
    Get all bot lists for reference.

    Returns:
        Dictionary with bot categories and their lists
    """
    return {
        "training": AI_TRAINING_BOTS,
        "search": AI_SEARCH_BOTS,
        "traditional": TRADITIONAL_BOTS,
    }