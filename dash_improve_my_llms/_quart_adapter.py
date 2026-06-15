"""
Quart adapter for dash-improve-my-llms 2.0.

Quart's API mirrors Flask's but is async. Same handler delegation
as the other adapters.
"""

from __future__ import annotations

from typing import Any

from .handlers import (
    build_llms_txt_for_page,
    build_robots_txt,
    build_sitemap_xml,
    handle_bot_request,
)


def register_quart(app: Any, config: Any, state: Any) -> None:
    """
    Wire the 4 routes and the bot middleware into a Quart-backed Dash app.

    Args:
        app: The Dash app (app.server is a quart.Quart instance).
        config: LLMSConfig.
        state: Shared module-level state (page_metadata, hidden_pages).
    """
    try:
        from quart import Response, request
    except ImportError as exc:
        raise RuntimeError(
            "Quart backend detected but `quart` is not installed. "
            "Install with: pip install dash-improve-my-llms[quart]"
        ) from exc

    server = app.server

    @server.before_request
    async def _bot_middleware():
        result = handle_bot_request(
            path=request.path,
            user_agent=request.headers.get("User-Agent", ""),
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        if result is None:
            return None
        return Response(
            result["body"],
            status=result["status"],
            mimetype=result["content_type"],
            headers=result.get("headers", {}),
        )

    @server.route("/<path:page_path>/llms.txt")
    @server.route("/llms.txt", defaults={"page_path": ""})
    async def _llms_txt(page_path: str):
        body, status = build_llms_txt_for_page(
            app=app,
            page_path=page_path,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        return Response(body, status=status, mimetype="text/plain")

    @server.route("/robots.txt")
    async def _robots():
        return Response(build_robots_txt(app), mimetype="text/plain")

    @server.route("/sitemap.xml")
    async def _sitemap():
        body = build_sitemap_xml(
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        return Response(body, mimetype="application/xml")
