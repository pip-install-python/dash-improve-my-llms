"""Header normalization across the three backends — G0 of 2.7.0.

The enforcement seam (``handlers.handle_bot_request``) receives plain
data, never framework request objects — that purity is what lets one
handler serve Flask, FastAPI and Quart through three thin adapters. But
through 2.6.x the seam received only ``path`` and ``user_agent``, and two
2.7.0 features need more: the geo guardrail reads edge country headers,
and W4's rate limiter keys on the client IP. This module is the ONE
threading change that serves both — adapters call ``normalize_headers``
at their single ``handle_bot_request`` call site and pass the result as
the seam's ``headers=`` kwarg.

Private module: consumers inside the package only.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

# Proxy headers that carry the real client IP, most specific first. The
# first comma-separated value of X-Forwarded-For is the client; later
# hops append themselves. Mirrors the fleet's analytics tracker, which
# learned the hard way that behind Render/Cloudflare ``remote_addr`` is
# the proxy and every visitor collapses into one address.
_IP_HEADERS = (
    "cf-connecting-ip",  # Cloudflare
    "true-client-ip",  # Cloudflare Enterprise / Akamai
    "x-real-ip",  # nginx
    "x-forwarded-for",  # everything else
)


def normalize_headers(headers: Any) -> Dict[str, str]:
    """Any header mapping → a plain dict with lowercase str keys.

    Accepts Flask's ``EnvironHeaders``, Starlette's ``Headers``, Quart's
    headers, or a plain dict. Never raises — anything unreadable yields
    ``{}``, because a malformed header mapping must not take down the
    request path it decorates.
    """
    try:
        return {str(k).lower(): str(v) for k, v in headers.items()}
    except Exception:
        return {}


def client_ip(
    headers: Optional[Mapping[str, str]] = None,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """The real client IP behind proxies, or ``fallback``.

    Unused by the geo guardrail on purpose — geo does no network lookups
    and keys on country headers, not addresses. This exists for W4's rate
    limiter (and for custom geo ``resolver`` callables that consult their
    own IP database), so W4 adds no second threading change.
    """
    for name in _IP_HEADERS:
        raw = (headers or {}).get(name) or ""
        first = raw.split(",")[0].strip()
        if first:
            return first
    return fallback
