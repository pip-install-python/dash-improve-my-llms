"""
dash-improve-my-llms 2.0 — crawler/SEO companion for Dash apps.

This release narrows the package's scope to the surfaces that
Dash 4.3's MCP server does NOT cover:

  1. /robots.txt           — bot-class access policies
  2. /sitemap.xml          — search-engine discovery
  3. /llms.txt per page    — prose docs for paste-into-chat use
  4. Static-HTML prerender — for crawlers that don't run JS
  5. MCP bridge            — register the same prose as dash.mcp resources

Component-tree extraction (/page.json, /architecture.txt, /llms.toon,
/architecture.toon) has been removed — Dash 4.3 MCP exposes that
information live and structured.

Usage:
    from dash import Dash, register_page
    from dash_improve_my_llms import add_llms_routes, RobotsConfig

    app = Dash(__name__, use_pages=True)
    app._base_url = "https://myapp.com"
    app._robots_config = RobotsConfig(block_ai_training=True)
    add_llms_routes(app)

Each page module provides its prose as a module-level LLMS_DOC string,
or via register_page_metadata(path, llms_doc="..."):

    # pages/equipment.py
    LLMS_DOC = '''
    # Equipment Catalog

    Browse equipment by category, search by name, filter by status.
    ...
    '''
"""

from __future__ import annotations

__version__ = "2.9.2"

import logging
import warnings
from typing import Any, Dict, List, Optional

from ._identity import configure_identity
from ._ledger import on_document_read
from ._paths import normalize_path as _normalize_path
from .access import configure_access, configure_viewer_identity
from .bot_detection import classify
from .bulletin import configure_bulletin
from .network import NetworkConfig, NetworkSite
from .robots_generator import RobotsConfig
from .seo import autoconfigure_icons, configure_seo, discover_icons
from .geo import configure_geo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared state — replaces module globals scattered through 1.x
# ---------------------------------------------------------------------------


class _State:
    """Container for module-level registries. One instance per process."""

    def __init__(self) -> None:
        self.page_metadata: Dict[str, Dict[str, Any]] = {}
        self.hidden_pages: set = set()
        self.network = NetworkConfig()


