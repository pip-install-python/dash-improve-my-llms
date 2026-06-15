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

__version__ = "2.0.0"

import logging
import warnings
from typing import Any, Dict, List, Optional

from .robots_generator import RobotsConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared state — replaces module globals scattered through 1.x
# ---------------------------------------------------------------------------


class _State:
    """Container for module-level registries. One instance per process."""

    def __init__(self) -> None:
        self.page_metadata: Dict[str, Dict[str, Any]] = {}
        self.hidden_pages: set = set()


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
    ) -> None:
        self.enabled = enabled
        self.warn_missing_llms_doc = warn_missing_llms_doc
        self.register_mcp_resources = register_mcp_resources


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

    Args:
        path: Page path (must match the path you passed to dash.register_page).
        name: Display name. Falls back to the dash.register_page name.
        description: One-sentence summary used in meta tags and sitemap.
        llms_doc: Optional prose body for /llms.txt. If omitted, the package
            looks for a module-level LLMS_DOC attribute on the page module.
        **kwargs: Additional SEO fields (og_image, schema_type, etc.) — passed
            through to html_generator for crawler-facing HTML.
    """
    entry = {"name": name, "description": description}
    if llms_doc is not None:
        entry["llms_doc"] = llms_doc
    entry.update(kwargs)
    _state.page_metadata[path] = entry


def mark_hidden(page_path: str) -> None:
    """
    Hide a page from crawlers, sitemaps, and /llms.txt.

    Hidden pages:
      - Are excluded from /sitemap.xml.
      - Return 404 for /<page>/llms.txt.
      - Are not registered as MCP resources.
      - Get a 404 when a crawler hits them via the bot middleware.
    """
    _state.hidden_pages.add(page_path)


def is_hidden(page_path: str) -> bool:
    """Return True if the page has been hidden via mark_hidden()."""
    return page_path in _state.hidden_pages


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
    return {"Flask": "flask", "FastAPI": "fastapi", "Quart": "quart"}.get(
        cls_name, "flask"
    )


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

    backend = _detect_backend(app)
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
        f"placeholder stub for these. Add `LLMS_DOC = \"\"\"...\"\"\"` "
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
    # Deprecated shims (kept for one release to not break 1.x users)
    "mark_important",
    "mark_component_hidden",
    "setup_llms_plugin",
]
