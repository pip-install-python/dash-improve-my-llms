"""
Inject each page's real content into the initial HTML, for every visitor.

Why this exists
---------------
The package originally served rich HTML only to requests whose user agent
looked like a crawler, and the JavaScript shell to everyone else. Two
problems with that:

1. **It is the shape of cloaking.** Serving a stub to users and prose to
   crawlers (or vice versa) is the pattern search engines penalise, even
   when the intent is benign. Google deprecated dynamic rendering as a
   recommendation in 2022. Serving the same content to everyone sidesteps
   the question entirely.
2. **It only worked for agents we recognised.** Any crawler, embedder, or
   link-preview fetcher outside the user-agent list got
   ``<div class="_dash-loading">Loading...</div>`` and nothing else.

So the prose goes into the initial HTML unconditionally. Dash mounts React
into ``#react-entry-point`` with ``createRoot().render()``, which *replaces*
whatever that container holds — so the prerendered markup is what a non-JS
consumer reads and what a browser paints first, and the live app takes over
on hydration with no coordination needed.

The user-agent path is deliberately kept as a fallback: it still short-
circuits before Dash runs and is cheaper for a pure crawler hit.

Head metadata
-------------
Injection also rewrites ``<title>`` and adds a description, canonical, and
JSON-LD per page. Dash's index is one static template for every route, so
without this every URL in a pages app ships the same app-level title and no
description at all — which is most of what "28 thin near-duplicates" means
to a search engine.
"""

from __future__ import annotations

import html as _stdlib_html
import logging
import re
from typing import Any, Dict, List, Optional

from .html_generator import _json_ld
from .markdown_renderer import markdown_to_text, render_markdown

logger = logging.getLogger(__name__)

__all__ = ["inject_prerender", "build_body_fragment", "build_head_tags"]


# Dash renders {%app_entry%} to this container. Matching on the id (rather
# than the exact loading markup) keeps us working across Dash versions that
# reword the placeholder.
_ENTRY_POINT_RE = re.compile(
    r'(<div\s+id=(?:"react-entry-point"|\'react-entry-point\')[^>]*>)(.*?)(</div>)',
    re.DOTALL | re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title>.*?</title>", re.DOTALL | re.IGNORECASE)
_HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)

# Marks our block so it is easy to spot in view-source and so a double
# injection (two middlewares, or a re-entrant call) is a no-op rather than
# duplicated content — which would look like keyword stuffing.
_MARKER = "data-dimll-prerender"


def _esc(value: Any) -> str:
    return _stdlib_html.escape(str(value or ""), quote=True)


def build_head_tags(context: Dict[str, Any], *, peers_html: str = "") -> str:
    """Per-page <head> metadata: description, canonical, OpenGraph, JSON-LD."""
    meta = context["page_metadata"]
    app_config = context["app_config"]
    page_path = context["page_path"]

    base_url = str(app_config.get("base_url") or "").rstrip("/")
    name = meta.get("name") or "Page"
    description = meta.get("description") or markdown_to_text(meta.get("llms_doc"), limit=155)
    canonical = f"{base_url}{page_path}"
    llms_link = "/llms.txt" if page_path == "/" else f"{page_path}/llms.txt"

    structured = {
        "@context": "https://schema.org",
        "@type": meta.get("schema_type") or "WebPage",
        "name": name,
        "url": canonical,
        "description": description or "",
        "isPartOf": {
            "@type": "WebSite",
            "name": app_config.get("name") or "Dash Application",
            "url": base_url or "/",
        },
    }

    parts = [
        f'<meta {_MARKER}="1" name="description" content="{_esc(description)}">',
        f'<link {_MARKER}="1" rel="canonical" href="{_esc(canonical)}">',
        f'<link {_MARKER}="1" rel="alternate" type="text/markdown" '
        f'href="{_esc(llms_link)}" title="LLM-friendly documentation">',
        f'<link {_MARKER}="1" rel="sitemap" type="application/xml" href="/sitemap.xml">',
        f'<meta {_MARKER}="1" property="og:type" content="website">',
        f'<meta {_MARKER}="1" property="og:title" content="{_esc(name)}">',
        f'<meta {_MARKER}="1" property="og:description" content="{_esc(description)}">',
        f'<meta {_MARKER}="1" property="og:url" content="{_esc(canonical)}">',
    ]

    og_image = meta.get("og_image")
    if og_image:
        image_url = og_image if "://" in str(og_image) else f"{base_url}{og_image}"
        parts.append(f'<meta {_MARKER}="1" property="og:image" content="{_esc(image_url)}">')

    if peers_html:
        parts.append(peers_html)

    parts.append(
        f'<script {_MARKER}="1" type="application/ld+json">\n' f"{_json_ld(structured)}\n</script>"
    )

    return "\n    ".join(parts)


