"""
FastAPI adapter for dash-improve-my-llms 2.0.

Translates between FastAPI/Starlette's request/response cycle and the
pure handlers in handlers.py. Only this file knows about FastAPI types.
"""

from typing import Any

# NOTE: deliberately NO `from __future__ import annotations` in this module.
#
# FastAPI reads route-handler annotations to decide what to inject. That
# import turns every annotation into a string, which FastAPI then resolves
# against *module* globals — and `Request` is imported inside
# register_fastapi(), so it isn't there. The result is not an error at
# startup: FastAPI silently treats `request: Request` as an undeclared query
# parameter and every /llms.txt request 422s. Keep annotations eager so they
# resolve in the enclosing scope where the import actually lives.

from . import access
from ._headers import normalize_headers
from .discovery import DIGEST_HEADER, link_header_value, wants_plain_text
from .handlers import (
    DOC_ROUTE_METHODS,
    page_source_digest,
    LLMS_FULL_VIEWER_NOTE,
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
from .seo import ROOT_ICON_PATHS, root_icon_target


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


def register_fastapi(app: Any, config: Any, state: Any) -> None:
    """
    Wire the 4 routes and the bot middleware into a FastAPI-backed Dash app.

    Args:
        app: The Dash app (app.server is a fastapi.FastAPI instance).
        config: LLMSConfig.
        state: Shared module-level state (page_metadata, hidden_pages).
    """
    try:
        from fastapi import APIRouter, Request, Response
        from fastapi.responses import PlainTextResponse, RedirectResponse
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI backend detected but `fastapi` is not installed. "
            "Install with: pip install dash-improve-my-llms[fastapi]"
        ) from exc

    server = app.server

    prerender_enabled = getattr(config, "prerender", True)

    @server.middleware("http")
    async def _bot_middleware(request: Request, call_next):
        result = handle_bot_request(
            path=request.url.path,
            user_agent=request.headers.get("user-agent", ""),
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
            headers=normalize_headers(request.headers),
        )
        if result is not None:
            return Response(
                content=result["body"],
                status_code=result["status"],
                media_type=result["content_type"],
                headers=result.get("headers", {}),
            )

        response = await call_next(request)

        is_panel = getattr(config, "panel", False) and request.url.path == getattr(
            config, "panel_path", "/llms-policy"
        )
        if (
            is_panel
            or not prerender_enabled
            or not should_prerender(
                path=request.url.path,
                status=response.status_code,
                content_type=response.headers.get("content-type", ""),
            )
        ):
            return response

        # call_next hands back a streaming response, so the body has to be
        # drained before it can be rewritten.
        chunks = [chunk async for chunk in response.body_iterator]
        body = b"".join(chunks)

        try:
            document = body.decode("utf-8")
        except UnicodeDecodeError:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        injected = apply_prerender(
            document=document,
            app=app,
            path=request.url.path,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
            state=state,
        )
        encoded = injected.encode("utf-8")

        headers = dict(response.headers)
        # The body just changed length; a stale Content-Length truncates it.
        headers.pop("content-length", None)
        if injected is not document:
            # llms.txt v2 discovery (2.7.1): the relations ride the headers
            # of the page response too.
            headers["Link"] = link_header_value(request.url.path.rstrip("/") or "/")

        return Response(
            content=encoded,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )

    router = APIRouter()

    def _serve_llms(page_path: str, request: Request) -> Response:
        """Shared body for both llms.txt routes — negotiated by Accept."""
        body, status = build_llms_txt_for_page(
            app=app,
            page_path=page_path,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
            state=state,
            include_nav=getattr(config, "llms_nav", True),
            user_agent=request.headers.get("user-agent", ""),
        )

        if status == 200 and getattr(config, "llms_viewer", True):
            if wants_html_viewer(
                accept=request.headers.get("accept", ""),
                user_agent=request.headers.get("user-agent", ""),
                query=dict(request.query_params),
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
                        content=html,
                        status_code=status,
                        media_type="text/html",
                        headers=_doc_headers(),
                    )

        headers = _doc_headers()
        # 2.7.1: the parity digest and the text/plain compatibility ramp.
        digest = page_source_digest(
            f"/{page_path}" if page_path else "/",
            state.page_metadata,
            state.hidden_pages,
            state,
        )
        if digest and status == 200:
            headers[DIGEST_HEADER] = digest
        media_type = (
            "text/plain" if wants_plain_text(request.headers.get("accept", "")) else "text/markdown"
        )
        if status == 402:
            # W5: private/no-store + the app's payment challenge. Header
            # failures inside offer_headers degrade to a header-bare 402,
            # never a different verdict.
            headers.update(
                access.offer_headers("/llms.txt" if not page_path else f"/{page_path}/llms.txt")
            )
        return Response(
            content=body,
            status_code=status,
            media_type=media_type,
            headers=headers,
        )

    @router.api_route("/llms.txt", methods=DOC_ROUTE_METHODS)
    def _llms_txt_root(request: Request):
        return _serve_llms("", request)

    if getattr(config, "llms_tiers", True):

        def _serve_tier(tier: str, request: Request) -> Response:
            """Shared body for both tier routes — mirrors _serve_llms."""
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
            if status == 402:
                headers.update(access.offer_headers(tier_path))
            if tier == "full":
                # The corpus duplicates every page's content; indexed, it
                # would compete with the real pages in search results.
                headers["X-Robots-Tag"] = "noindex"

            if status == 200 and getattr(config, "llms_viewer", True):
                if wants_html_viewer(
                    accept=request.headers.get("accept", ""),
                    user_agent=request.headers.get("user-agent", ""),
                    query=dict(request.query_params),
                ):
                    markdown_body = body
                    source_note = ""
                    if tier == "full":
                        # Never render the multi-megabyte corpus to HTML — a
                        # browser gets a card describing it. The same URL with
                        # ?raw=1, or any agent UA, gets the corpus itself.
                        # The chrome has to say so, or it describes the card
                        # as the thing agents receive.
                        markdown_body = build_llms_full_summary(app, body)
                        source_note = LLMS_FULL_VIEWER_NOTE
                    html = build_llms_viewer_html(
                        app=app,
                        page_path=tier_path,
                        markdown_body=markdown_body,
                        page_metadata=state.page_metadata,
                        state=state,
                        raw_url=tier_path,
                        source_note=source_note,
                        page_name=(state.page_metadata.get(tier_path) or {}).get("name")
                        or TIER_DOC_META[tier]["name"],
                    )
                    if html is not None:
                        return Response(
                            content=html,
                            status_code=status,
                            media_type="text/html",
                            headers=headers,
                        )

            return Response(
                content=body,
                status_code=status,
                media_type=(
                    "text/plain"
                    if wants_plain_text(request.headers.get("accept", ""))
                    else "text/markdown"
                ),
                headers=headers,
            )

        @router.api_route(TIER_DOC_PATHS["small"], methods=DOC_ROUTE_METHODS)
        def _llms_small(request: Request):
            return _serve_tier("small", request)

        @router.api_route(TIER_DOC_PATHS["full"], methods=DOC_ROUTE_METHODS)
        def _llms_full(request: Request):
            return _serve_tier("full", request)

    @router.api_route("/{page_path:path}/llms.txt", methods=DOC_ROUTE_METHODS)
    def _llms_txt(page_path: str, request: Request):
        return _serve_llms(page_path, request)

    @router.api_route("/robots.txt", methods=DOC_ROUTE_METHODS, response_class=PlainTextResponse)
    def _robots():
        return PlainTextResponse(build_robots_txt(app))

    if getattr(config, "panel", False):
        # P1: the read-only operator panel — see the Flask adapter's note.
        @router.api_route(getattr(config, "panel_path", "/llms-policy"), methods=DOC_ROUTE_METHODS)
        def _llms_panel(request: Request):
            from . import panel as _panel

            req_headers = normalize_headers(request.headers)
            token = request.query_params.get("token", "")
            if not _panel.authorized(config, req_headers, token):
                return PlainTextResponse("404 Not Found", status_code=404)
            return Response(
                content=_panel.build_panel_html(
                    app=app, config=config, state=state, request_headers=req_headers
                ),
                media_type="text/html",
                headers=_panel.panel_response_headers(),
            )

    @router.api_route("/sitemap.xml", methods=DOC_ROUTE_METHODS)
    def _sitemap():
        body = build_sitemap_xml(
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        return Response(content=body, media_type="application/xml")

    # Well-known root icons — see the note in _flask_adapter. Dash's page
    # catch-all answers these with the app shell, so a search engine falling
    # back to /favicon.ico receives markup where an image should be. A route
    # the application registered for one of these paths before improve()
    # keeps precedence; the package only claims paths nobody else has.
    _claimed = {getattr(route, "path", None) for route in server.routes}

    def _make_root_icon(icon_path):
        def _root_icon():
            target = root_icon_target(icon_path)
            if not target:
                return Response(status_code=404)
            return RedirectResponse(target, status_code=302)

        return _root_icon

    for _root_path in ROOT_ICON_PATHS:
        if _root_path in _claimed:
            continue
        router.add_api_route(
            _root_path,
            _make_root_icon(_root_path),
            methods=DOC_ROUTE_METHODS,
            include_in_schema=False,
        )

    # IMPORTANT: register router last so /{page_path:path}/llms.txt doesn't
    # shadow user-registered routes like /api/something.
    server.include_router(router)