_state = _State()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class LLMSConfig:
    """Configuration for add_llms_routes()."""

    def __init__(
        self,
        enabled: bool = True,
        warn_missing_llms_doc: bool = True,
        register_mcp_resources: bool = True,
        prerender: bool = True,
        llms_nav: bool = True,
        llms_viewer: bool = True,
        llms_tiers: bool = True,
        llms_full_max_bytes: int = 4_000_000,
        rate_limit_per_minute: Optional[int] = None,
        metering: bool = False,
        panel: bool = False,
        panel_path: str = "/llms-policy",
        panel_token: Optional[str] = None,
    ) -> None:
        """
        Args:
            enabled: Master switch. False registers nothing at all.
            warn_missing_llms_doc: Emit a startup warning naming pages with
                no prose. Leave this on — a silent miss here is exactly how
                a site ends up serving stub bodies on most of its URLs.
            register_mcp_resources: Register each page's prose as a
                ``dash.mcp`` resource on Dash 4.3+.
            prerender: Inject each page's prose and metadata into the initial
                HTML for **every** visitor, not just recognised crawlers.
                Dash replaces the block when React mounts, so the interactive
                app is unaffected. Set False to fall back to serving rich
                HTML only to detected crawlers.
            llms_nav: Prefix each page's /llms.txt with a short navigation
                block pointing at the site index, the network index and the
                sitemap. Without it, a page document fetched in isolation has
                no links to follow and an agent's exploration stops there.
            llms_viewer: Serve a rendered HTML view of /llms.txt to browsers,
                while agents and crawlers keep receiving the identical
                Markdown from the same URL. The chrome exists only in the HTML
                variant, so it costs an agent nothing.
            llms_tiers: Serve the tiered corpus documents — /llms-small.txt
                (a compact briefing for tight context windows) and
                /llms-full.txt (every page's prose in one document). The
                root /llms.txt stays the medium index and advertises both.
            llms_full_max_bytes: Byte budget for /llms-full.txt. Pages past
                the cap are listed as links under "Not included (size cap)"
                instead of inlined. Compression is left to the proxy.
            rate_limit_per_minute: W4's anonymous-bulk ceiling. When set,
                bot traffic against the CORPUS routes (never /robots.txt
                or /sitemap.xml, never humans) is limited per client IP
                per worker; over-ceiling requests receive 429 with
                Retry-After — the machine-readable half of the conduct
                contract the documents publish. The limiter FAILS OPEN on
                any error: refusing to serve documents is worse than
                serving too many. None (default) disables it entirely —
                byte-identical behaviour. NOTE: per-process, so gunicorn's
                N workers give an effective ceiling of N x this value.
            metering: W5's 402 lane — WIRED, SHIPPED OFF. False (default)
                degrades a "priced" access verdict to gated, so a check
                returning it can neither publish prose nor charge; True
                lets it serve the offer document at 402 with the
                app-provided payment headers. Turning this on is gated on
                the crawl-data decision and the x402 prototype — one host,
                testnet — not on this release.
            panel: Register the read-only operator policy panel (P1) at
                ``panel_path``. False (default) registers nothing — the
                path keeps falling through to the app exactly as before.
            panel_path: Where the panel lives. Deliberately absent from
                robots.txt, the sitemap and the llms index.
            panel_token: The shared secret; falls back to the
                DIMLL_PANEL_TOKEN env var, read per-request so rotation
                needs no redeploy. Unset ⇒ the panel answers 404
                unconditionally (fails closed). See docs/PANEL.md.
        """
        self.enabled = enabled
        self.warn_missing_llms_doc = warn_missing_llms_doc
        self.register_mcp_resources = register_mcp_resources
        self.prerender = prerender
        self.llms_nav = llms_nav
        self.llms_viewer = llms_viewer
        self.llms_tiers = llms_tiers
        self.llms_full_max_bytes = llms_full_max_bytes
        self.rate_limit_per_minute = rate_limit_per_minute
        self.metering = metering
        self.panel = panel
        self.panel_path = panel_path
        self.panel_token = panel_token


# ---------------------------------------------------------------------------
# Public API: page-level metadata and hiding
# ---------------------------------------------------------------------------


