"""
Pure, framework-agnostic handlers.

These functions know nothing about Flask, FastAPI, or Quart. They take
plain Python inputs (path strings, user-agent strings, the Dash `app`
object) and return either plain strings, dicts, or None.

Each backend adapter wraps these in its own Response type at the I/O
boundary.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import access
from . import geo
from ._paths import normalize_path as _normalize_page_path
from .bot_detection import get_bot_type, is_any_bot
from .markdown_renderer import strip_directive_lines
from .robots_generator import RobotsConfig, generate_robots_txt
from .sitemap_generator import generate_sitemap_xml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page resolution
# ---------------------------------------------------------------------------


def _find_page(page_path: str) -> Optional[Dict[str, Any]]:
    """Look up a page in dash.page_registry by path. Returns the dict or None."""
    try:
        import dash
    except ImportError:
        return None

    page_path = _normalize_page_path(page_path)
    registry = getattr(dash, "page_registry", None) or {}
    for entry in registry.values():
        if page_path in (
            _normalize_page_path(entry.get("path") or ""),
            _normalize_page_path(entry.get("relative_path") or ""),
        ):
            return entry
    return None


def _resolve_llms_doc(
    page_path: str,
    page_metadata: Dict[str, Dict[str, Any]],
    page_entry: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    Resolve the prose body for a page.

    Order of precedence:
      1. register_page_metadata(path, llms_doc="...") stored in page_metadata.
      2. An llms_doc passed straight through dash.register_page(**kwargs).
      3. Module-level LLMS_DOC attribute on the page module.
      4. None (caller emits the stub fallback).

    Step 3 is deliberately forgiving about the registry's ``module`` field.
    ``dash.register_page`` takes the module name positionally, and pages
    registered from a loop commonly pass a display name there instead
    ("Activity · Cockpit"). That name is not in ``sys.modules``, so a strict
    lookup finds nothing and the page silently loses its prose. When the
    field isn't importable we fall back to the module that actually defines
    the page's layout.
    """
    page_path = _normalize_page_path(page_path)

    meta = page_metadata.get(page_path) or {}
    doc = meta.get("llms_doc")
    if doc:
        return strip_directive_lines(doc)

    if page_entry is None:
        return None

    entry_doc = page_entry.get("llms_doc")
    if entry_doc:
        return strip_directive_lines(entry_doc)

    for module_name in _candidate_modules(page_entry):
        module_doc = getattr(sys.modules[module_name], "LLMS_DOC", None)
        if module_doc:
            return strip_directive_lines(module_doc)

    return None


def _candidate_modules(page_entry: Dict[str, Any]) -> List[str]:
    """Module names that might carry this page's LLMS_DOC, best guess first."""
    candidates: List[str] = []

    module_name = page_entry.get("module")
    if isinstance(module_name, str) and module_name in sys.modules:
        candidates.append(module_name)

    # The registry's `module` was not a real module (see _resolve_llms_doc).
    # The layout callable knows where it was actually defined.
    layout = page_entry.get("layout")
    layout_module = getattr(layout, "__module__", None)
    if isinstance(layout_module, str) and layout_module in sys.modules:
        if layout_module not in candidates:
            candidates.append(layout_module)

    return candidates


def list_pages_missing_llms_doc(
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
) -> List[str]:
    """Return paths of visible pages that have no LLMS_DOC source."""
    try:
        import dash
    except ImportError:
        return []

    missing: List[str] = []
    registry = getattr(dash, "page_registry", None) or {}
    for entry in registry.values():
        path = _normalize_page_path(entry.get("path") or "/")
        if path in hidden_paths:
            continue
        if _resolve_llms_doc(path, page_metadata, entry) is None:
            missing.append(path)
    return missing


# ---------------------------------------------------------------------------
# /llms.txt
# ---------------------------------------------------------------------------


def _stub_llms_txt(page_name: str, page_path: str, description: str) -> str:
    """Fallback prose when no LLMS_DOC is registered."""
    desc_line = f"> {description}\n\n" if description else ""
    return (
        f"# {page_name}\n\n"
        f"{desc_line}"
        f"_No `LLMS_DOC` registered for `{page_path}`._\n\n"
        f'To populate this document, either set `LLMS_DOC = """..."""` '
        f"at module scope in the page file, or call "
        f'`register_page_metadata("{page_path}", llms_doc="...")`.\n'
    )


def build_page_nav_block(
    app: Any,
    page_path: str,
    state: Any = None,
) -> str:
    """
    Build the navigation header for a single page's /llms.txt.

    A page document fetched in isolation is a dead end. An agent handed
    ``https://docs.example.com/getting-started/llms.txt`` learns
    everything about that page and nothing about where it sits — not the
    other pages on the site, not the other hosts in the network, not where
    the index lives. There is no link to follow, so exploration stops.

    This block is the way out. It is deliberately three lines: an agent that
    only wants the prose skips it in a few tokens, and one that wants to
    explore has the two URLs that matter.
    """
    base_url = str(getattr(app, "_base_url", "") or "").rstrip("/")
    page_path = _normalize_page_path(page_path)

    # The site index is decorated when this request carries authority, so an
    # agent handed an authorised document can follow the link and still be
    # authorised. The sitemap is not: it is a public document, and a key in it
    # would be both useless and a leak.
    site_index = access.decorate(f"{base_url}/llms.txt" if base_url else "/llms.txt")
    sitemap = f"{base_url}/sitemap.xml" if base_url else "/sitemap.xml"

    lines = [
        f"**Site index:** [{site_index}]({site_index}) — every page on this site, as Markdown.",
    ]

    network = getattr(state, "network", None) if state is not None else None
    if network is not None and not network.is_empty:
        hub = (network.hub_url or "").rstrip("/")
        if hub:
            hub_index = f"{hub}/llms.txt"
            label = network.name or "the wider network"
            lines.append(
                f"**Network index:** [{hub_index}]({hub_index}) — {label}; "
                f"start here to discover sibling sites."
            )
        peers = network.by_tier("peer")
        if peers:
            lines.append(
                f"**Sibling sites:** {len(peers)} more in "
                f"{network.name or 'this network'} — listed in the site index above."
            )

    lines.append(f"**Sitemap:** {sitemap}")

    return "\n".join(f"{line}  " for line in lines)


