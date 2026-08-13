"""
Flask adapter for dash-improve-my-llms 2.0.

Translates between Flask's request/response cycle and the pure handlers
in handlers.py. All Flask-specific code lives here.
"""

from __future__ import annotations

from typing import Any, Dict

from . import access
from .handlers import (
    TIER_DOC_META,
    TIER_DOC_PATHS,
    apply_prerender,
    build_llms_full_summary,
    build_llms_tier_doc,
    build_llms_txt_for_page,
    build_llms_viewer_html,
    build_robots_txt,
    build_sitemap_xml,
    handle_bot_request,
    should_prerender,
    wants_html_viewer,
)


def _doc_headers() -> Dict[str, str]:
    """Headers for an llms.txt response.

    ``Vary: Accept`` always, because the same URL serves Markdown or HTML by
    negotiation and a CDN must not hand a cached browser page to the next
    agent. When the response is per-requester — it names the reader, or its
    links carry authority — nothing shared may cache it at all.
    """
    if access.is_restricted():
        return access.private_headers()
    return {"Vary": "Accept"}


def register_flask(app: Any, config: Any, state: Any) -> None:
    """
    Wire the 4 routes and the bot middleware into a Flask-backed Dash app.

    Args:
        app: The Dash app (app.server is a flask.Flask instance).
        config: LLMSConfig.
        state: Shared module-level state (page_metadata, hidden_pages).
    """
    from flask import Response, request

    server = app.server

    @server.before_request
    def _bot_middleware():  # type: ignore[unused-ignore]
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
        def _prerender(response):  # type: ignore[unused-ignore]
            if not should_prerender(
                path=request.path,
                status=response.status_code,
                content_type=response.content_type or "",
            ):
                return response
            # Streamed/passthrough responses have no materialised body.
            if response.direct_passthrough or not response.is_sequence:
                return response

            document = response.get_data(as_text=True)
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
    def _llms_txt(page_path: str):
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
                query=request.args.to_dict(),
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

    if getattr(config, "llms_tiers", True):

        @server.route(TIER_DOC_PATHS["small"], defaults={"tier": "small"})
        @server.route(TIER_DOC_PATHS["full"], defaults={"tier": "full"})
        def _llms_tier(tier: str):
            body, status = build_llms_tier_doc(
                app=app,
                tier=tier,
                page_metadata=state.page_metadata,
                hidden_paths=state.hidden_pages,
                state=state,
                full_max_bytes=getattr(config, "llms_full_max_bytes", 4_000_000),
            )
            tier_path = TIER_DOC_PATHS[tier]

            headers = _doc_headers()
            if tier == "full":
                # The corpus duplicates every page's content; indexed, it
                # would compete with the real pages in search results.
                headers["X-Robots-Tag"] = "noindex"

            if status == 200 and getattr(config, "llms_viewer", True):
                if wants_html_viewer(
                    accept=request.headers.get("Accept", ""),
                    user_agent=request.headers.get("User-Agent", ""),
                    query=request.args.to_dict(),
                ):
                    markdown_body = body
                    if tier == "full":
                        # Never render the multi-megabyte corpus to HTML — a
                        # browser gets a card describing it. The same URL with
                        # ?raw=1, or any agent UA, gets the corpus itself.
                        markdown_body = build_llms_full_summary(app, body)
                    html = build_llms_viewer_html(
                        app=app,
                        page_path=tier_path,
                        markdown_body=markdown_body,
                        page_metadata=state.page_metadata,
                        state=state,
                        raw_url=tier_path,
                        page_name=(state.page_metadata.get(tier_path) or {}).get("name")
                        or TIER_DOC_META[tier]["name"],
                    )
                    if html is not None:
                        return Response(
                            html,
                            status=status,
                            mimetype="text/html",
                            headers=headers,
                        )

            return Response(
                body,
                status=status,
                mimetype="text/markdown",
                headers=headers,
            )

    @server.route("/robots.txt")
    def _robots():
        return Response(build_robots_txt(app), mimetype="text/plain")

    @server.route("/sitemap.xml")
    def _sitemap():
        body = build_sitemap_xml(
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        return Response(body, mimetype="application/xml")
