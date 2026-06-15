"""
MCP bridge for dash-improve-my-llms 2.0.

Registers each page's LLMS_DOC as a `dash.mcp` resource so MCP-aware
clients can fetch narrative documentation through their existing
JSON-RPC tool calls instead of round-tripping through /llms.txt over
HTTP.

NOTE: As of this writing, Dash 4.3 (which ships `dash.mcp`) is in RC.
The exact registration API may differ from what's coded here; this
module tries the most likely call shapes and no-ops cleanly if none
match. Revisit once Dash 4.3 GA lands.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .handlers import _resolve_llms_doc

logger = logging.getLogger(__name__)


def register_mcp_resources(app: Any, state: Any) -> bool:
    """
    Try to register each page's LLMS_DOC as a Dash MCP resource.

    Returns:
        True if at least one resource was registered, False otherwise
        (including when dash.mcp isn't available — that's the normal
        case on Dash < 4.3).
    """
    mcp_api = _import_dash_mcp()
    if mcp_api is None:
        logger.debug("dash.mcp not available; skipping MCP resource registration")
        return False

    try:
        import dash
    except ImportError:
        return False

    if not _is_mcp_enabled(app, mcp_api):
        logger.debug("MCP is not enabled on this Dash app; skipping registration")
        return False

    registry = getattr(dash, "page_registry", None) or {}
    registered_any = False

    for entry in registry.values():
        path = entry.get("path", "/")
        if path in state.hidden_pages:
            continue

        prose = _resolve_llms_doc(path, state.page_metadata, entry)
        if not prose:
            continue

        page_name = (
            (state.page_metadata.get(path) or {}).get("name")
            or entry.get("name")
            or path
        )
        description = (
            (state.page_metadata.get(path) or {}).get("description")
            or f"LLM documentation for {page_name}"
        )

        ok = _try_register(
            mcp_api=mcp_api,
            app=app,
            uri=f"llms://{path.lstrip('/') or 'index'}",
            name=f"llms.txt for {page_name}",
            description=description,
            content=prose,
            mime_type="text/markdown",
        )
        if ok:
            registered_any = True

    return registered_any


# ---------------------------------------------------------------------------
# dash.mcp discovery and call shape probing
# ---------------------------------------------------------------------------


def _import_dash_mcp() -> Any:
    """Return the dash.mcp module if importable, else None."""
    try:
        from dash import mcp as dash_mcp  # type: ignore
    except ImportError:
        try:
            import dash_mcp  # type: ignore
        except ImportError:
            return None
    return dash_mcp


def _is_mcp_enabled(app: Any, mcp_api: Any) -> bool:
    """Best-effort check that MCP is actually turned on for this app."""
    for fn_name in ("is_enabled", "mcp_enabled", "is_mcp_enabled"):
        fn = getattr(mcp_api, fn_name, None)
        if callable(fn):
            try:
                return bool(fn(app))
            except TypeError:
                try:
                    return bool(fn())
                except Exception:
                    continue
            except Exception:
                continue
    # If we can't tell, assume yes — registration calls will fail safely.
    return True


def _try_register(
    *,
    mcp_api: Any,
    app: Any,
    uri: str,
    name: str,
    description: str,
    content: str,
    mime_type: str,
) -> bool:
    """
    Attempt to register a resource via whichever `dash.mcp` API shape exists.

    Tries, in order:
      1. mcp_api.register_resource(app, uri=..., name=..., description=...,
                                   handler=lambda: content, mime_type=...)
      2. mcp_api.register_resource(uri=..., name=..., description=...,
                                   content=content, mime_type=...)
      3. mcp_api.add_resource(...)
      4. app.mcp.register_resource(...)
    """
    handler = lambda: content  # noqa: E731

    candidates = []

    for fn_name in ("register_resource", "add_resource"):
        fn = getattr(mcp_api, fn_name, None)
        if callable(fn):
            candidates.append(("module", fn))

    app_mcp = getattr(app, "mcp", None)
    if app_mcp is not None:
        for fn_name in ("register_resource", "add_resource"):
            fn = getattr(app_mcp, fn_name, None)
            if callable(fn):
                candidates.append(("app", fn))

    if not candidates:
        logger.debug("No dash.mcp resource-registration function found")
        return False

    kwargs_variants = [
        # Modern shape: app-first, handler callable
        dict(uri=uri, name=name, description=description, handler=handler, mime_type=mime_type),
        # Content-as-string shape
        dict(uri=uri, name=name, description=description, content=content, mime_type=mime_type),
        # Minimal shape
        dict(uri=uri, name=name, content=content),
    ]

    for binding, fn in candidates:
        for kwargs in kwargs_variants:
            try:
                if binding == "module":
                    fn(app, **kwargs)
                else:
                    fn(**kwargs)
                return True
            except TypeError:
                continue
            except Exception as exc:
                logger.debug("MCP register call failed for %s: %s", uri, exc)
                continue

    logger.debug("Exhausted dash.mcp registration shapes for %s", uri)
    return False