def insert_nav_block(document: str, nav_block: str) -> str:
    """
    Splice the nav block in after a document's title and tagline.

    Placing it above the H1 would push the page's own identity below
    boilerplate, and appending it at the end puts it past the point a
    long-document reader stops. So it goes directly after the heading and
    blockquote, which is where a reader looks for orientation.

    Falls back to prepending when the document has no recognisable heading.
    """
    if not nav_block:
        return document
    if not document:
        return nav_block + "\n"

    lines = document.splitlines()
    index = 0

    while index < len(lines) and not lines[index].strip():
        index += 1

    if index < len(lines) and lines[index].lstrip().startswith("# "):
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        # Consume a leading blockquote tagline, however many lines it spans.
        while index < len(lines) and lines[index].lstrip().startswith(">"):
            index += 1
    else:
        index = 0

    head = lines[:index]
    tail = lines[index:]

    block = ["", nav_block, ""]
    return "\n".join(head + block + tail).lstrip("\n") + "\n"


# Nav labels, not site identities. Dash convention is to register the
# landing page with name="Home" so the navbar link reads well — but "# Home"
# as the H1 of the site index identifies nothing (Home of *what*?), and every
# agent that fetches /llms.txt cold sees that H1 as the site's name. "Dash"
# is the Dash() constructor's default title, equally anonymous.
_GENERIC_SITE_TITLES = frozenset({"home", "homepage", "index", "main", "dash"})


def resolve_site_title(home_name: Any, app_title: Any) -> str:
    """
    Pick the H1 for the root /llms.txt.

    The registered home-page name wins over ``app.title`` — that ordering is
    what lets a site override the index title with a name-only
    ``register_page_metadata(path="/", name="my-package")`` without touching
    its navbar. But a *generic* value ("Home", "Index", Dash's default
    "Dash") is skipped rather than served, falling through to the next
    candidate, so a boilerplate nav label can never become the site's
    public identity.
    """
    candidates = [home_name, app_title]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        candidate = candidate.strip()
        if candidate and candidate.lower() not in _GENERIC_SITE_TITLES:
            return candidate
    # Everything was generic or missing — keep the old behaviour rather
    # than invent a name.
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return "Dash Application"


def build_policy_block(
    app: Any, state: Any = None, hidden_paths: Optional[set] = None
) -> List[str]:
    """The conduct contract, as document lines — W3 of the toll gate.

    Why this exists (the 2026-08-13 multiagent findings, distilled): agents
    are low-variance — one that finds a stated fetch discipline conforms to
    it, and one that finds nothing invents a poll loop, identically to
    every other agent. So the contract lives IN the document bytes: terms,
    identity, the rate rule, one coordination point, and the vendor policy
    summary rendered from the same registry robots.txt renders from, so
    the two can never drift.

    Hard constraint: these are SHARED document bytes and must stay
    identity-free — per-visitor state belongs in configure_viewer_identity,
    never here. This builder reads only config and state, no request data.

    Every input degrades: no robots config, no bulletin, no hub, no W4
    ceiling — each line simply drops out, and the section stays truthful
    on every host.
    """
    lines: List[str] = ["## Access policy", ""]

    llms_config = getattr(app, "_llms_config", None)
    metering_on = bool(getattr(llms_config, "metering", False))
    if metering_on:
        lines.append(
            "- Terms: documents marked free are free forever; a free account "
            "unlocks gated documents; anonymous bulk fetching of priced "
            "documents is metered."
        )
    else:
        lines.append(
            "- Terms: these documents are free to fetch. A free account "
            "unlocks any gated document."
        )

    # Identity: how to present a key, and where to get one. The sign-in URL
    # travels in the network bulletin so the whole network can move it with
    # one hub edit.
    sign_in_url = ""
    try:
        from .bulletin import get_bulletin

        bulletin = get_bulletin() or {}
        sign_in_url = str((bulletin.get("network") or {}).get("sign_in_url") or "")
    except Exception:  # pragma: no cover - bulletin is optional by design
        sign_in_url = ""
    identity = (
        "- Identity: agents may present a key by appending `?key=<value>` " "to any document URL."
    )
    if sign_in_url:
        identity += f" Get one: {sign_in_url}"
    lines.append(identity)

    # Rate contract. The numeric ceiling is W4's knob and degrades to the
    # behavioural rule alone until it lands. The bulk-fetch rule names
    # /llms-full.txt only where that tier is actually reachable — a denied
    # tier is not advertised anywhere, and the conduct contract does not
    # get an exemption from that rule.
    ceiling = getattr(llms_config, "rate_limit_per_minute", None)
    full_reachable = access.resolve(TIER_DOC_PATHS["full"], hidden_paths or set()) != access.DENY
    bulk = "ONE `/llms-full.txt` fetch" if full_reachable else "one bulk fetch"
    rate = (
        f"- Rate: prefer {bulk} over N per-page fetches. "
        "On 429, honour `Retry-After` and back off exponentially."
    )
    if ceiling:
        rate += f" Anonymous ceiling: {int(ceiling)} requests/minute."
    lines.append(rate)

    network = getattr(state, "network", None) if state is not None else None
    hub_url = str(getattr(network, "hub_url", "") or "").rstrip("/")
    if hub_url:
        lines.append(
            f"- Coordination: start at {hub_url}/llms.txt — one index "
            "enumerates every site; do not rediscover the network by "
            "crawling it."
        )

    robots_config = getattr(app, "_robots_config", None)
    if robots_config is not None:
        from .vendors import VENDORS, effective_policies

        policies = effective_policies(robots_config)
        by_policy: Dict[str, List[str]] = {"allow": [], "block": [], "meter": []}
        for vendor in VENDORS:
            if vendor.robots_tokens:  # never name what robots.txt never names
                by_policy[policies[vendor.key]].append(vendor.display)
        parts = []
        if by_policy["allow"]:
            parts.append("allowed: " + ", ".join(by_policy["allow"]))
        if by_policy["meter"]:
            parts.append("metered: " + ", ".join(by_policy["meter"]))
        if by_policy["block"]:
            parts.append("blocked: " + ", ".join(by_policy["block"]))
        if parts:
            lines.append("- Crawler policy (mirrors /robots.txt): " + "; ".join(parts) + ".")

    lines.append("")
    return lines


