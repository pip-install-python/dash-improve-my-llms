"""Per-request access control for the documents this package serves.

``mark_hidden()`` answers "is this page hidden?". An application with accounts
needs to answer "is this page hidden **from this requester?**", which a
process-wide set cannot express. :func:`configure_access` lets the application
answer that question itself, once per request, and have every surface honour it.

Three verdicts, and the difference between the last two is the whole point:

``allow``
    Serve the prose.
``gated``
    The document exists and this requester may not read it *yet*. Serve
    ``gate_doc(path)`` at 200 and keep the URL in the sitemap and the index —
    it is public knowledge that the page exists, only the content is
    restricted. This is what makes a sign-up funnel work: an agent that fetches
    it learns what the page is and how to get access.
``deny``
    There is nothing here. 404, and omitted from every listing. Use where
    advertising the URL would itself be a disclosure.

Nothing here knows what a session, a cookie or a key is. The application
decides; this module asks.

**The check is only ever called inside a request.** Startup-time work (the
missing-prose warning) keeps using the static hidden set, because a check that
reads request state would raise there — and by design that raise means
``gated``, which would make every page look restricted at boot.

See ``docs/ACCESS.md`` in the repository for the full contract.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)

ALLOW = "allow"
GATED = "gated"
DENY = "deny"

_VERDICTS = (ALLOW, GATED, DENY)


class _AccessConfig:
    """Holds the application's callbacks. One instance per process."""

    def __init__(self) -> None:
        self.check: Optional[Callable[[str], str]] = None
        self.gate_doc: Optional[Callable[[str], str]] = None
        self.link_suffix: Optional[Callable[[], str]] = None


_config = _AccessConfig()

# Paths whose check has already raised, so a broken callback logs once rather
# than once per request per crawler.
_warned: Set[str] = set()


def configure_access(
    check: Callable[[str], str],
    *,
    gate_doc: Optional[Callable[[str], str]] = None,
    link_suffix: Optional[Callable[[], str]] = None,
) -> None:
    """
    Let the application decide, per request, who may read each document.

    Args:
        check: ``(path) -> "allow" | "gated" | "deny"``. Called inside the
            request, on every request, for paths that may be hot — keep it
            cheap. Raising is safe: it degrades to ``"gated"``.
        gate_doc: ``(path) -> markdown`` for the ``"gated"`` verdict. Falls
            back to a stub built from the page's registered name and
            description, plus the network's sign-in URL when the bulletin
            supplies one.
        link_suffix: ``() -> ""`` or a query string such as ``"?key=…"`` for
            the current request. Appended to the same-origin URLs this package
            generates — the navigation block and the root index — so that an
            agent handed an authorised URL can follow the links inside it.
            Never appended to canonical tags, sitemap entries or peer links.

    Not configuring this leaves every behaviour exactly as it was; only
    ``mark_hidden()`` applies.
    """
    if not callable(check):
        raise TypeError("configure_access(check=...) must be callable")
    _config.check = check
    _config.gate_doc = gate_doc if callable(gate_doc) else None
    _config.link_suffix = link_suffix if callable(link_suffix) else None
    _warned.clear()
    logger.debug("dash-improve-my-llms: per-request access control configured")


def is_configured() -> bool:
    return _config.check is not None


def resolve(path: str, hidden_paths: Optional[Set[str]] = None) -> str:
    """The verdict for ``path`` on this request.

    Folds the static hidden set and the application's check into one answer, so
    that no call site can implement half the rule. ``mark_hidden()`` wins: it
    means "deny, always", and an application check cannot un-hide a page.
    """
    if hidden_paths and path in hidden_paths:
        return DENY

    check = _config.check
    if check is None:
        return ALLOW

    try:
        verdict = check(path)
    except Exception as exc:  # noqa: BLE001 - a broken callback must not 500
        if path not in _warned:
            _warned.add(path)
            logger.warning(
                "dash-improve-my-llms: access check raised for %s (%s) — "
                "serving the gate document. Fix the callback; until then this "
                "page's prose is withheld rather than published.",
                path,
                exc,
            )
        return GATED

    if verdict in _VERDICTS:
        return verdict

    if path not in _warned:
        _warned.add(path)
        logger.warning(
            "dash-improve-my-llms: access check returned %r for %s; expected "
            "one of %s. Treating as %r.",
            verdict,
            path,
            ", ".join(_VERDICTS),
            GATED,
        )
    return GATED


def is_listable(path: str, hidden_paths: Optional[Set[str]] = None) -> bool:
    """Whether ``path`` may appear in the index, the sitemap or MCP.

    ``gated`` pages stay listed — the URL is public even when the content is
    not, and hiding it would defeat the funnel the gate exists for.
    """
    return resolve(path, hidden_paths) != DENY


def gate_document(
    path: str,
    page_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    state: Any = None,
) -> str:
    """The body served for a ``gated`` verdict.

    Prefers the application's ``gate_doc``; falls back to a stub assembled from
    what is already registered, so a misconfigured app still serves something
    coherent rather than an empty document.
    """
    provider = _config.gate_doc
    if provider is not None:
        try:
            body = provider(path)
            if body and body.strip():
                return body
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "dash-improve-my-llms: gate_doc raised for %s (%s) — using the " "built-in stub.",
                path,
                exc,
            )

    meta = (page_metadata or {}).get(path) or {}
    name = meta.get("name") or path
    description = meta.get("description") or ""

    lines = [f"# {name}", ""]
    if description:
        lines += [f"> {description}", ""]
    lines += [
        "This document is not publicly available.",
        "",
    ]

    sign_in = _sign_in_url(state)
    if sign_in:
        lines += [f"Access requires an account: {sign_in}", ""]

    return "\n".join(lines)


