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


# ---------------------------------------------------------------------------
# 2.8 — positive browser identification, and the one classification fold.
# ---------------------------------------------------------------------------

# Through 2.7.x an unrecognised client was assumed to be a person and was
# handed the JavaScript shell. For a package whose whole thesis is machine
# readers that default is backwards: `httpx`, `aiohttp`, `node-fetch`,
# `Go-http-client` and an absent User-agent are overwhelmingly programs,
# and a program that receives the shell receives nothing at all. So 2.8
# asks the positive question instead — is this a BROWSER? — and treats
# everything else as a reader.
#
# A browser sends `Mozilla/` and an engine token. That is a low bar by
# design: the cost of a false "browser" is one agent getting the shell (the
# old behaviour for everyone), while the cost of a false "crawler" is a
# person seeing static HTML, which is the more visible failure.
_BROWSER_ENGINE_TOKENS = (
    "applewebkit",
    "gecko/",
    "trident",
    "edg/",
    "chrome/",
    "safari/",
    "firefox/",
)


def is_browser_ua(user_agent: str) -> bool:
    """True when the User-agent positively identifies a web browser.

    NOT the complement of ``is_any_bot()``: most AI crawlers also send
    ``Mozilla/5.0 ... AppleWebKit ...`` for compatibility, so this must
    only ever be consulted AFTER vendor and generic-bot matching have both
    failed. ``classify()`` enforces that order; callers should prefer it.
    """
    if not user_agent:
        return False
    ua_lower = user_agent.lower()
    if "mozilla/" not in ua_lower:
        return False
    return any(token in ua_lower for token in _BROWSER_ENGINE_TOKENS)


def classify(user_agent: str, client_ip: Optional[str] = None) -> dict:
    """The one classification fold — who is asking, and on which lane.

    This is *the* entry point for classifying a request, and the reason it
    exists is that it was not there before: with only the predicates on
    offer, every consumer that needed a vendor name wrote its own
    User-agent list, and those lists drifted from this registry in both
    directions. An application should call this once and use the result
    rather than maintaining lists of its own.

    Args:
        user_agent: The raw ``User-agent`` header, possibly empty.
        client_ip: The client address, when the caller has one. Only used
            for ``verified``; omitting it costs nothing else.

    Returns a dict with:
        ``bot_type``      ``training`` | ``search`` | ``traditional`` |
                          ``unknown``, or ``None`` for an identified browser.
        ``vendor_key``    registry key, or ``None``.
        ``vendor_class``  the vendor's class, or ``None`` when no vendor
                          matched (a generic ``bot`` token gives a
                          ``bot_type`` but no ``vendor_class``).
        ``verified``      ``verified`` | ``unverified`` | ``n/a`` — see
                          ``_identity``. Never affects the lane.
        ``lane``          ``crawler`` | ``browser``. What this UA gets by
                          identity alone; per-vendor POLICY can still turn
                          a crawler lane into a 403, which is
                          ``handle_bot_request``'s decision, not this one.
    """
    vendor_key = get_bot_vendor(user_agent)
    vendor = get_vendor(vendor_key) if vendor_key else None
    vendor_class = vendor.cls if vendor is not None else None

    bot_type: Optional[str] = get_bot_type(user_agent)
    if bot_type == "unknown" and is_browser_ua(user_agent):
        # An identified browser is the one case with no bot_type at all.
        bot_type = None
        lane = "browser"
    else:
        # Vendors, generic bots, AND the unidentified all read as crawlers.
        lane = "crawler"

    from ._identity import verify

    return {
        "bot_type": bot_type,
        "vendor_key": vendor_key,
        "vendor_class": vendor_class,
        "verified": verify(vendor_key, client_ip),
        "lane": lane,
    }


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