def build_llms_index(
    app: Any,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
    state: Any = None,
    user_agent: str = "",
) -> str:
    """
    Build the root /llms.txt — the app's index, in llmstxt.org format.

    This is the single document an agent should be able to fetch to
    understand what the app is, enumerate every page, and find its way to
    sibling hosts. Previously the root just echoed the home page's prose,
    which told a reader what the landing page said and nothing about the
    other 27 URLs.

    Layout:
        # App name
        > tagline
        <home page prose>
        ## Pages          — every visible page, with its own llms.txt
        ## Network        — sibling hosts (see network.py for the tiers)
        ## Related projects
        ## External references
    """
    base_url = str(getattr(app, "_base_url", "") or "").rstrip("/")

    home_meta = page_metadata.get("/") or {}
    home_entry = _find_page("/")
    home_doc = _resolve_llms_doc("/", page_metadata, home_entry)

    site_title = resolve_site_title(home_meta.get("name"), getattr(app, "title", None))
    lines: List[str] = [f"# {site_title}", ""]

    tagline = home_meta.get("description") or (home_entry or {}).get("description")
    if tagline:
        lines += [f"> {tagline}", ""]

    if home_doc:
        # Strip the doc's own H1 — the index already opened with one, and two
        # top-level headings in one document reads as two documents.
        body = home_doc.strip()
        if body.startswith("# "):
            body = body.split("\n", 1)[1].lstrip() if "\n" in body else ""
        lines += [body.strip(), ""]

    pages = _visible_pages(page_metadata, hidden_paths)

    # Advertise the other two sizes of this document, above the page listing
    # so an agent with a tight budget finds the small tier before it has paid
    # for the enumeration. A denied tier is not advertised — same rule as a
    # denied page.
    tier_lines: List[str] = []
    small_path = TIER_DOC_PATHS["small"]
    if access.resolve(small_path, hidden_paths) != access.DENY:
        url = access.decorate(f"{base_url}{small_path}" if base_url else small_path)
        tier_lines.append(
            f"- [{small_path}]({url}): compact briefing — start here if context is tight."
        )
    full_path = TIER_DOC_PATHS["full"]
    if access.resolve(full_path, hidden_paths) != access.DENY:
        url = access.decorate(f"{base_url}{full_path}" if base_url else full_path)
        tier_lines.append(
            f"- [{full_path}]({url}): every page's prose in one document " f"({len(pages)} pages)."
        )
    if tier_lines:
        # Under its own heading: the home page's prose ends with whatever the
        # author wrote — often a bullet list — and an unlabelled list appended
        # straight onto it reads as more of the author's list, not as this
        # document offered at two other sizes.
        lines += ["## Other sizes of this document", ""] + tier_lines + [""]

    # The conduct contract sits after the size pointers and before the
    # enumeration: an agent reads the terms before it starts fetching.
    lines += build_policy_block(app, state, hidden_paths)

    if pages:
        lines += [
            "## Pages",
            "",
            "Every page in this application. Each has a Markdown version at "
            "the `llms.txt` URL beside it.",
            "",
        ]
        for page in pages:
            path = page["path"]
            url = f"{base_url}{path}" if base_url else path
            # The root's document lives at /llms.txt, not //llms.txt.
            llms_url = f"{base_url}/llms.txt" if path == "/" else f"{url}/llms.txt"
            # Only the document URL is decorated. Authority unlocks documents,
            # not pages, so putting a key on the page link would promise
            # something it cannot deliver.
            llms_url = access.decorate(llms_url)
            suffix = f": {page['description']}" if page["description"] else ""
            lines.append(f"- [{page['name']}]({url}){suffix}")
            lines.append(f"  - Machine-readable: {llms_url}")
        lines.append("")

    if state is not None:
        try:
            from .network import build_directory_markdown

            directory = build_directory_markdown(state)
            if directory:
                lines.append(directory)
        except Exception:
            logger.debug("network directory unavailable", exc_info=True)

    # Same-origin document links only: the network directory in this same body
    # names peer hosts, and this key is not theirs to receive.
    return access.decorate_body(
        "\n".join(lines).rstrip() + "\n",
        str(getattr(app, "_base_url", "") or ""),
    )


def _visible_pages(
    page_metadata: Dict[str, Dict[str, Any]], hidden_paths: set
) -> List[Dict[str, str]]:
    """Every listable page, sorted by path, with resolved name/description.

    "Listable" is not "readable": a ``gated`` page stays in the index because
    the URL is public even when the content is not. Only ``deny`` removes it.
    """
    try:
        import dash
    except ImportError:
        return []

    registry = getattr(dash, "page_registry", None) or {}
    pages: List[Dict[str, str]] = []
    for entry in registry.values():
        path = _normalize_page_path(entry.get("path") or "/")
        if not access.is_listable(path, hidden_paths):
            continue
        meta = page_metadata.get(path) or {}
        pages.append(
            {
                "path": path,
                "name": str(meta.get("name") or entry.get("name") or path),
                "description": str(meta.get("description") or entry.get("description") or ""),
            }
        )
    pages.sort(key=lambda p: p["path"])
    return pages


# ---------------------------------------------------------------------------
# Tiered corpus documents — /llms-small.txt and /llms-full.txt
# ---------------------------------------------------------------------------
#
# The Svelte docs popularised serving llms.txt at more than one size: one
# document cannot be both small enough to sit whole in a tight context
# window and complete enough to feed an offline ingestion job. The root
# /llms.txt stays the medium index and advertises the other two.


TIER_DOC_PATHS: Dict[str, str] = {
    "small": "/llms-small.txt",
    "full": "/llms-full.txt",
}

# Default identity per tier. Seeded into page_metadata at registration so a
# gated tier never renders its gate document as "# /llms-full.txt".
TIER_DOC_META: Dict[str, Dict[str, str]] = {
    "small": {
        "name": "Compact briefing",
        "description": "The whole site in a few hundred tokens — for tight context windows.",
    },
    "full": {
        "name": "Full corpus",
        "description": "Every page's prose in one document — for offline ingestion.",
    },
}


def _first_paragraph(doc: str, max_chars: int = 600) -> str:
    """The first prose paragraph of a document, without its H1 or tagline."""
    lines: List[str] = []
    for line in (doc or "").strip().splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        if not lines and (stripped.startswith("# ") or stripped.startswith(">")):
            continue
        if stripped.startswith("#"):
            # A later heading with no prose before it — there is no intro.
            break
        lines.append(stripped)
    paragraph = " ".join(lines)
    if len(paragraph) > max_chars:
        paragraph = paragraph[: max_chars - 1].rstrip() + "…"
    return paragraph