def _sign_in_url(state: Any) -> str:
    """The network's sign-in URL, when the bulletin published one."""
    try:
        from .bulletin import get_bulletin

        network = (get_bulletin() or {}).get("network") or {}
        return str(network.get("sign_in_url") or "")
    except Exception:  # noqa: BLE001 - the bulletin is optional everywhere
        return ""


def link_suffix() -> str:
    """Query string to append to generated same-origin URLs this request."""
    provider = _config.link_suffix
    if provider is None:
        return ""
    try:
        suffix = provider() or ""
    except Exception as exc:  # noqa: BLE001
        logger.debug("dash-improve-my-llms: link_suffix raised (%s)", exc)
        return ""
    suffix = str(suffix).strip()
    if not suffix:
        return ""
    if not suffix.startswith(("?", "&")):
        suffix = "?" + suffix
    return suffix


def decorate(url: str) -> str:
    """Append :func:`link_suffix` to one generated URL."""
    suffix = link_suffix()
    if not suffix:
        return url
    if "?" in url:
        return url + "&" + suffix.lstrip("?&")
    return url + suffix


def decorate_body(body: str, base_url: str = "") -> str:
    """Carry this request's authority across every document link in ``body``.

    The nav block and the index are generated here, so :func:`decorate` handles
    them. But most of a document is application prose — a catalogue page listing
    every component's ``llms.txt``, a "read this next" line — and an agent handed
    one authorised URL will follow those links too. Undecorated, they land
    unauthenticated and the exploration stops at the first gate, one hop from
    the document that was meant to open the door.

    Rewrites **same-origin ``llms.txt`` URLs only**:

    * a peer or third-party host must never receive this key;
    * anything already carrying a query string is left alone;
    * non-document URLs are left alone — authority opens documents, not pages,
      so decorating a page link would promise something it cannot deliver.

    A no-op when the request carries no authority, which is every request on a
    site that never configured this.
    """
    suffix = link_suffix()
    if not suffix or not body:
        return body

    import re

    param = suffix.lstrip("?&")
    origin = (base_url or "").rstrip("/")

    # The lookbehind rejects `:` and `/` as well as word characters, and that
    # is load-bearing: without it the relative pattern matches the
    # `//peer.example.com/llms.txt` tail of an ABSOLUTE url — the `//` after
    # `https:` reads as the start of a path — and this key gets appended to
    # another network host's URL. Caught in testing; do not relax it.
    patterns = [r"(?<![\w/:])(/[\w\-./]*?/llms\.txt)(?![\w?&=])"]
    if origin:
        patterns.insert(0, rf"({re.escape(origin)}[\w\-./]*?/llms\.txt)(?![\w?&=])")

    def _add(match: "re.Match") -> str:
        return f"{match.group(1)}?{param}"

    for pattern in patterns:
        body = re.sub(pattern, _add, body)
    return body


# ---------------------------------------------------------------------------
# Viewer identity
# ---------------------------------------------------------------------------
# Same request-scoped shape as the access check, same fail-safe posture, and it
# answers the other half of "who is asking" — so it lives here rather than in
# its own module.

_identity_provider: Optional[Callable[[], Optional[Dict[str, Any]]]] = None


def configure_viewer_identity(
    provider: Callable[[], Optional[Dict[str, Any]]],
) -> None:
    """
    Show the signed-in reader who they are, in the llms.txt viewer's header.

    Args:
        provider: ``() -> {"name": str, "since": str, "plan": str} | None``,
            for the current request. Return ``None`` for anonymous visitors.

    Rendered in the **HTML variant only**. Agents, crawlers and curl already
    receive the banner-free Markdown from the same URL, so this costs them
    nothing and cannot reach an index.

    ``since`` is a display string the application supplies; this package
    escapes and truncates it but never interprets it. (If your identity
    provider is Clerk: its session token is refreshed about every 60 seconds,
    so the ``iat`` claim is the token's age, not a login time. Track first-seen
    per session instead, or the clock resets every minute.)

    Not configuring this renders nothing, which is what keeps a site without
    authentication unaffected.
    """
    global _identity_provider
    if not callable(provider):
        raise TypeError("configure_viewer_identity(provider) must be callable")
    _identity_provider = provider


def viewer_identity() -> Optional[Dict[str, Any]]:
    """The current request's identity, or None. Never raises."""
    if _identity_provider is None:
        return None
    try:
        identity = _identity_provider()
    except Exception as exc:  # noqa: BLE001
        logger.debug("dash-improve-my-llms: identity provider raised (%s)", exc)
        return None
    if not isinstance(identity, dict):
        return None
    name = str(identity.get("name") or "").strip()
    if not name:
        return None
    return {
        "name": name[:120],
        "since": str(identity.get("since") or "").strip()[:60],
        "plan": str(identity.get("plan") or "").strip()[:40],
    }


def is_restricted() -> bool:
    """True when this response is per-requester and must not be shared-cached.

    Either it carries authority in its links, or it names the reader. A CDN
    that stored such a response would hand one visitor's document — or one
    visitor's name — to the next.
    """
    return bool(link_suffix()) or viewer_identity() is not None


def private_headers() -> Dict[str, str]:
    """Response headers for a per-requester document."""
    return {
        "Cache-Control": "private, no-store",
        "Vary": "Accept, Cookie",
        "X-Robots-Tag": "noindex",
    }


def reset() -> None:
    """Clear configuration. For tests."""
    global _identity_provider
    _config.check = None
    _config.gate_doc = None
    _config.link_suffix = None
    _identity_provider = None
    _warned.clear()
