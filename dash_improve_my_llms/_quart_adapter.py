"""
Quart adapter for dash-improve-my-llms 2.0.

Quart's API mirrors Flask's but is async. Same handler delegation
as the other adapters.
"""

from __future__ import annotations

from typing import Any

from . import access
from .handlers import (
    apply_prerender,
    build_llms_txt_for_page,
    build_llms_viewer_html,
    build_robots_txt,
    build_sitemap_xml,
    handle_bot_request,
    should_prerender,
    wants_html_viewer,
)


def _doc_headers():
    """Headers for an llms.txt response.

    ``Vary: Accept`` always, because the same URL serves Markdown or HTML by
    negotiation and a CDN must not hand a cached browser page to the next
    agent. When the response is per-requester — it names the reader, or its
    links carry authority — nothing shared may cache it at all.
    """
    if access.is_restricted():
        return access.private_headers()
    return {"Vary": "Accept"}


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

    if getattr(config, "prerender", True):

        @server.after_request
        async def _prerender(response):
            if not should_prerender(
                path=request.path,
                status=response.status_code,
                content_type=response.content_type or "",
            ):
                return response

            document = await response.get_data(as_text=True)
            injected = apply_prerender(
                document=document,
                app=app,
                path=request.path,
                page_metadata=state.page_metadata,
                hidden_paths=state.hidden_pages,
                state=state,
            )
            if injected is not document:
                response.set_data(injected)
            return response

    @server.route("/<path:page_path>/llms.txt")
    @server.route("/llms.txt", defaults={"page_path": ""})
    async def _llms_txt(page_path: str):
        body, status = build_llms_txt_for_page(
            app=app,
            page_path=page_path,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
            state=state,
            include_nav=getattr(config, "llms_nav", True),
        )

        if status == 200 and getattr(config, "llms_viewer", True):
            if wants_html_viewer(
                accept=request.headers.get("Accept", ""),
                user_agent=request.headers.get("User-Agent", ""),
                query=dict(request.args),
            ):
                html = build_llms_viewer_html(
                    app=app,
                    page_path=page_path,
                    markdown_body=body,
                    page_metadata=state.page_metadata,
                    state=state,
                )
                if html is not None:
                    return Response(
                        html,
                        status=status,
                        mimetype="text/html",
                        headers=_doc_headers(),
                    )

        return Response(
            body,
            status=status,
            mimetype="text/markdown",
            headers=_doc_headers(),
        )

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