def build_llms_small(
    app: Any,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
    state: Any = None,
    user_agent: str = "",
) -> str:
    """
    Build /llms-small.txt — the compact briefing.

    An application that registers its own prose for the tier path serves it
    verbatim (``register_page_metadata("/llms-small.txt", llms_doc=...)``).
    Otherwise the briefing is synthesized: the site's identity, the home
    page's first paragraph, one line per listable page, and pointers to the
    two larger documents. Page links point at each page's *document*, not
    the page itself, because the reader of this file is an agent choosing
    what to fetch next.
    """
    override = (page_metadata.get(TIER_DOC_PATHS["small"]) or {}).get("llms_doc")
    if override:
        return str(override)

    base_url = str(getattr(app, "_base_url", "") or "").rstrip("/")

    home_meta = page_metadata.get("/") or {}
    home_entry = _find_page("/")

    site_title = resolve_site_title(home_meta.get("name"), getattr(app, "title", None))
    lines: List[str] = [f"# {site_title}", ""]

    tagline = home_meta.get("description") or (home_entry or {}).get("description")
    if tagline:
        lines += [f"> {tagline}", ""]

    intro = _first_paragraph(_resolve_llms_doc("/", page_metadata, home_entry) or "")
    if intro:
        lines += [intro, ""]

    pages = _visible_pages(page_metadata, hidden_paths)
    if pages:
        lines += ["## Pages", ""]
        for page in pages:
            path = page["path"]
            url = f"{base_url}{path}" if base_url else path
            # The root's document lives at /llms.txt, not //llms.txt.
            llms_url = f"{base_url}/llms.txt" if path == "/" else f"{url}/llms.txt"
            llms_url = access.decorate(llms_url)
            suffix = f": {page['description']}" if page["description"] else ""
            lines.append(f"- [{page['name']}]({llms_url}){suffix}")
        lines.append("")

    index_url = access.decorate(f"{base_url}/llms.txt" if base_url else "/llms.txt")
    full_url = access.decorate(
        f"{base_url}{TIER_DOC_PATHS['full']}" if base_url else TIER_DOC_PATHS["full"]
    )
    # A list, not three loose lines: consecutive lines with no blank line
    # between them are one paragraph in Markdown, so the pointers rendered
    # as a single run-on sentence — in the one document whose whole job is
    # to be read quickly.
    lines += ["## Other documents", ""]
    lines += [
        f"- Page index: {index_url}",
        f"- Full corpus: {full_url}",
    ]

    network = getattr(state, "network", None) if state is not None else None
    if network is not None and not network.is_empty:
        hub = (network.hub_url or "").rstrip("/")
        if hub:
            lines.append(f"- Network hub: {hub}/llms.txt — {network.name or 'the wider network'}.")

    # The conduct contract closes the briefing (W3): the small tier is the
    # document an agent with a tight budget reads INSTEAD of the index, so
    # it must carry the same terms.
    lines += [""] + build_policy_block(app, state, hidden_paths)

    return "\n".join(lines).rstrip() + "\n"


def _corpus_pages(
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
) -> List[Dict[str, Any]]:
    """Every page the corpus may name, sorted by path, with its verdict.

    ``resolve()`` is called exactly once per page: the verdict decides both
    whether the page appears and what body it contributes, and resolving
    twice would let a time-varying check answer each question differently.
    ``deny`` pages are omitted here, so no later step can leak one.
    """
    try:
        import dash
    except ImportError:
        return []

    registry = getattr(dash, "page_registry", None) or {}
    pages: List[Dict[str, Any]] = []
    for entry in registry.values():
        path = _normalize_page_path(entry.get("path") or "/")
        verdict = access.resolve(path, hidden_paths)
        if verdict == access.DENY:
            continue
        meta = page_metadata.get(path) or {}
        pages.append(
            {
                "path": path,
                "name": str(meta.get("name") or entry.get("name") or path),
                "description": str(meta.get("description") or entry.get("description") or ""),
                "verdict": verdict,
                "entry": entry,
            }
        )
    pages.sort(key=lambda p: p["path"])
    return pages


def build_llms_full(
    app: Any,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
    state: Any = None,
    max_bytes: int = 4_000_000,
    user_agent: str = "",
) -> str:
    """
    Build /llms-full.txt — every page's prose in one document.

    Each page's prose appears verbatim, with **no** navigation block: the
    corpus is one document, and a per-page "way out" repeated N times is
    noise. A source comment above each page keeps every passage traceable
    back to the page's own llms.txt. Gated pages contribute their gate
    document rather than prose — the corpus must never hold the text the
    per-page route withholds. Denied pages are omitted entirely.

    The byte budget is enforced page-by-page in path order: the first page
    that would push the document past ``max_bytes`` stops the corpus, and
    everything from there on is listed as links under "Not included" rather
    than silently dropped. Compression is deliberately left to the proxy.
    """
    base_url = str(getattr(app, "_base_url", "") or "").rstrip("/")

    home_meta = page_metadata.get("/") or {}
    home_entry = _find_page("/")
    site_title = resolve_site_title(home_meta.get("name"), getattr(app, "title", None))

    pages = _corpus_pages(page_metadata, hidden_paths)

    lines: List[str] = [f"# {site_title} — full corpus", ""]

    # The conduct contract heads the corpus (W3): this is the single
    # document the rate rule tells agents to prefer, so the terms travel
    # with it.
    lines += build_policy_block(app, state, hidden_paths)
    tagline = home_meta.get("description") or (home_entry or {}).get("description")
    if tagline:
        lines += [f"> {tagline}", ""]

    index_url = f"{base_url}/llms.txt" if base_url else "/llms.txt"
    small_url = f"{base_url}{TIER_DOC_PATHS['small']}" if base_url else TIER_DOC_PATHS["small"]
    plural = "s" if len(pages) != 1 else ""
    lines.append(
        f"Generated from {len(pages)} page{plural}. The page index lives at "
        f"{index_url} and a compact briefing at {small_url}; each page also "
        f"serves its own document at `<page>/llms.txt`."
    )

    body = "\n".join(lines)
    used = len(body.encode("utf-8"))
    overflow: List[Dict[str, Any]] = []

    for page in pages:
        if overflow:
            # The cap was hit on an earlier page. Order is the contract —
            # squeezing a smaller later page in would reorder the corpus
            # relative to the index.
            overflow.append(page)
            continue

        path = page["path"]
        doc_path = "/llms.txt" if path == "/" else f"{path}/llms.txt"
        doc_url = f"{base_url}{doc_path}" if base_url else doc_path

        if page["verdict"] == access.GATED:
            content = access.gate_document(path, page_metadata, state).strip()
        else:
            prose = _resolve_llms_doc(path, page_metadata, page["entry"])
            if prose:
                content = prose.strip()
            else:
                content = f"_No prose registered for `{path}` — see {doc_path}._"

        chunk = f"\n\n---\n\n<!-- {path} — {doc_url} -->\n\n{content}"
        chunk_bytes = len(chunk.encode("utf-8"))
        if used + chunk_bytes > max_bytes:
            overflow.append(page)
            continue
        body += chunk
        used += chunk_bytes

    if overflow:
        listing = ["", "---", "", "## Not included (size cap)", ""]
        for page in overflow:
            path = page["path"]
            doc_path = "/llms.txt" if path == "/" else f"{path}/llms.txt"
            doc_url = f"{base_url}{doc_path}" if base_url else doc_path
            listing.append(f"- [{page['name']}]({doc_url})")
        body += "\n" + "\n".join(listing)

    # Carry authority across every same-origin document link, source
    # comments included — an agent handed an authorised corpus follows them.
    return access.decorate_body(
        body.rstrip() + "\n",
        str(getattr(app, "_base_url", "") or ""),
    )


