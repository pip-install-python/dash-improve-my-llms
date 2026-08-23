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
Injection also resolves the page ``<title>`` (same resolution as the crawler
document: explicit ``title``, else "page · site") and adds a description,
canonical, and JSON-LD per page. Dash's classic index is one static template
for every route, so without this every URL in a pages app ships the same
app-level title and no description at all — which is most of what "28 thin
near-duplicates" means to a search engine.

The app's own head wins. Every injected tag is skipped when the document
already declares its counterpart, and the ``<title>`` is only rewritten when
that is an upgrade — an app whose title already carries the page's name
(Dash Pages resolves per-page titles server-side) keeps it verbatim.
"""

from __future__ import annotations

import html as _stdlib_html
import logging
import re
from typing import Any, Dict, List, Optional

from .html_generator import _json_ld, resolve_page_title
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

# What "already injected" actually looks like: the body div's opening tag.
# The probe deliberately targets this, not _MARKER — see inject_prerender.
_INJECTED_PROBE = '<div id="dimll-prerender"'


def _esc(value: Any) -> str:
    return _stdlib_html.escape(str(value or ""), quote=True)


def build_head_tags(context: Dict[str, Any], *, peers_html: str = "", document: str = "") -> str:
    """Per-page <head> metadata: description, canonical, OpenGraph, JSON-LD.

    Pass the ``document`` being injected into and each tag is emitted only
    when the document does not already declare its counterpart. The app's own
    head always wins: Dash Pages and hand-written index templates both emit
    per-page metadata, and a second description, canonical, or og:title is
    not reinforcement — duplicate canonicals are ignored by crawlers and
    conflicting og:titles make the scraper pick one arbitrarily.
    """
    meta = context["page_metadata"]
    app_config = context["app_config"]
    page_path = context["page_path"]

    base_url = str(app_config.get("base_url") or "").rstrip("/")
    name = meta.get("name") or "Page"
    title = resolve_page_title(page_path, meta, str(app_config.get("name") or ""))
    description = meta.get("description") or markdown_to_text(meta.get("llms_doc"), limit=155)
    canonical = f"{base_url}{page_path}"
    llms_link = "/llms.txt" if page_path == "/" else f"{page_path}/llms.txt"

    def missing(tag: str, attr: str, value: str) -> bool:
        """True when the document has no non-empty counterpart of a tag.

        Dash emits `<meta name="description" content="">` for a page with no
        description — an empty declaration is a slot nobody filled, not a
        decision to defer to, so only a non-empty content/href suppresses
        the injected tag.
        """
        for match in re.finditer(
            rf'<{tag}[^>]*\b{attr}=["\']{re.escape(value)}["\'][^>]*>', document, re.IGNORECASE
        ):
            if re.search(r'(?:content|href)=["\'][^"\']+["\']', match.group(0), re.IGNORECASE):
                return False
        return True

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

    parts = []
    if missing("meta", "name", "description"):
        parts.append(f'<meta {_MARKER}="1" name="description" content="{_esc(description)}">')
    if missing("link", "rel", "canonical"):
        parts.append(f'<link {_MARKER}="1" rel="canonical" href="{_esc(canonical)}">')
    parts.append(
        f'<link {_MARKER}="1" rel="alternate" type="text/markdown" '
        f'href="{_esc(llms_link)}" title="LLM-friendly documentation">'
    )
    # llms.txt v2 discovery (2.7.1): the covering site index, and the
    # digest of the markdown source this page's representations share —
    # parity across the page, its twin, and the crawler document becomes
    # provable rather than plausible. Digest is of the SERVED source
    # (a gated page's lanes all carry the gate doc's digest).
    if missing("link", "rel", "describedby"):
        parts.append(f'<link {_MARKER}="1" rel="describedby" href="/llms.txt">')
    from .discovery import DIGEST_META_NAME, source_digest

    digest = source_digest(meta.get("llms_doc"))
    if digest and missing("meta", "name", DIGEST_META_NAME):
        parts.append(f'<meta {_MARKER}="1" name="{DIGEST_META_NAME}" content="{_esc(digest)}">')
    parts.append(f'<link {_MARKER}="1" rel="sitemap" type="application/xml" href="/sitemap.xml">')
    if missing("meta", "property", "og:type"):
        parts.append(f'<meta {_MARKER}="1" property="og:type" content="website">')
    if missing("meta", "property", "og:title"):
        parts.append(f'<meta {_MARKER}="1" property="og:title" content="{_esc(title)}">')
    if missing("meta", "property", "og:description"):
        parts.append(
            f'<meta {_MARKER}="1" property="og:description" content="{_esc(description)}">'
        )
    if missing("meta", "property", "og:url"):
        parts.append(f'<meta {_MARKER}="1" property="og:url" content="{_esc(canonical)}">')

    og_image = meta.get("og_image") or meta.get("image_url")
    if og_image and missing("meta", "property", "og:image"):
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

    # SEO-audit finding (2026-08-23, confirmed on every host): the header's
    # h1 duplicated the doc body's own opening markdown H1 — two identical
    # h1s on every prerendered page. When the prose opens with its own h1,
    # the header contributes only the description; when it doesn't (a page
    # with no LLMS_DOC, or prose that starts mid-thought), the header's h1
    # is the page's only one and stays.
    prose_opens_with_h1 = prose.lstrip().lower().startswith("<h1")
    if prose_opens_with_h1:
        header = f"<header><p>{description}</p></header>"
    else:
        header = f"<header><h1>{name}</h1><p>{description}</p></header>"

    sections = [
        header,
        f"<main>{prose}</main>",
    ]

    if nav_items:
        sections.append(
            f'<nav aria-label="Site pages"><h2>All pages</h2>' f"<ul>{nav_items}</ul></nav>"
        )

    if extra_sections:
        sections.extend(extra_sections)

    # On the home page the per-page document IS the root index — linking
    # both rendered "…/llms.txt · /llms.txt · /sitemap.xml".
    if llms_link == "/llms.txt":
        footer_links = (
            '<a href="/llms.txt">/llms.txt</a> · ' '<a href="/sitemap.xml">/sitemap.xml</a>'
        )
    else:
        footer_links = (
            f'<a href="{_esc(llms_link)}">{_esc(llms_link)}</a> · '
            '<a href="/llms.txt">/llms.txt</a> · '
            '<a href="/sitemap.xml">/sitemap.xml</a>'
        )
    sections.append(
        "<footer><p>Machine-readable version of this page: " + footer_links + "</p></footer>"
    )

    # The div ships VISIBLE, and the inline script right after it hides it.
    #
    # It used to ship with a literal `hidden` attribute, on the theory that
    # crawlers and text extractors read hidden DOM normally. An outside SEO
    # audit (2026-08-22) proved the theory wrong the expensive way: every
    # consumer that respects visibility — html-to-text extractors, audit
    # tooling, and plausibly crawler content-weighting — saw only the Dash
    # loader, and six production hosts read as 20 identical thin pages each.
    # The prose was present and invisible, which is the worst of both.
    #
    # This shape gives each audience exactly what it needs:
    #   - A non-JS consumer never executes the script, so it reads fully
    #     visible prose. That is the entire fix.
    #   - A JS browser executes it synchronously during parse, before first
    #     paint of subsequent content, so the pre-mount flash the old
    #     `hidden` existed to prevent stays prevented; React's mount then
    #     wipes the whole block from the DOM exactly as before.
    #   - NOT a <noscript> (search engines treat noscript as second-class
    #     and it is a classic spam vector) and NOT a stylesheet class (an
    #     extractor ignoring stylesheets is not guaranteed; the attribute
    #     was this problem's own proof of what these tools respect).
    #
    # Both nodes carry the marker so exclusion logic that strips
    # prerender-tagged nodes keeps matching the pair. CSP note: the inline
    # script needs `unsafe-inline` or a nonce under a strict CSP — recorded
    # in the changelog; no 2plot host ships a restrictive CSP today.
    return (
        f'<div id="dimll-prerender" {_MARKER}="1">' + "".join(sections) + "</div>"
        f'<script {_MARKER}="1">'
        'document.getElementById("dimll-prerender").hidden=true;'
        "</script>"
    )


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
    # The already-injected probe matches the injected node's OPENING TAG,
    # never the bare marker string. Through 2.6.x this was
    # `_MARKER in document`, and the marker's NAME appearing anywhere —
    # including an innocent index.html COMMENT — silently disabled the
    # entire universal prerender. Two production hosts shipped exactly
    # that (fleet finding, 2026-08-22): a comment mentioning
    # data-dimll-prerender cost them every prerendered page. The rule for
    # authors stands regardless (never spell the marker in served text),
    # but the package no longer hands out that footgun.
    if not document or _INJECTED_PROBE in document:
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

    head_tags = build_head_tags(context, peers_html=peers_html, document=document)
    document = _HEAD_CLOSE_RE.sub(lambda _m: f"    {head_tags}\n</head>", document, count=1)

    if set_title:
        meta = context["page_metadata"]
        app_config = context.get("app_config") or {}
        resolved = resolve_page_title(
            context.get("page_path") or "/", meta, str(app_config.get("name") or "")
        )
        explicit = str(meta.get("title") or "").strip()
        current_match = _TITLE_RE.search(document)
        current = re.sub(r"</?title>", "", current_match.group(0)).strip() if current_match else ""
        page_name = str(meta.get("name") or "").strip()

        # Rewrite only when it is an upgrade. An explicit metadata title is
        # authoritative; otherwise a title that already carries the page's
        # name is page-specific — Dash Pages resolves per-page titles
        # server-side from 4.x, and replacing "site | page" with a
        # synthesized "page · site" would clobber the application's own,
        # deliberate title. The rewrite exists for the static-template case,
        # where every URL ships the same app-level <title>.
        already_specific = bool(
            page_name and current and page_name.lower() in _stdlib_html.unescape(current).lower()
        )
        if resolved and (explicit or not already_specific):
            document = _TITLE_RE.sub(
                lambda _m: f"<title>{_esc(resolved)}</title>", document, count=1
            )

    return document
