"""
Network bulletin — centrally-managed tips and announcements for the
human-facing ``llms.txt`` viewer.

A network of twenty documentation sites has no shared place to say "here is
what changed this week" without editing twenty repositories. This module
lets one host publish a small JSON document that every other site renders in
its ``llms.txt`` viewer header, so the message is written once.

Three properties this has to hold, because it puts a remote dependency in
front of a route that must always work:

**It never blocks a response.** Requests read whatever is in the cache and
return immediately. Refreshes happen on a daemon thread. A first-ever
request renders the banner without a bulletin rather than waiting for one.

**It never raises.** Every failure path — timeout, DNS, bad JSON, wrong
shape, hostile payload — degrades to "no bulletin". A documentation page
must not 500 because a sibling host is down.

**It is off unless you turn it on.** An open-source package that makes
outbound HTTP requests by default is a surprise nobody wants in their
deployment. Call :func:`configure_bulletin` to opt in.

The payload is treated as untrusted input. It arrives over the network, it
is rendered into HTML, and the host serving it is a separate deployment that
could be compromised independently of this one — so every field is length
capped and HTML-escaped at render time, and no field is ever interpreted as
markup.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["configure_bulletin", "get_bulletin", "BulletinConfig"]

# Caps applied to every remote string. Generous enough for real content,
# small enough that a hostile or broken endpoint cannot bloat a page.
_MAX_TITLE = 120
_MAX_BODY = 400
_MAX_ITEMS = 5

# W6: policy payload caps — hard ELEMENT caps in the _MAX_ITEMS taste, not
# just byte caps. The registry holds ~20 vendors; a hub bulletin that
# needs more than 8 tightenings at once is doing something the bulletin
# is not for.
_MAX_POLICY_ITEMS = 8
_MAX_PRICE_ITEMS = 8
_MAX_RATE_LIMIT = 10_000

# W6's hard refusal: price is a business setting, an ADDRESS is a key.
# The bulletin is fetched over the network and TTL-cached, which makes a
# fetched pay-to address a payment-redirection target — so any payload
# that carries one is refused WHOLE, not sanitized. The address belongs
# pinned per-repo in constants (the OG_IMAGE_URL precedent).
_ADDRESS_KEY_TOKENS = ("pay_to", "payto", "pay-to", "wallet", "address", "recipient")


class PayToAddressRefused(ValueError):
    """Raised by _normalize when a bulletin tries to carry a pay-to key."""


def _refuse_addresses(obj: Any, path: str = "") -> None:
    """Recursively refuse any payload whose keys smell like an address."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            if any(token in lowered for token in _ADDRESS_KEY_TOKENS):
                raise PayToAddressRefused(f"bulletin carries {path}{key!r} — refused whole")
            _refuse_addresses(value, f"{path}{key}.")
    elif isinstance(obj, list):
        for entry in obj:
            _refuse_addresses(entry, path)


_MAX_WORDMARK_LINES = 12
_MAX_WORDMARK_WIDTH = 120
_MAX_RESPONSE_BYTES = 64 * 1024


class BulletinConfig:
    """Where the bulletin comes from and how aggressively it is refreshed."""

    def __init__(
        self,
        url: Optional[str] = None,
        ttl: float = 900.0,
        timeout: float = 3.0,
        enabled: bool = False,
        app_id: Optional[str] = None,
    ) -> None:
        self.url = url
        self.ttl = ttl
        self.timeout = timeout
        self.app_id = app_id
        self.enabled = enabled and bool(url)


class _Cache:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.data: Optional[Dict[str, Any]] = None
        self.fetched_at: float = 0.0
        self.in_flight = False
        # After a failure, back off so a down endpoint isn't hammered once
        # per request-that-notices-the-cache-is-stale.
        self.failure_until: float = 0.0


_config = BulletinConfig()
_cache = _Cache()