def register_page_metadata(
    path: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    llms_doc: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Register supplemental metadata for a page.

    Calls MERGE into any existing entry for `path`. Passing None for a field
    leaves whatever was registered earlier intact — so a later bookkeeping
    call that only refreshes name/description can never blank out prose a
    page module registered at import time.

    Historically this assigned, and that cost real traffic: apps that looped
    over dash.page_registry to backfill titles silently erased every
    `llms_doc`, and every affected page served crawlers a bare
    "This page contains interactive content that requires JavaScript" stub.
    To deliberately clear a field, pass the empty string.

    The home page's `name` doubles as the site title: it is the H1 of the
    root /llms.txt, ahead of `app.title`. Register the package/site name
    there — `register_page_metadata(path="/", name="my-package")` — and keep
    "Home" on dash.register_page for the navbar. Generic labels ("Home",
    "Index", Dash's default "Dash") are never promoted to the index title;
    they fall through to `app.title`.

    Args:
        path: Page path (must match the path you passed to dash.register_page).
        name: Display name. Falls back to the dash.register_page name.
        description: One-sentence summary used in meta tags and sitemap.
        llms_doc: Optional prose body for /llms.txt and the prerendered page
            body. If omitted, the package looks for a module-level LLMS_DOC
            attribute on the page module.
        **kwargs: Additional SEO fields passed through to html_generator for
            the crawler-facing HTML. Consumed today:

            title       the full ``<title>`` for this page. Without it the
                        site name is appended to ``name`` — a crawler used to
                        receive the bare page name while the browser got the
                        application's own prefixed title.
            og_image    this page's social card, overriding the site default
                        from ``configure_seo(social_image=...)``. Advertised
                        here since 2.0 and read by nothing until 2.5.0.
            image_url   accepted as an alias, so a page that already passes
                        it to ``dash.register_page`` can pass the same value.
            schema_type schema.org ``@type`` (default ``WebPage``). Docs sites
                        want ``TechArticle``; a package's home page wants
                        ``SoftwareApplication``.
            lastmod     ``YYYY-MM-DD`` for this page's sitemap entry. When
                        absent the sitemap omits ``<lastmod>`` entirely —
                        it used to be invented as "today", and a field that
                        always says today is a field search engines learn
                        to ignore.
    """
    path = _normalize_path(path)
    entry = _state.page_metadata.setdefault(path, {})

    if name is not None:
        entry["name"] = name
    if description is not None:
        entry["description"] = description
    if llms_doc is not None:
        entry["llms_doc"] = llms_doc

    for key, value in kwargs.items():
        if value is not None:
            entry[key] = value


def mark_hidden(page_path: str) -> None:
    """
    Hide a page from crawlers, sitemaps, and /llms.txt.

    Hidden pages:
      - Are excluded from /sitemap.xml.
      - Return 404 for /<page>/llms.txt.
      - Are not registered as MCP resources.
      - Get a 404 when a crawler hits them via the bot middleware.
      - Are never prerendered into the initial HTML.
    """
    _state.hidden_pages.add(_normalize_path(page_path))


def is_hidden(page_path: str) -> bool:
    """Return True if the page has been hidden via mark_hidden()."""
    return _normalize_path(page_path) in _state.hidden_pages


# ---------------------------------------------------------------------------
# Public API: cross-host discovery
# ---------------------------------------------------------------------------


def describe_network(
    name: Optional[str] = None,
    description: Optional[str] = None,
    hub_url: Optional[str] = None,
    wordmark: Optional[Any] = None,
) -> None:
    """
    Name the network this app belongs to.

    Args:
        name: e.g. "The Example Network".
        description: One paragraph an agent can use to understand what the
            network is, before it starts following links.
        hub_url: The canonical host that indexes every member. Give agents
            one place to land and enumerate from; without it, discovery
            depends on whichever member host they happened to reach first.

            In a tiered network this points one level up, not all the way to
            the root: a subdomain names its section hub, and that hub names
            the network root. Each llms.txt then has exactly one "up" link and
            an agent walks the chain.
        wordmark: Optional mark for the llms.txt viewer banner. Either
            ``{"morse": "docs", "prefix": "", "suffix": ".dev"}`` to draw
            the word as morse code, or a list of ASCII-art lines. A bulletin
            payload overrides this, so a hub can restyle every satellite
            without redeploying them.
    """
    network = _state.network
    if name is not None:
        network.name = name
    if description is not None:
        network.description = description
    if hub_url is not None:
        network.hub_url = hub_url
    if wordmark is not None:
        network.wordmark = wordmark


def register_network_site(
    name: str,
    url: str,
    description: str = "",
    llms_txt: Optional[str] = None,
    tier: str = "peer",
) -> None:
    """
    Add one site to the cross-host directory.

    Args:
        name: Display name.
        url: Site root, e.g. "https://maps.example.com".
        description: What the site is — one sentence, written for a reader
            deciding whether to follow the link.
        llms_txt: Override the machine-readable URL. Defaults to
            ``{url}/llms.txt``.
        tier: One of:
            "peer"       — same network, same operator.
            "affiliated" — yours, on its own unrelated domain.
            "external"   — third-party docs you reference but don't own.
                           These are emitted with rel="nofollow".
    """
    _state.network.add(
        NetworkSite(
            name=name,
            url=url,
            description=description,
            llms_txt=llms_txt,
            tier=tier,
        )
    )


def register_network(
    name: Optional[str] = None,
    description: Optional[str] = None,
    hub_url: Optional[str] = None,
    wordmark: Optional[Any] = None,
    peers: Optional[List[Dict[str, Any]]] = None,
    affiliated: Optional[List[Dict[str, Any]]] = None,
    external: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Declare the whole cross-host directory in one call.

    Each list holds dicts of ``{"name", "url", "description", "llms_txt"}``;
    only ``name`` and ``url`` are required.

        register_network(
            name="The Example Network",
            hub_url="https://hub.example.com",
            peers=[
                {"name": "Hub", "url": "https://hub.example.com",
                 "description": "Network index and account origin."},
                {"name": "Maps", "url": "https://maps.example.com",
                 "description": "Mapping components."},
            ],
            affiliated=[
                {"name": "Side Project", "url": "https://sideproject.example"},
            ],
            external=[
                {"name": "Upstream component library",
                 "url": "https://components.example.org"},
            ],
        )
    """
    describe_network(name=name, description=description, hub_url=hub_url, wordmark=wordmark)

    for tier, entries in (
        ("peer", peers),
        ("affiliated", affiliated),
        ("external", external),
    ):
        for entry in entries or []:
            register_network_site(tier=tier, **entry)


# ---------------------------------------------------------------------------
# Backend detection + dispatch
# ---------------------------------------------------------------------------


def _detect_backend(app: Any) -> str:
    """Identify which backend is powering this Dash app's server."""
    try:
        from dash.backends import get_server_type  # type: ignore

        return get_server_type(app.server)
    except Exception:
        pass

    cls_name = type(app.server).__name__
    return {"Flask": "flask", "FastAPI": "fastapi", "Quart": "quart"}.get(cls_name, "flask")


def add_llms_routes(app: Any, config: Optional[LLMSConfig] = None) -> None:
    """
    Attach the crawler/SEO routes and bot middleware to a Dash app.

    Detects the Dash backend (Flask / FastAPI / Quart) and dispatches to
    the matching adapter. Public API is unchanged from 1.x: callers do
    not need to know which backend they're on.

    Args:
        app: Dash app instance.
        config: Optional LLMSConfig. Defaults are sensible for most apps.
    """
    if config is None:
        config = LLMSConfig()

    if not config.enabled:
        return

    app._llms_config = config

    if config.warn_missing_llms_doc:
        _warn_missing_llms_docs()

    if config.llms_tiers:
        _seed_tier_metadata()

    # Identity for the crawler document. This package serves crawlers a
    # GENERATED head instead of the app's own, so an app that declared its
    # favicon perfectly well still had it dropped on the way out. Adopt what
    # the app already ships unless it declared icons explicitly.
    autoconfigure_icons(app)

    # W5: the 402 lane's master switch — access.resolve honours a "priced"
    # verdict only when the app opted in; the default keeps it degrading
    # to gated exactly as every release before it.
    from . import access as _access

    _access.set_metering(getattr(config, "metering", False))

    backend = _detect_backend(app)

    from ._compat import warn_on_known_issues

    warn_on_known_issues(backend)

    if backend == "flask":
        from ._flask_adapter import register_flask

        register_flask(app, config, _state)
    elif backend == "fastapi":
        from ._fastapi_adapter import register_fastapi

        register_fastapi(app, config, _state)
    elif backend == "quart":
        from ._quart_adapter import register_quart

        register_quart(app, config, _state)
    else:
        raise RuntimeError(
            f"Unsupported Dash backend for add_llms_routes: {backend!r}. "
            "Supported: flask, fastapi, quart."
        )

    if config.register_mcp_resources:
        try:
            from ._mcp_bridge import register_mcp_resources as _register_mcp

            _register_mcp(app, _state)
        except Exception as exc:
            logger.debug("MCP bridge registration skipped: %s", exc)


def _seed_tier_metadata() -> None:
    """Give the tier documents a registered identity before any gate needs one.

    A ``gated`` verdict on a tier path renders a gate document assembled from
    ``page_metadata``; without this seed that document's H1 would be the bare
    path ("# /llms-full.txt"). ``setdefault`` at both levels, so anything the
    application registered for a tier path — including its own ``llms_doc``
    for /llms-small.txt — wins over the defaults.
    """
    from .handlers import TIER_DOC_META, TIER_DOC_PATHS

    for tier, tier_path in TIER_DOC_PATHS.items():
        entry = _state.page_metadata.setdefault(tier_path, {})
        for key, value in TIER_DOC_META[tier].items():
            entry.setdefault(key, value)

    try:
        import dash
    except ImportError:
        return

    tier_paths = set(TIER_DOC_PATHS.values())
    registry = getattr(dash, "page_registry", None) or {}
    for page in registry.values():
        path = _normalize_path(page.get("path") or "/")
        if path in tier_paths:
            warnings.warn(
                f"dash-improve-my-llms: a Dash page is registered at {path}, "
                f"which is also a tier-document route. The document route "
                f"wins and the page will not be reachable. Move the page, or "
                f"pass LLMSConfig(llms_tiers=False).",
                UserWarning,
                stacklevel=3,
            )


# ---------------------------------------------------------------------------
# Diagnostics: warn loudly when pages have no LLMS_DOC
# ---------------------------------------------------------------------------


def _warn_missing_llms_docs() -> None:
    """Emit a single combined warning naming every page without prose."""
    from .handlers import list_pages_missing_llms_doc

    missing = list_pages_missing_llms_doc(_state.page_metadata, _state.hidden_pages)
    if not missing:
        return

    plural = "s" if len(missing) > 1 else ""
    paths_str = ", ".join(missing)
    warnings.warn(
        f"dash-improve-my-llms: {len(missing)} page{plural} have no "
        f"LLMS_DOC source ({paths_str}). /llms.txt will return a "
        f'placeholder stub for these. Add `LLMS_DOC = """..."""` '
        f"at module scope, or pass llms_doc=... to register_page_metadata(). "
        f"To silence this warning, pass LLMSConfig(warn_missing_llms_doc=False).",
        UserWarning,
        stacklevel=3,
    )


# ---------------------------------------------------------------------------
# Deprecation shims for 1.x APIs that no longer have a job
# ---------------------------------------------------------------------------


def mark_important(component: Any, component_id: Optional[str] = None) -> Any:
    """
    Deprecated in 2.0. Returns the component unchanged.

    Reason: 2.0 dropped layout-walking extraction. Section emphasis now
    belongs inside your LLMS_DOC markdown (use headings, emphasis, etc.).
    """
    warnings.warn(
        "mark_important() is a no-op in dash-improve-my-llms 2.0 and will "
        "be removed in 2.1. The package no longer walks layouts to extract "
        "content — put emphasis directly in your LLMS_DOC string.",
        DeprecationWarning,
        stacklevel=2,
    )
    return component


def mark_component_hidden(component: Any, component_id: Optional[str] = None) -> Any:
    """Deprecated in 2.0. Returns the component unchanged."""
    warnings.warn(
        "mark_component_hidden() is a no-op in dash-improve-my-llms 2.0. "
        "Component-tree extraction was removed; there is no extraction to "
        "hide from. Use mark_hidden(path) to hide whole pages.",
        DeprecationWarning,
        stacklevel=2,
    )
    return component


def setup_llms_plugin(app: Any, **kwargs: Any) -> None:
    """Deprecated alias for add_llms_routes()."""
    warnings.warn(
        "setup_llms_plugin() is deprecated; use add_llms_routes() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    add_llms_routes(app, LLMSConfig(enabled=kwargs.get("enabled", True)))


__all__: List[str] = [
    "__version__",
    "add_llms_routes",
    "LLMSConfig",
    "RobotsConfig",
    "register_page_metadata",
    "mark_hidden",
    "is_hidden",
    # Cross-host discovery
    "register_network",
    "register_network_site",
    "describe_network",
    "configure_bulletin",
    "NetworkSite",
    # Per-request access control and viewer identity (see docs/ACCESS.md)
    "configure_access",
    "configure_viewer_identity",
    # Country guardrail — opt-in 451 on every surface (see docs/GEO.md)
    "configure_geo",
    # The read ledger — one event per document served (2.8)
    "on_document_read",
    # One classification fold: who is asking, and on which lane (2.8).
    # THE entry point for classifying a request — an application should
    # call this rather than keep User-agent lists of its own.
    "classify",
    # Opt-in refresh of the shipped crawler IP-range snapshots (2.8)
    "configure_identity",
    # Site-level search identity for the crawler document (see docs/SEO.md)
    "autoconfigure_icons",
    "configure_seo",
    "discover_icons",
    # Deprecated shims (kept for one release to not break 1.x users)
    "mark_important",
    "mark_component_hidden",
    "setup_llms_plugin",
]
