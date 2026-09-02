"""Standards-tracking discovery relations and the source digest — 2.7.1.

Three small, additive surfaces (llms.txt v2's August 2026 discovery
update), all default-on, none changing existing bytes' meaning:

1. **Discovery relations.** Every page declares its markdown twin
   (``rel="alternate" type="text/markdown"`` — emitted since 2.x) and the
   covering site index (``rel="describedby"`` → ``/llms.txt``), in the
   HTML head of BOTH document lanes and as an HTTP ``Link`` header on
   page responses — so an agent that reads only headers still finds the
   machine surface.
2. **The text/plain ramp** lives in the adapters: an Accept header that
   asks for ``text/plain`` (and not markdown) gets the same bytes with
   the compatible content type — a mainstream agent retrieval stack was
   measured rejecting ``text/markdown`` outright.
3. **The source digest**: the sha256 of the markdown source a lane
   serves, exposed as a meta tag (HTML lanes) and an
   ``X-Llms-Source-Digest`` header (the markdown twin) — representation
   parity becomes provable rather than plausible: a deployment battery
   can assert the page, its twin, and the crawler document were
   generated from the same source. The digest is of the SERVED source
   (a gated page's lanes all digest the gate document — parity holds for
   every verdict). The root ``/llms.txt`` is a composite index built
   from many sources and carries no digest: the home page's HTML lanes
   digest the home prose, and the composite is the documented exception.
"""

from __future__ import annotations

import hashlib
from typing import Optional

DIGEST_META_NAME = "llms-source-digest"
DIGEST_HEADER = "X-Llms-Source-Digest"


def source_digest(markdown_source: Optional[str]) -> Optional[str]:
    """``sha256:<hex>`` of the markdown source, or None for no source."""
    if not markdown_source or not str(markdown_source).strip():
        return None
    return "sha256:" + hashlib.sha256(str(markdown_source).encode("utf-8")).hexdigest()


def twin_path(page_path: str) -> str:
    """The page's markdown twin."""
    return "/llms.txt" if page_path == "/" else f"{page_path}/llms.txt"


def link_header_value(page_path: str) -> str:
    """The HTTP ``Link`` header for a page response.

    The alternate points at the page's own twin; describedby at the
    covering site index. On the home page the two coincide — emitted
    once each regardless, so consumers get uniform relations.
    """
    return (
        f'<{twin_path(page_path)}>; rel="alternate"; type="text/markdown", '
        '</llms.txt>; rel="describedby"'
    )


def accept_quality(accept: str, media_type: str) -> float:
    """The q-value an ``Accept`` header gives one media type.

    RFC 9110 §12.5.1 precedence: the most specific matching range wins
    regardless of q, so ``text/markdown`` beats ``text/*`` beats ``*/*``.
    That ordering is the whole reason this is a parser and not a
    substring test — a browser's
    ``text/html,application/xhtml+xml,*/*;q=0.8`` matches markdown only
    through the wildcard, at 0.8, while html matches exactly at 1.0.

    An absent or unparseable header reads as ``*/*``: 1.0 for anything.
    """
    text = (accept or "").strip()
    if not text:
        return 1.0

    main_type = media_type.split("/")[0]
    best = None  # (specificity, q) — specificity 2 exact, 1 type/*, 0 */*
    for part in text.split(","):
        piece = part.strip()
        if not piece:
            continue
        range_, _, params = piece.partition(";")
        range_ = range_.strip().lower()

        quality = 1.0
        for param in params.split(";"):
            key, _, value = param.partition("=")
            if key.strip().lower() == "q":
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 1.0

        if range_ == media_type:
            specificity = 2
        elif range_ == f"{main_type}/*":
            specificity = 1
        elif range_ == "*/*":
            specificity = 0
        else:
            continue

        if best is None or specificity > best[0]:
            best = (specificity, quality)

    return 0.0 if best is None else best[1]


def prefers_markdown(accept: str) -> bool:
    """True when a client asks for markdown MORE than for HTML.

    Strictly greater, deliberately. ``*/*`` and a tie both leave HTML the
    default, so a browser, a crawler sending ``*/*`` and every client that
    has never heard of this negotiation are all unaffected — which is the
    property that lets a page URL answer two content types without
    anything having to opt out.
    """
    return accept_quality(accept, "text/markdown") > accept_quality(accept, "text/html")


def wants_plain_text(accept: str) -> bool:
    """The one-line compatibility ramp: an Accept header that names
    text/plain and does not name markdown gets the same bytes typed
    text/plain. ``*/*`` alone keeps the markdown type (the historical
    contract; ``Vary: Accept`` already travels on these responses)."""
    accept = (accept or "").lower()
    return "text/plain" in accept and "text/markdown" not in accept