def configure_bulletin(
    url: Optional[str] = None,
    ttl: float = 900.0,
    timeout: float = 3.0,
    enabled: bool = True,
    app_id: Optional[str] = None,
) -> None:
    """
    Point this app at a network bulletin endpoint.

    Args:
        url: Absolute URL returning the bulletin JSON (see ``docs/BULLETIN.md``
            for the contract). Passing None disables the feature.
        ttl: Seconds before a cached bulletin is considered stale. The stale
            copy keeps being served while a refresh runs in the background.
        timeout: Socket timeout for the fetch.
        enabled: Set False to configure without activating.
        app_id: Identifies this app to the hub, sent as ``?app=``. Lets the
            hub target announcements at particular satellites and see which
            of them are actually rendering the bulletin. Optional — the hub
            must serve a sensible default when it is absent.

    Fetching is opt-in; with no call to this function the package makes no
    outbound requests.
    """
    global _config
    _config = BulletinConfig(url=url, ttl=ttl, timeout=timeout, enabled=enabled, app_id=app_id)

    # A new endpoint invalidates whatever the old one said.
    with _cache.lock:
        _cache.data = None
        _cache.fetched_at = 0.0
        _cache.failure_until = 0.0

    if _config.enabled:
        _spawn_refresh()


def get_bulletin() -> Optional[Dict[str, Any]]:
    """
    Return the cached bulletin, or None.

    Returns immediately in all cases. Triggers a background refresh when the
    cached copy is stale, and keeps returning the stale copy until the new
    one lands.
    """
    if not _config.enabled:
        return None

    now = time.monotonic()
    with _cache.lock:
        data = _cache.data
        stale = (now - _cache.fetched_at) > _config.ttl
        backing_off = now < _cache.failure_until

    if stale and not backing_off:
        _spawn_refresh()

    return data


def _spawn_refresh() -> None:
    """Start a background fetch unless one is already running."""
    with _cache.lock:
        if _cache.in_flight:
            return
        _cache.in_flight = True

    thread = threading.Thread(target=_refresh, name="dimll-bulletin-refresh", daemon=True)
    thread.start()


def _refresh() -> None:
    try:
        payload = _fetch(_config.url, _config.timeout, _config.app_id)
        normalized = _normalize(payload)
    except Exception as exc:  # noqa: BLE001 - a bulletin must never propagate
        logger.debug("dash-improve-my-llms: bulletin fetch failed: %s", exc)
        with _cache.lock:
            _cache.in_flight = False
            # Back off for one TTL rather than retrying on every request.
            _cache.failure_until = time.monotonic() + _config.ttl
        return

    with _cache.lock:
        _cache.data = normalized
        _cache.fetched_at = time.monotonic()
        _cache.failure_until = 0.0
        _cache.in_flight = False


def _fetch(url: Optional[str], timeout: float, app_id: Optional[str] = None) -> Dict[str, Any]:
    if not url:
        raise ValueError("no bulletin URL configured")

    if app_id:
        # Same attribution convention as the ad-network endpoint this mirrors,
        # so one admin surface can target and measure both.
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}app={urllib.parse.quote(app_id, safe='')}"

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "dash-improve-my-llms bulletin client",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        # Read one byte past the cap so an oversized body is detected rather
        # than silently truncated into invalid JSON.
        raw = response.read(_MAX_RESPONSE_BYTES + 1)

    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError(f"bulletin larger than {_MAX_RESPONSE_BYTES} bytes")

    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("bulletin must be a JSON object")
    return parsed


def _clean(value: Any, limit: int) -> str:
    """Coerce a remote value to a bounded single-line string."""
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _clean_url(value: Any) -> str:
    """Accept only http(s) URLs — the payload is untrusted."""
    text = _clean(value, 500)
    return text if text.lower().startswith(("http://", "https://")) else ""


def _items(raw: Any) -> List[Dict[str, str]]:
    if not isinstance(raw, list):
        return []

    items: List[Dict[str, str]] = []
    for entry in raw[:_MAX_ITEMS]:
        if isinstance(entry, str):
            entry = {"title": entry}
        if not isinstance(entry, dict):
            continue

        title = _clean(entry.get("title"), _MAX_TITLE)
        body = _clean(entry.get("body") or entry.get("text"), _MAX_BODY)
        if not (title or body):
            continue

        items.append(
            {
                "title": title,
                "body": body,
                "url": _clean_url(entry.get("url")),
                "date": _clean(entry.get("date"), 40),
            }
        )
    return items