def build_llms_tier_doc(
    app: Any,
    tier: str,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
    state: Any = None,
    full_max_bytes: int = 4_000_000,
) -> Tuple[str, int]:
    """
    Build the body of one tier document. Returns (body, status).

    Kept as a single pure verdict→response mapping on purpose: this is the
    seam where a future release maps a ``priced`` verdict to HTTP 402, and
    the payment branch will slot in here without the adapters changing.
    """
    tier_path = TIER_DOC_PATHS[tier]
    verdict = access.resolve(tier_path, hidden_paths)

    if verdict == access.DENY:
        return ("Document not available", 404)

    if verdict == access.GATED:
        return (access.gate_document(tier_path, page_metadata, state), 200)

    if tier == "small":
        return (build_llms_small(app, page_metadata, hidden_paths, state), 200)
    return (
        build_llms_full(app, page_metadata, hidden_paths, state, max_bytes=full_max_bytes),
        200,
    )


# Every other document renders in the browser exactly as an agent receives
# it, and the viewer chrome says so. The full tier is the one exception —
# the browser gets the card above, the agent gets the corpus — so it must
# say something else, or the chrome states a falsehood on the one surface
# whose whole promise is that machines and humans are reading the same bytes.
LLMS_FULL_VIEWER_NOTE = (
    "agents fetching this URL receive the full corpus itself, not the summary rendered below."
)


def build_llms_full_summary(app: Any, corpus: str) -> str:
    """
    The browser-facing stand-in for /llms-full.txt.

    The corpus can run to megabytes, and rendering that through the viewer
    would freeze the tab — so a browser gets this card instead: what the
    document is, how big it is, and where the real thing lives. Agents,
    crawlers and ``?raw=1`` receive the corpus itself from the same URL.
    """
    size = len(corpus.encode("utf-8"))
    if size >= 1_000_000:
        size_label = f"{size / 1_000_000:.1f} MB"
    elif size >= 1_000:
        size_label = f"{size / 1_000:.0f} kB"
    else:
        size_label = f"{size} bytes"

    page_count = corpus.count("\n\n---\n\n<!-- ")

    small_path = TIER_DOC_PATHS["small"]
    full_path = TIER_DOC_PATHS["full"]
    raw_url = access.decorate(f"{full_path}?raw=1")
    small_url = access.decorate(small_path)
    index_url = access.decorate("/llms.txt")

    return (
        "# Full corpus\n\n"
        f"> Every page's prose in one document — {page_count} pages, {size_label}.\n\n"
        "This document is built for agents and offline ingestion, not for "
        f"reading in a browser; rendering {size_label} of Markdown here would "
        "help nobody. The corpus itself is one click away:\n\n"
        f"- **Raw corpus:** [{full_path}?raw=1]({raw_url}) — the complete "
        "document, as Markdown.\n"
        f"- **Compact briefing:** [{small_path}]({small_url}) — the whole "
        "site in a few hundred tokens.\n"
        f"- **Page index:** [/llms.txt]({index_url}) — every page, each with "
        "its own document.\n\n"
        "Agents and crawlers fetching this same URL receive the corpus "
        "directly.\n"
    )


def build_llms_txt_for_page(
    app: Any,
    page_path: str,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
    state: Any = None,
    include_nav: bool = True,
    user_agent: str = "",
) -> Optional[Tuple[str, int]]:
    """
    Build the body of /llms.txt for one page.

    The root path returns the app index (see build_llms_index); every other
    path returns that page's prose, prefixed with a navigation block so the
    document isn't a dead end (see build_page_nav_block).

    ``user_agent`` (W4): threaded from the adapters so W5's metering and
    per-vendor DOCUMENT policy can differentiate readers. Unused until
    then — passing it changes nothing, which is the point of landing the
    threading before the consumers.

    Returns (body, status) — 200 on success, 200 with the gate document when
    the application gates this requester, 404 if the path is denied or
    unknown. Returns None ONLY if dash itself isn't importable (signal to the
    adapter to 500).
    """
    page_path = _normalize_page_path(page_path)

    verdict = access.resolve(page_path, hidden_paths)
    if verdict == access.DENY:
        return ("Page not available", 404)

    # A gated page still gets its nav block: the point of serving 200 rather
    # than 404 is that the reader learns what this is and where to get access,
    # and the links are half of that.
    if verdict == access.GATED and page_path != "/":
        doc = access.gate_document(page_path, page_metadata, state)
        if include_nav:
            doc = insert_nav_block(doc, build_page_nav_block(app, page_path, state))
        return (doc, 200)

    if page_path == "/":
        return (
            build_llms_index(
                app=app,
                page_metadata=page_metadata,
                hidden_paths=hidden_paths,
                state=state,
            ),
            200,
        )

    page_entry = _find_page(page_path)
    if page_entry is None:
        return (f"llms.txt not available for {page_path}", 404)

    doc = _resolve_llms_doc(page_path, page_metadata, page_entry)
    if not doc:
        meta = page_metadata.get(page_path) or {}
        page_name = meta.get("name") or page_entry.get("name") or page_path
        description = meta.get("description") or ""
        doc = _stub_llms_txt(page_name, page_path, description)

    if include_nav:
        doc = insert_nav_block(doc, build_page_nav_block(app, page_path, state))

    # Carry authority across the document's own links, so an agent given one
    # authorised URL can follow the others instead of hitting a gate one hop in.
    doc = access.decorate_body(doc, str(getattr(app, "_base_url", "") or ""))

    return (doc, 200)


# ---------------------------------------------------------------------------
# Content negotiation for /llms.txt
# ---------------------------------------------------------------------------

_RAW_QUERY_VALUES = ("1", "true", "yes", "md", "markdown", "raw", "text")


