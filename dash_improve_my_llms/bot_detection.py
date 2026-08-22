"""
Bot detection utilities for identifying AI crawlers.

Since 2.7.0 every vendor identity lives in ONE place — ``vendors.py`` —
and this module is a thin classification layer over it. Through 2.6.x
this file carried its own token lists, which drifted from robots.txt's
hand-written groups in both directions (defects P1–P3, see vendors.py's
module docstring); now both read the same registry and agreement holds by
construction.

Two matching tiers, in order:

1. **Vendor matching** (the registry) — runs FIRST, so an enumerated AI
   vendor is never swallowed by the generic fallback below (the P2 fix).
2. **Generic fallback** — ``bot``/``crawler``/``spider``/``scraper`` plus
   CLI tools, classifying as ``traditional`` exactly as 1.x did. This is
   what keeps an unenumerated crawler counted as a bot at all.

Contract change (2.7.0, deliberate): ``claudebot`` classifies
``training``, not ``search`` — robots.txt has disallowed ClaudeBot since
2.3.3 and the published promise is the side that stands (P1). The
named-human fetchers Claude-User / Claude-SearchBot / Perplexity-User
gained tokens and classify ``search`` (P3).
"""

from typing import Optional

from .vendors import (
    SEARCH,
    TRADITIONAL,
    TRAINING,
    get_bot_vendor,
    get_vendor,
    ua_tokens_of_class,
)

# Back-compat module-level lists: consumers (the demo site's crawler page,
# get_all_bot_lists, downstream apps) have imported these since 1.x. They
# are now DERIVED from the registry — edit vendors.py, never these.
AI_TRAINING_BOTS = ua_tokens_of_class(TRAINING)

AI_SEARCH_BOTS = ua_tokens_of_class(SEARCH)

# Generic patterns are not vendors: they identify "some bot" without
# saying whose. Matched only after vendor matching fails.
_GENERIC_BOT_TOKENS = [
    "bot",
    "crawler",
    "spider",
    "scraper",  # Generic patterns
    "curl",
    "wget",
    "python-requests",  # CLI tools
]

TRADITIONAL_BOTS = ua_tokens_of_class(TRADITIONAL) + _GENERIC_BOT_TOKENS


def _vendor_class(user_agent: str) -> Optional[str]:
    key = get_bot_vendor(user_agent)
    if key is None:
        return None
    vendor = get_vendor(key)
    return vendor.cls if vendor else None


def is_ai_training_bot(user_agent: str) -> bool:
    """
    Check if request is from an AI training crawler.

    Args:
        user_agent: User agent string from request headers

    Returns:
        True if the user agent matches a registry vendor of the
        training class
    """
    return _vendor_class(user_agent) == TRAINING


def is_ai_search_bot(user_agent: str) -> bool:
    """
    Check if request is from an AI search/citation crawler.

    Args:
        user_agent: User agent string from request headers

    Returns:
        True if the user agent matches a registry vendor of the
        search class
    """
    return _vendor_class(user_agent) == SEARCH


def is_traditional_bot(user_agent: str) -> bool:
    """
    Check if request is from a traditional search engine bot.

    Vendor matching runs first: an enumerated AI vendor whose UA happens
    to contain a generic token (they all do — "bot") is NOT traditional.

    Args:
        user_agent: User agent string from request headers

    Returns:
        True for a registry vendor of the traditional class, or any
        generic bot pattern with no vendor identity
    """
    cls = _vendor_class(user_agent)
    if cls is not None:
        return cls == TRADITIONAL
    ua_lower = user_agent.lower()
    return any(token in ua_lower for token in _GENERIC_BOT_TOKENS)


def is_any_bot(user_agent: str) -> bool:
    """
    Check if request is from any bot (AI or traditional).

    Args:
        user_agent: User agent string from request headers

    Returns:
        True if the user agent matches any registry vendor or generic
        bot pattern
    """
    if get_bot_vendor(user_agent) is not None:
        return True
    ua_lower = user_agent.lower()
    return any(token in ua_lower for token in _GENERIC_BOT_TOKENS)


def get_bot_type(user_agent: str) -> str:
    """
    Identify bot type from user agent.

    Args:
        user_agent: User agent string from request headers

    Returns:
        One of: 'training', 'search', 'traditional', or 'unknown'
    """
    cls = _vendor_class(user_agent)
    if cls is not None:
        return cls
    ua_lower = user_agent.lower()
    if any(token in ua_lower for token in _GENERIC_BOT_TOKENS):
        return TRADITIONAL
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