def _wordmark(raw: Any) -> Any:
    """
    Accept an optional mark for the banner, in either supported form.

    A ``{"morse": "plot", "prefix": "2", "suffix": ".ai"}`` mapping draws the
    word as morse code; a list of strings is ASCII art. Both are kept in the
    payload rather than the package so the package stays brand-neutral and a
    network can restyle every satellite without a release.

    Returns None when there is nothing usable, so the viewer falls back to the
    network name as styled text.
    """
    if isinstance(raw, dict):
        word = _clean(raw.get("morse") or raw.get("word"), 32)
        if word:
            return {
                "morse": word,
                "prefix": _clean(raw.get("prefix"), 8),
                "suffix": _clean(raw.get("suffix"), 8),
                "label": _clean(raw.get("label"), _MAX_TITLE),
                # Only a real boolean overrides the suffix-based default.
                "arrow": raw["arrow"] if isinstance(raw.get("arrow"), bool) else None,
            }
        return _ascii_wordmark(raw.get("ascii")) or None

    return _ascii_wordmark(raw) or None


def _ascii_wordmark(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []

    lines: List[str] = []
    for line in raw[:_MAX_WORDMARK_LINES]:
        if not isinstance(line, str):
            continue
        lines.append(line.replace("\t", "  ")[:_MAX_WORDMARK_WIDTH])
    return lines


def _crawler_policy(raw: Any) -> List[Dict[str, str]]:
    """Bounded {vendor, policy} list — hub tightenings for the W2 fold.

    Only registry vendor keys and real policies survive; the hub may only
    TIGHTEN local policy (vendors.effective_policies applies the overlay
    most-restrictively), so a junk entry dropped here can never loosen
    anything either.
    """
    if not isinstance(raw, list):
        return []
    from .vendors import get_vendor

    out: List[Dict[str, str]] = []
    for entry in raw[:_MAX_POLICY_ITEMS]:
        if not isinstance(entry, dict):
            continue
        vendor = _clean(entry.get("vendor"), 40)
        policy = _clean(entry.get("policy"), 10).lower()
        if vendor and get_vendor(vendor) is not None and policy in ("allow", "block", "meter"):
            out.append({"vendor": vendor, "policy": policy})
    return out


def _prices(raw: Any) -> List[Dict[str, str]]:
    """Bounded {path, price} list. Price STRINGS only — never an address."""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for entry in raw[:_MAX_PRICE_ITEMS]:
        if not isinstance(entry, dict):
            continue
        path = _clean(entry.get("path"), 120)
        price = _clean(entry.get("price"), 40)
        if path and price:
            out.append({"path": path, "price": price})
    return out


def _rate_limit(raw: Any) -> Optional[int]:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if 1 <= value <= _MAX_RATE_LIMIT:
        return value
    return None


def _normalize(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce an arbitrary payload to the bounded shape the viewer renders.

    Raises PayToAddressRefused — refusing the WHOLE payload — if any key
    anywhere smells like a payment address; see _refuse_addresses.
    """
    _refuse_addresses(payload)
    network = payload.get("network")
    if not isinstance(network, dict):
        network = {}

    return {
        "network": {
            "name": _clean(network.get("name"), _MAX_TITLE),
            "tagline": _clean(network.get("tagline"), _MAX_BODY),
            "url": _clean_url(network.get("url")),
            "llms_txt": _clean_url(network.get("llms_txt")),
            # Where an account comes from, for a site that gates documents but
            # does not own the accounts. Network-wide, static and cacheable.
            #
            # The visitor's identity must NEVER travel here: this payload is
            # TTL-cached and shared by every viewer of every satellite, so a
            # username in it would be a privacy bug wearing a cache. Identity
            # is per-request and local — see configure_viewer_identity().
            "sign_in_url": _clean_url(network.get("sign_in_url")),
            "account_label": _clean(network.get("account_label"), _MAX_TITLE),
            "wordmark": _wordmark(network.get("wordmark")),
            # W6 — the toll-gate policy keys. Consumed by
            # vendors.effective_policies (crawler_policy, tighten-only) and
            # the W4 limiter (rate_limit, tighten-only); the price fields
            # are carried for the application's offer_doc and never
            # interpreted by the package.
            "crawler_policy": _crawler_policy(network.get("crawler_policy")),
            "price_default": _clean(network.get("price_default"), 40),
            "prices": _prices(network.get("prices")),
            "rate_limit": _rate_limit(network.get("rate_limit")),
        },
        "tips": _items(payload.get("tips")),
        "whats_new": _items(payload.get("whats_new") or payload.get("whatsNew")),
        "version": _clean(payload.get("version"), 40),
    }