def build_body_fragment(
    context: Dict[str, Any], *, extra_sections: Optional[List[str]] = None
) -> str:
    """
    The prerendered page body that lands inside ``#react-entry-point``.

    Contains the page's prose plus a real, crawlable link to every sibling
    page. The sibling links matter as much as the prose: they are what gives
    a pages app an internal link graph in its initial HTML rather than one
    assembled by JavaScript.
    """
    meta = context["page_metadata"]
    page_path = context["page_path"]
    llms_doc = meta.get("llms_doc")

    name = _esc(meta.get("name") or "Page")
    description = _esc(meta.get("description") or markdown_to_text(llms_doc, limit=200))

    if llms_doc:
        prose = render_markdown(llms_doc)
    else:
        prose = "<p>This page contains interactive content that requires " "JavaScript.</p>"

    nav_items = "".join(
        f'<li><a href="{_esc(page["path"])}">{_esc(page["name"])}</a></li>'
        for page in context["all_pages"]
        if page["path"] != page_path
    )

    llms_link = "/llms.txt" if page_path == "/" else f"{page_path}/llms.txt"

    sections = [
        f"<header><h1>{name}</h1><p>{description}</p></header>",
        f"<main>{prose}</main>",
    ]

    if nav_items:
        sections.append(
            f'<nav aria-label="Site pages"><h2>All pages</h2>' f"<ul>{nav_items}</ul></nav>"
        )

    if extra_sections:
        sections.extend(extra_sections)

    sections.append(
        "<footer><p>Machine-readable version of this page: "
        f'<a href="{_esc(llms_link)}">{_esc(llms_link)}</a> · '
        '<a href="/llms.txt">/llms.txt</a> · '
        '<a href="/sitemap.xml">/sitemap.xml</a></p></footer>'
    )

    # `hidden` keeps the block out of the painted page for JS visitors, so a
    # slow hydration never flashes a second copy of the content over the app.
    # It stays in the DOM and in the served bytes, so crawlers and text
    # extractors read it normally — this is not display-based hiding of
    # content that differs from what users get.
    return f'<div id="dimll-prerender" {_MARKER}="1" hidden>' + "".join(sections) + "</div>"


def inject_prerender(
    document: str,
    context: Dict[str, Any],
    *,
    extra_sections: Optional[List[str]] = None,
    peers_html: str = "",
    set_title: bool = True,
) -> str:
    """
    Splice prerendered head metadata and body content into a Dash index page.

    Returns the document unchanged if it doesn't look like a Dash index or
    has already been injected, so this is safe to call more than once.
    """
    if not document or _MARKER in document:
        return document

    match = _ENTRY_POINT_RE.search(document)
    if not match:
        logger.debug(
            "dash-improve-my-llms: no #react-entry-point in the response for %s; "
            "skipping prerender injection.",
            context.get("page_path"),
        )
        return document

    fragment = build_body_fragment(context, extra_sections=extra_sections)

    # Keep Dash's loading placeholder as the last child so the app's own
    # loading UX is unchanged for JS visitors.
    document = (
        document[: match.start()]
        + match.group(1)
        + fragment
        + match.group(2)
        + match.group(3)
        + document[match.end() :]
    )

    head_tags = build_head_tags(context, peers_html=peers_html)
    document = _HEAD_CLOSE_RE.sub(lambda _m: f"    {head_tags}\n</head>", document, count=1)

    if set_title:
        name = context["page_metadata"].get("name")
        if name:
            document = _TITLE_RE.sub(lambda _m: f"<title>{_esc(name)}</title>", document, count=1)

    return document