def wants_html_viewer(
    *,
    accept: str = "",
    user_agent: str = "",
    query: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Decide whether this request should get the rendered viewer.

    The default is Markdown, and the checks are ordered so that anything
    ambiguous stays Markdown. Serving HTML to something that wanted the
    document would defeat the entire purpose of the route, whereas serving
    Markdown to a browser is merely less pretty — so the asymmetry in
    consequences decides the default.

    Escape hatches, in precedence order:
      ``?raw=1`` / ``?format=md``  → always Markdown.
      ``?format=html``            → always HTML (lets you preview it).
    """
    query = query or {}

    raw = str(query.get("raw", "")).lower()
    fmt = str(query.get("format", "")).lower()

    if raw in _RAW_QUERY_VALUES or fmt in _RAW_QUERY_VALUES:
        return False
    if fmt == "html":
        return True

    # Crawlers and agents get the document, whatever they claim to Accept.
    if is_any_bot(user_agent or ""):
        return False

    accept = (accept or "").lower()
    if "text/html" not in accept:
        return False

    # `Accept: */*` (curl, most SDK HTTP clients, many fetchers) contains no
    # explicit text/html, so it already returned above. Reaching here means
    # text/html was named — but only prefer HTML if it outranks plain text,
    # which is what a browser sends and a Markdown-aware client does not.
    return _accept_rank(accept, "text/html") >= _accept_rank(accept, "text/plain")


def _accept_rank(accept: str, media_type: str) -> float:
    """Quality value for a media type in an Accept header, 0.0 if absent."""
    best = 0.0
    for part in accept.split(","):
        segments = part.strip().split(";")
        name = segments[0].strip()
        if name != media_type:
            continue
        quality = 1.0
        for segment in segments[1:]:
            key, _, value = segment.partition("=")
            if key.strip() == "q":
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 1.0
        best = max(best, quality)
    return best


def build_llms_viewer_html(
    *,
    app: Any,
    page_path: str,
    markdown_body: str,
    page_metadata: Dict[str, Dict[str, Any]],
    state: Any = None,
    raw_url: Optional[str] = None,
    page_name: Optional[str] = None,
    source_note: str = "",
) -> Optional[str]:
    """Render the browser-facing view of an llms.txt document.

    ``raw_url`` and ``page_name`` override the computed values for documents
    that are not page documents — the tier docs live at ``/llms-small.txt``,
    not ``/<page>/llms.txt``, so the derived raw link would point nowhere.
    ``source_note`` overrides the chrome's description of what an agent gets
    from this URL; only /llms-full.txt needs it (see LLMS_FULL_VIEWER_NOTE).
    """
    try:
        from .bulletin import get_bulletin
        from .llms_viewer import render_llms_viewer
    except ImportError:
        return None

    page_path = _normalize_page_path(page_path)
    base_url = str(getattr(app, "_base_url", "") or "").rstrip("/")

    meta = page_metadata.get(page_path) or {}
    entry = _find_page(page_path)
    if page_name is None:
        page_name = meta.get("name") or (entry or {}).get("name") or page_path

    network = getattr(state, "network", None) if state is not None else None
    hub = (getattr(network, "hub_url", "") or "").rstrip("/") if network else ""

    if raw_url is None:
        raw_url = "/llms.txt" if page_path == "/" else f"{page_path}/llms.txt"

    try:
        return render_llms_viewer(
            markdown_body=markdown_body,
            page_name=str(page_name),
            # The brand chip in the viewer banner — same resolution as the
            # /llms.txt H1 so the chrome and the document never disagree.
            app_name=resolve_site_title(
                (page_metadata.get("/") or {}).get("name"),
                getattr(app, "title", None) or "Documentation",
            ),
            raw_url=raw_url,
            source_note=source_note,
            site_llms_url=f"{base_url}/llms.txt" if base_url else "/llms.txt",
            network_name=getattr(network, "name", "") or "" if network else "",
            network_url=hub,
            network_llms_url=f"{hub}/llms.txt" if hub else "",
            bulletin=get_bulletin(),
            wordmark=getattr(network, "wordmark", None) if network else None,
        )
    except Exception:
        logger.exception(
            "dash-improve-my-llms: llms.txt viewer failed for %s; " "serving the Markdown instead.",
            page_path,
        )
        return None


# ---------------------------------------------------------------------------
# /robots.txt
# ---------------------------------------------------------------------------


def build_robots_txt(app: Any) -> str:
    """Build the body of /robots.txt from app._robots_config + app._base_url."""
    robots_config = getattr(app, "_robots_config", None) or RobotsConfig()
    base_url = getattr(app, "_base_url", "https://example.com")
    return generate_robots_txt(
        config=robots_config,
        sitemap_url=f"{base_url}/sitemap.xml",
        base_url=base_url,
    )


# ---------------------------------------------------------------------------
# /sitemap.xml
# ---------------------------------------------------------------------------


def build_sitemap_xml(
    app: Any,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
) -> str:
    """Build the body of /sitemap.xml from dash.page_registry."""
    try:
        import dash
    except ImportError:
        dash = None  # type: ignore

    registry = getattr(dash, "page_registry", None) or {} if dash else {}
    pages: List[Dict[str, Any]] = []
    for entry in registry.values():
        path = _normalize_page_path(entry.get("path") or "/")
        # Gated pages stay in the sitemap: the URL is public, the content is
        # not, and de-listing would hide that the page exists at all.
        if not access.is_listable(path, hidden_paths):
            continue
        meta = page_metadata.get(path) or {}
        pages.append(
            {
                "path": path,
                "name": meta.get("name") or entry.get("name", "Page"),
                "description": meta.get("description", ""),
                # register_page_metadata(lastmod="YYYY-MM-DD") — omitted from
                # the XML entirely when the app never said. Truth or silence.
                "lastmod": str(meta.get("lastmod") or ""),
                "hidden": False,
            }
        )

    base_url = getattr(app, "_base_url", "https://example.com")
    return generate_sitemap_xml(pages=pages, base_url=base_url, hidden_paths=list(hidden_paths))


# ---------------------------------------------------------------------------
# Bot middleware decision
# ---------------------------------------------------------------------------


# The tier documents are listed explicitly: "/llms-small.txt" does not end
# with "/llms.txt", so without these entries the bot middleware would treat
# the tier routes as ordinary pages — and block_ai_training would serve
# training bots a 403 on the very documents that exist for them.
#
# The corpus is CONTENT and may be gated (`block_ai_training_docs`). The
# policy routes never are: robots.txt is the channel that tells a blocked
# bot "Disallow: /", and RFC 9309 treats an unreadable (4xx) robots.txt as
# no-rules-at-all — so 403ing it would silence the very signal that asks
# the bot to stop requesting.
_CORPUS_ROUTE_SUFFIXES: Tuple[str, ...] = (
    "/llms.txt",
    "/llms-small.txt",
    "/llms-full.txt",
)
_POLICY_ROUTE_SUFFIXES: Tuple[str, ...] = (
    "/robots.txt",
    "/sitemap.xml",
)
_DOC_ROUTE_SUFFIXES: Tuple[str, ...] = _CORPUS_ROUTE_SUFFIXES + _POLICY_ROUTE_SUFFIXES
_ASSET_MARKERS: Tuple[str, ...] = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    "_dash",
    "_reload-hash",
    "/favicon",
)


def _is_asset_path(path: str) -> bool:
    return any(marker in path for marker in _ASSET_MARKERS)


def _is_documentation_route(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _DOC_ROUTE_SUFFIXES)


def handle_bot_request(
    *,
    path: str,
    user_agent: str,
    app: Any,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
    headers: Optional[Mapping[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Decide whether to short-circuit a request.

    Returns:
        None — continue to the normal Dash handler.
        Dict — return this directly to the client. Shape:
            {
                "status": int,
                "body": str,
                "content_type": str,
                "headers": dict,
            }
    """
    # The geo guardrail runs before EVERYTHING — the asset short-circuit
    # below (which would wave through /assets/* and the
    # /_dash-update-component POSTs that carry client-side navigation)
    # and the is_any_bot gate (which would exempt humans). "451 on all
    # surfaces" is one enforcement point with nothing to drift; when geo
    # is unconfigured this is a single None-check.
    geo_response = geo.gate(path=path, headers=headers)
    if geo_response is not None:
        return geo_response

    if _is_asset_path(path):
        return None

    # Documentation routes used to short-circuit here unconditionally, which
    # meant `block_ai_training=True` protected every page EXCEPT the corpus —
    # the one surface built to be read by machines and the only one worth
    # metering. They are now subject to policy like anything else, but the
    # DEFAULT still lets them through: the documents exist to get the
    # packages used, and an upgrade must not silently start 403ing them.
    is_doc_route = _is_documentation_route(path)

    if not is_any_bot(user_agent):
        return None

    bot_type = get_bot_type(user_agent)
    robots_config: Optional[RobotsConfig] = getattr(app, "_robots_config", None)

    # W2: the SAME effective-policy fold robots.txt renders from decides
    # what the middleware does — what the site says and what it does are
    # one source, by construction. With vendor_policy unset the fold
    # reproduces the coarse flags, so this block behaves exactly as the
    # training-only branch it replaced.
    effective = None
    explicitly_policied = False
    if robots_config is not None:
        from .vendors import effective_policies, get_bot_vendor, vendor_overrides

        vendor_key = get_bot_vendor(user_agent)
        if vendor_key is not None:
            effective = effective_policies(robots_config).get(vendor_key)
            explicitly_policied = vendor_key in vendor_overrides(robots_config)
        elif bot_type == "traditional":
            # Generic-pattern bots with no vendor identity — the
            # unenumerated-AI residue of P2. CLI tools are deliberately
            # exempt: they are the paste-into-chat lane.
            posture = getattr(robots_config, "default_unknown_ai", "allow")
            ua_lower = user_agent.lower()
            is_cli = any(t in ua_lower for t in ("curl", "wget", "python-requests"))
            if posture in ("block", "meter") and not is_cli:
                effective = posture

    if effective == "block":
        # `block_ai_training_docs` is the opt-in, and the seam the
        # per-vendor `meter` policy slots into: the decision about who may
        # read the corpus belongs here, not in a hard-coded exemption. It
        # gates the CORPUS routes only — robots.txt and sitemap.xml stay
        # readable even by a blocked bot, because they are where the block
        # itself is announced. The same carve-out applies to every blocked
        # vendor, not only the training class: the documents exist to get
        # the packages used, and an upgrade must not silently 403 them.
        docs_blocked = getattr(robots_config, "block_ai_training_docs", False)
        is_corpus_route = any(path.endswith(suffix) for suffix in _CORPUS_ROUTE_SUFFIXES)
        if not is_doc_route or (docs_blocked and is_corpus_route):
            if bot_type == "training":
                body = (
                    "403 Forbidden - AI training bots are not allowed to access this content.\n"
                    "This site blocks AI training bots to prevent unauthorized use of content "
                    "for model training.\n"
                    f"Bot detected: {user_agent[:100]}\n"
                    "For more information, see /robots.txt"
                )
            else:
                body = (
                    "403 Forbidden - This crawler is not permitted to access this content.\n"
                    f"Bot detected: {user_agent[:100]}\n"
                    "For more information, see /robots.txt"
                )
            return {
                "status": 403,
                "body": body,
                "content_type": "text/plain",
                "headers": {},
            }
    # effective == "meter": fetchable under the rate contract. Enforced by
    # the limiter once W4 lands; until then it behaves as allow.

    # W4 — the rate contract, enforced. Bot traffic against the CORPUS
    # routes only (policy routes are where the rules are announced and are
    # never limited; humans are never limited — the stampede is an agent
    # failure mode), keyed on the client IP the edge headers carry. FAIL
    # OPEN on absolutely anything: a limiter bug must never black-hole the
    # corpus — the one place the package's fail-closed instinct is wrong.
    llms_config = getattr(app, "_llms_config", None)
    ceiling = getattr(llms_config, "rate_limit_per_minute", None)
    if ceiling and is_doc_route:
        is_corpus = any(path.endswith(suffix) for suffix in _CORPUS_ROUTE_SUFFIXES)
        if is_corpus:
            try:
                from . import _rate_limit
                from ._headers import client_ip

                key = client_ip(headers) or f"ua:{user_agent[:64]}"
                retry_after = _rate_limit.check(key, int(ceiling))
            except Exception:
                retry_after = None  # fail open
            if retry_after is not None:
                return {
                    "status": 429,
                    "body": (
                        "429 Too Many Requests - anonymous bulk fetching is "
                        "rate-limited.\n"
                        "Prefer ONE /llms-full.txt fetch over N per-page "
                        "fetches, honour Retry-After, and back off "
                        "exponentially. See the Access policy section of "
                        "/llms.txt.\n"
                    ),
                    "content_type": "text/plain",
                    "headers": {
                        "Retry-After": str(retry_after),
                        "Cache-Control": "no-store",
                    },
                }

    # A documentation route that survived policy is served by its own handler,
    # which runs the access verdict itself. Never fall through to the page
    # branches below — they would render the app shell for /llms.txt.
    if is_doc_route:
        return None

    # An EXPLICIT vendor_policy allow/meter serves the crawler branch —
    # that is what "allow" means for a crawler. A vendor merely
    # not-blocked by the coarse flags keeps its historical fall-through
    # to the app (byte-identity for flag-only configs).
    if bot_type in ("search", "traditional") or (
        explicitly_policied and effective in ("allow", "meter")
    ):
        page_path = _normalize_page_path(path)

        verdict = access.resolve(page_path, hidden_paths)
        if verdict == access.DENY:
            return {
                "status": 404,
                "body": "404 Not Found - Page not available",
                "content_type": "text/plain",
                "headers": {},
            }

        # A crawler sees exactly what an anonymous human sees. Serving prose
        # here while gating the same content elsewhere would be cloaking, and
        # would make the gate pointless besides — the index would hold the
        # very text the gate withholds.
        if verdict == access.GATED:
            return {
                "status": 200,
                "body": access.gate_document(page_path, page_metadata, None),
                "content_type": "text/markdown; charset=utf-8",
                "headers": {},
            }

        html = _render_static_html_for_bot(
            app=app,
            page_path=page_path,
            page_metadata=page_metadata,
            hidden_paths=hidden_paths,
        )
        if html is None:
            return None

        headers = {}
        if robots_config and robots_config.block_ai_training:
            headers["X-Robots-Tag"] = "noai"
        return {
            "status": 200,
            "body": html,
            "content_type": "text/html",
            "headers": headers,
        }

    return None


def resolve_page_context(
    *,
    app: Any,
    page_path: str,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
) -> Optional[Dict[str, Any]]:
    """
    Gather everything needed to render a page for a non-JS consumer.

    Shared by the crawler HTML path and the universal prerender path so the
    two can never disagree about what a page's prose, title, or sibling
    links are — a split that would recreate exactly the crawler-sees-
    something-different problem the prerender is meant to remove.

    Returns None when the path isn't a known page.
    """
    try:
        import dash
    except ImportError:
        return None

    page_path = _normalize_page_path(page_path)
    registry = getattr(dash, "page_registry", None) or {}

    page_entry = None
    for entry in registry.values():
        if _normalize_page_path(entry.get("path") or "") == page_path:
            page_entry = entry
            break

    if page_entry is None:
        return None

    meta = page_metadata.get(page_path) or {}
    page_name = meta.get("name") or page_entry.get("name") or page_path
    description = meta.get("description") or page_entry.get("description") or f"View {page_name}"

    all_pages = []
    for entry in registry.values():
        p_path = _normalize_page_path(entry.get("path") or "/")
        if not access.is_listable(p_path, hidden_paths):
            continue
        p_meta = page_metadata.get(p_path) or {}
        all_pages.append(
            {
                "path": p_path,
                "name": p_meta.get("name") or entry.get("name", "Page"),
                "description": p_meta.get("description") or entry.get("description", ""),
            }
        )
    all_pages.sort(key=lambda p: p["path"])

    return {
        "page_path": page_path,
        "page_metadata": {
            "name": page_name,
            "description": description,
            "path": page_path,
            "llms_doc": _resolve_llms_doc(page_path, page_metadata, page_entry),
            **{k: v for k, v in meta.items() if k not in ("name", "description")},
        },
        "all_pages": all_pages,
        "app_config": {
            # Same identity the root /llms.txt H1 uses, so og:title,
            # schema.org name, and the crawler-facing H1 all agree.
            "name": resolve_site_title(
                (page_metadata.get("/") or {}).get("name"),
                getattr(app, "title", None),
            ),
            "base_url": getattr(app, "_base_url", "https://example.com"),
        },
    }


# ---------------------------------------------------------------------------
# Universal prerender — same content for every visitor
# ---------------------------------------------------------------------------


def should_prerender(*, path: str, status: int, content_type: str) -> bool:
    """Cheap gate run on every response, before any page lookup."""
    if status != 200:
        return False
    if "text/html" not in (content_type or "").lower():
        return False
    return not (_is_asset_path(path) or _is_documentation_route(path))


def apply_prerender(
    *,
    document: str,
    app: Any,
    path: str,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
    state: Any = None,
) -> str:
    """
    Inject a page's prose and metadata into the Dash index HTML.

    Returns the document unchanged on any miss — an unknown path, a hidden
    page, or an unexpected document shape. A page that fails to prerender
    must still render as a working app.
    """
    page_path = _normalize_page_path(path)
    verdict = access.resolve(page_path, hidden_paths)
    if verdict == access.DENY:
        return document

    try:
        from .prerender import inject_prerender
    except ImportError:
        return document

    context = resolve_page_context(
        app=app,
        page_path=page_path,
        page_metadata=page_metadata,
        hidden_paths=hidden_paths,
    )
    if context is None:
        return document

    if verdict == access.GATED:
        # Swap the prose for the gate document but keep injecting. The head
        # metadata — per-page title, canonical, description, JSON-LD — is not
        # secret, and a gated page is still in the sitemap, so dropping the
        # injection entirely would put those pages back to sharing the app's
        # generic title and a homepage canonical.
        context["page_metadata"] = {
            **context["page_metadata"],
            "llms_doc": access.gate_document(page_path, page_metadata, state),
        }

    extra_sections: List[str] = []
    peers_html = ""
    if state is not None:
        try:
            from .network import build_directory_section, build_peer_link_tags

            extra_sections = build_directory_section(state)
            peers_html = build_peer_link_tags(state)
        except Exception:
            logger.debug("network directory unavailable", exc_info=True)

    try:
        return inject_prerender(
            document,
            context,
            extra_sections=extra_sections,
            peers_html=peers_html,
        )
    except Exception:
        logger.exception(
            "dash-improve-my-llms: prerender injection failed for %s; "
            "serving the unmodified app shell.",
            page_path,
        )
        return document


def _render_static_html_for_bot(
    *,
    app: Any,
    page_path: str,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
) -> Optional[str]:
    """Render the static HTML response for a crawler hitting a normal page URL."""
    try:
        from .html_generator import generate_static_page_html
    except ImportError:
        return None

    context = resolve_page_context(
        app=app,
        page_path=page_path,
        page_metadata=page_metadata,
        hidden_paths=hidden_paths,
    )
    if context is None:
        return None

    try:
        return generate_static_page_html(
            page_path=context["page_path"],
            page_metadata=context["page_metadata"],
            all_pages=context["all_pages"],
            app_config=context["app_config"],
        )
    except Exception:
        logger.exception(
            "dash-improve-my-llms: crawler HTML generation failed for %s; "
            "falling through to the JS app.",
            page_path,
        )
        return None
