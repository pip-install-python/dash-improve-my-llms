"""
Pure, framework-agnostic handlers.

These functions know nothing about Flask, FastAPI, or Quart. They take
plain Python inputs (path strings, user-agent strings, the Dash `app`
object) and return either plain strings, dicts, or None.

Each backend adapter wraps these in its own Response type at the I/O
boundary.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

from .bot_detection import get_bot_type, is_any_bot
from .robots_generator import RobotsConfig, generate_robots_txt
from .sitemap_generator import generate_sitemap_xml


# ---------------------------------------------------------------------------
# Page resolution
# ---------------------------------------------------------------------------


def _normalize_page_path(page_path: str) -> str:
    """Normalize a path captured from a URL to the form dash.page_registry uses."""
    if not page_path:
        return "/"
    if not page_path.startswith("/"):
        return "/" + page_path
    return page_path


def _find_page(page_path: str) -> Optional[Dict[str, Any]]:
    """Look up a page in dash.page_registry by path. Returns the dict or None."""
    try:
        import dash
    except ImportError:
        return None

    registry = getattr(dash, "page_registry", None) or {}
    for entry in registry.values():
        if entry.get("path") == page_path or entry.get("relative_path") == page_path:
            return entry
    return None


def _resolve_llms_doc(
    page_path: str,
    page_metadata: Dict[str, Dict[str, Any]],
    page_entry: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    Resolve the prose body for a page in 2.0.

    Order of precedence:
      1. register_page_metadata(path, llms_doc="...") stored in page_metadata.
      2. Module-level LLMS_DOC attribute on the page module.
      3. None (caller emits the stub fallback).
    """
    meta = page_metadata.get(page_path) or {}
    doc = meta.get("llms_doc")
    if doc:
        return doc

    if page_entry is not None:
        module_name = page_entry.get("module")
        if module_name and module_name in sys.modules:
            module_doc = getattr(sys.modules[module_name], "LLMS_DOC", None)
            if module_doc:
                return module_doc

    return None


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
        path = entry.get("path", "/")
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
        f"To populate this document, either set `LLMS_DOC = \"\"\"...\"\"\"` "
        f"at module scope in the page file, or call "
        f"`register_page_metadata(\"{page_path}\", llms_doc=\"...\")`.\n"
    )


def build_llms_txt_for_page(
    app: Any,
    page_path: str,
    page_metadata: Dict[str, Dict[str, Any]],
    hidden_paths: set,
) -> Optional[Tuple[str, int]]:
    """
    Build the body of /llms.txt for one page.

    Returns (body, status) — status 200 on success, 404 if the path is
    hidden or unknown. Returns None ONLY if dash itself isn't importable
    (signal to the adapter to 500).
    """
    page_path = _normalize_page_path(page_path)

    if page_path in hidden_paths:
        return ("Page not available", 404)

    page_entry = _find_page(page_path)
    if page_entry is None:
        return (f"llms.txt not available for {page_path}", 404)

    doc = _resolve_llms_doc(page_path, page_metadata, page_entry)
    if doc:
        return (doc, 200)

    meta = page_metadata.get(page_path) or {}
    page_name = meta.get("name") or page_entry.get("name") or page_path
    description = meta.get("description") or ""
    return (_stub_llms_txt(page_name, page_path, description), 200)


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
        path = entry.get("path", "/")
        if path in hidden_paths:
            continue
        meta = page_metadata.get(path) or {}
        pages.append(
            {
                "path": path,
                "name": meta.get("name") or entry.get("name", "Page"),
                "description": meta.get("description", ""),
                "hidden": False,
            }
        )

    base_url = getattr(app, "_base_url", "https://example.com")
    return generate_sitemap_xml(
        pages=pages, base_url=base_url, hidden_paths=list(hidden_paths)
    )


# ---------------------------------------------------------------------------
# Bot middleware decision
# ---------------------------------------------------------------------------


_DOC_ROUTE_SUFFIXES: Tuple[str, ...] = ("/llms.txt", "/robots.txt", "/sitemap.xml")
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
    if _is_asset_path(path) or _is_documentation_route(path):
        return None

    if not is_any_bot(user_agent):
        return None

    bot_type = get_bot_type(user_agent)
    robots_config: Optional[RobotsConfig] = getattr(app, "_robots_config", None)

    if bot_type == "training" and robots_config and robots_config.block_ai_training:
        body = (
            "403 Forbidden - AI training bots are not allowed to access this content.\n"
            "This site blocks AI training bots to prevent unauthorized use of content "
            "for model training.\n"
            f"Bot detected: {user_agent[:100]}\n"
            "For more information, see /robots.txt"
        )
        return {
            "status": 403,
            "body": body,
            "content_type": "text/plain",
            "headers": {},
        }

    if bot_type in ("search", "traditional"):
        page_path = path if path != "" else "/"

        if page_path in hidden_paths:
            return {
                "status": 404,
                "body": "404 Not Found - Page not available",
                "content_type": "text/plain",
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

    try:
        import dash
    except ImportError:
        return None

    registry = getattr(dash, "page_registry", None) or {}

    page_entry = None
    for entry in registry.values():
        if entry.get("path") == page_path:
            page_entry = entry
            break

    if page_entry is None:
        return None

    meta = page_metadata.get(page_path) or {}
    page_name = meta.get("name") or page_entry.get("name") or page_path
    description = meta.get("description") or f"View {page_name}"

    all_pages = []
    for entry in registry.values():
        p_path = entry.get("path", "/")
        if p_path in hidden_paths:
            continue
        all_pages.append(
            {
                "path": p_path,
                "name": (page_metadata.get(p_path) or {}).get("name")
                or entry.get("name", "Page"),
            }
        )

    app_config = {
        "name": getattr(app, "title", "Dash Application"),
        "base_url": getattr(app, "_base_url", "https://example.com"),
    }

    prose = _resolve_llms_doc(page_path, page_metadata, page_entry)

    try:
        return generate_static_page_html(
            page_path=page_path,
            page_metadata={
                "name": page_name,
                "description": description,
                "path": page_path,
                "llms_doc": prose,
            },
            all_pages=all_pages,
            app_config=app_config,
        )
    except Exception:
        return None
