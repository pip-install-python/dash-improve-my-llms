"""
FastAPI adapter for dash-improve-my-llms 2.0.

Translates between FastAPI/Starlette's request/response cycle and the
pure handlers in handlers.py. Only this file knows about FastAPI types.
"""

from typing import Any, Dict

# NOTE: deliberately NO `from __future__ import annotations` in this module.
#
# FastAPI reads route-handler annotations to decide what to inject. That
# import turns every annotation into a string, which FastAPI then resolves
# against *module* globals — and `Request` is imported inside
# register_fastapi(), so it isn't there. The result is not an error at
# startup: FastAPI silently treats `request: Request` as an undeclared query
# parameter and every /llms.txt request 422s. Keep annotations eager so they
# resolve in the enclosing scope where the import actually lives.

from . import _ledger, access, wellknown
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
    merge_vary,
    read_event_identity,
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

    ``Vary: User-Agent`` since 2.8, because it is simply true: the same URL
    answers a browser and a crawler with different bytes, and through
    2.7.x the package told no cache so. Nothing reported it only because
    the edge in front of these hosts happened to mark every document
    response DYNAMIC; a shared cache that did not would hand a crawler the
    document built for a browser, or the reverse.
    """
    if access.is_restricted():
        return access.private_headers()
    return {"Vary": "Accept, User-Agent"}


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

    class _MarkdownResponse(Response):
        """Only ever used as a `response_class` — for the SCHEMA's media type.

        Every doc endpoint returns an explicit `Response` it built itself,
        so this class never renders anything. It exists because FastAPI
        derives the declared media type from `response_class` and defaults
        to JSONResponse; without it the schema opens every markdown route
        with `application/json`. Declared here rather than at module level
        because `fastapi` is an extra and is imported inside this function
        on purpose.
        """

        media_type = "text/markdown"

    class _XmlResponse(Response):
        """Same, for /sitemap.xml."""

        media_type = "application/xml"

    class _HtmlSchemaResponse(Response):
        """Same, for the operator panel."""

        media_type = "text/html"

    server = app.server

    prerender_enabled = getattr(config, "prerender", True)

    @server.middleware("http")
    async def _bot_middleware(request: Request, call_next):
        if request.method == "HEAD":
            # Dash's page catch-all is registered from the ASGI lifespan
            # startup, i.e. after register_fastapi() ran — so the pass at
            # registration time cannot have seen it. Idempotent; see
            # _allow_head_wherever_get_is_allowed.
            _allow_head_wherever_get_is_allowed(server)

        result = handle_bot_request(
            path=request.url.path,
            user_agent=request.headers.get("user-agent", ""),
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
            headers=normalize_headers(request.headers),
            method=request.method,
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

        # 2.8: this page route answers a browser and a crawler with
        # different bytes — the middleware short-circuits machines to the
        # crawler document above — so the header has to say so whether or
        # not the prerender ends up injecting anything.
        response.headers["Vary"] = merge_vary(
            response.headers.get("Vary", ""), "Accept", "User-Agent"
        )

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

    def _emit(request, path: str, tier: str, status: int, body, verdict: str = "") -> None:
        """One read event for a document this adapter served.

        The package does no I/O with it — see _ledger. On a host with no
        listener registered this is a single truth-test.
        """
        if not _ledger.has_listeners():
            return
        user_agent = request.headers.get("user-agent", "")
        request_headers = normalize_headers(request.headers)
        _ledger.emit_read(
            path=path,
            method=request.method,
            tier=tier,
            status=status,
            body=body,
            verdict=verdict or _ledger.verdict_for_status(status),
            user_agent=user_agent,
            headers=request_headers,
            # 2.9.0: the posture this document went out under. Documents
            # served from these routes never enter handle_bot_request, so
            # before this every adapter event carried policy=None.
            **read_event_identity(app=app, user_agent=user_agent, headers=request_headers),
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
                    _emit(
                        request,
                        request.url.path,
                        "index" if not page_path else "page",
                        status,
                        html,
                    )
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
        _emit(request, request.url.path, "index" if not page_path else "page", status, body)
        return Response(
            content=body,
            status_code=status,
            media_type=media_type,
            headers=headers,
        )

    # ---------------------------------------------------------------
    # 2.9.3 — the schema says what the wire does
    # ---------------------------------------------------------------
    #
    # Measured on a live host 2026-08-31 and reproduced in-process: every
    # markdown route declared `application/json` with an empty schema,
    # because FastAPI infers the media type from `response_class` and the
    # default is JSONResponse. `/sitemap.xml` declared JSON too, while
    # serving application/xml. An agent generating a client from that
    # schema gets the wrong content contract for the one surface the whole
    # package exists to serve.
    #
    # The declaration is the FULL truth, not just the common case: the
    # llms.txt family answers text/markdown, and by Accept negotiation
    # text/html (the viewer) and text/plain. All three are reachable, so
    # all three are declared.
    MARKDOWN_MEDIA_TYPES = {
        "text/markdown": {"schema": {"type": "string"}},
        "text/html": {"schema": {"type": "string"}},
        "text/plain": {"schema": {"type": "string"}},
    }

    def _doc_route(path: str, *, summary: str, media: Dict[str, Any], **extra: Any):
        """Register one document route as GET-in-schema plus a hidden HEAD.

        Two registrations rather than one `methods=["GET", "HEAD"]` route,
        because FastAPI derives an operationId per route and then emits it
        once per method — which produced six `Duplicate Operation ID`
        warnings and a schema whose operationIds collide, so a generated
        client silently loses methods. HEAD is a protocol obligation
        (RFC 9110) rather than a distinct operation for a client author,
        so it is registered and kept out of the schema.
        """

        def decorator(fn):
            router.add_api_route(
                path,
                fn,
                methods=["GET"],
                summary=summary,
                responses={200: {"content": media, "description": summary}},
                **extra,
            )
            router.add_api_route(path, fn, methods=["HEAD"], include_in_schema=False, **extra)
            return fn

        return decorator

    @_doc_route(
        "/llms.txt",
        summary="This site's llms.txt index — the machine-readable documentation entry point",
        media=MARKDOWN_MEDIA_TYPES,
        response_class=_MarkdownResponse,
    )
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
                        _emit(request, tier_path, tier, status, html)
                        return Response(
                            content=html,
                            status_code=status,
                            media_type="text/html",
                            headers=headers,
                        )

            _emit(request, tier_path, tier, status, body)
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

        @_doc_route(
            TIER_DOC_PATHS["small"],
            summary="The smallest corpus tier — index and taglines only",
            media=MARKDOWN_MEDIA_TYPES,
            response_class=_MarkdownResponse,
        )
        def _llms_small(request: Request):
            return _serve_tier("small", request)

        @_doc_route(
            TIER_DOC_PATHS["full"],
            summary="The whole corpus in one document — every page's prose",
            media=MARKDOWN_MEDIA_TYPES,
            response_class=_MarkdownResponse,
        )
        def _llms_full(request: Request):
            return _serve_tier("full", request)

    @_doc_route(
        "/{page_path:path}/llms.txt",
        summary="One page's prose documentation",
        media=MARKDOWN_MEDIA_TYPES,
        response_class=_MarkdownResponse,
    )
    def _llms_txt(page_path: str, request: Request):
        return _serve_llms(page_path, request)

    @_doc_route(
        "/robots.txt",
        summary="Crawler policy, rendered from the vendor registry",
        media={"text/plain": {"schema": {"type": "string"}}},
        response_class=PlainTextResponse,
    )
    def _robots(request: Request):
        body = build_robots_txt(app)
        _emit(request, "/robots.txt", "policy", 200, body)
        return PlainTextResponse(body)

    if getattr(config, "panel", False):
        # P1: the read-only operator panel — see the Flask adapter's note.
        @_doc_route(
            getattr(config, "panel_path", "/llms-policy"),
            summary="Operator policy panel (token-gated; 404 without one)",
            media={"text/html": {"schema": {"type": "string"}}},
            response_class=_HtmlSchemaResponse,
        )
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

    @_doc_route(
        "/sitemap.xml",
        summary="XML sitemap of every public page",
        media={"application/xml": {"schema": {"type": "string"}}},
        response_class=_XmlResponse,
    )
    def _sitemap(request: Request):
        body = build_sitemap_xml(
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        _emit(request, "/sitemap.xml", "sitemap", 200, body)
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

    # -----------------------------------------------------------------
    # 2.10 — the /.well-known/ namespace, and the refusal under it
    # -----------------------------------------------------------------
    #
    # Measured before this shipped, on three live hosts and all three
    # adapters: EVERY path under /.well-known/ answered 200 with the Dash
    # app shell. An agent asking for an API catalog or OAuth metadata got
    # a web page, so nothing published here could be trusted. The guard
    # ships with the documents rather than after them.
    #
    # Starlette matches in REGISTRATION order, and this router is included
    # below before Dash registers its page catch-all from the lifespan
    # startup — so the specific paths precede the guard, the guard
    # precedes Dash, and a host that registered its own well-known route
    # before add_llms_routes() still wins over all of it.
    _wk_claimed = {getattr(route, "path", None) for route in _flatten_routes(server.routes)}

    def _wk_result(request, body: str, content_type: str, status: int) -> Response:
        _emit(request, request.url.path, wellknown.WELLKNOWN_TIER, status, body)
        return Response(
            content=body,
            status_code=status,
            media_type=content_type,
            headers={"Cache-Control": "no-store"} if status == 404 else {},
        )

    if wellknown.API_CATALOG_PATH not in _wk_claimed:

        @_doc_route(
            wellknown.API_CATALOG_PATH,
            summary="RFC 9727 API catalog — this host's machine surfaces as a linkset",
            media={wellknown.LINKSET_TYPE: {"schema": {"type": "object"}}},
        )
        def _wk_api_catalog(request: Request):
            # FastAPI is the one backend that really serves an OpenAPI
            # document, so it is the one backend whose catalog may claim
            # `service-desc`. Flask and Quart omit the relation rather
            # than point at a 404.
            return _wk_result(
                request,
                wellknown.build_api_catalog(
                    app,
                    openapi_path=server.openapi_url or None,
                    status_path=wellknown.detect_status_path(_wk_claimed),
                ),
                wellknown.LINKSET_TYPE,
                200,
            )

    if wellknown.MCP_CARD_PATH not in _wk_claimed:

        @_doc_route(
            wellknown.MCP_CARD_PATH,
            summary="MCP server card, when this app registers MCP resources",
            media={"application/json": {"schema": {"type": "object"}}},
        )
        def _wk_mcp_card(request: Request):
            card = wellknown.build_mcp_server_card(app, config)
            if card is None:
                return _wk_result(request, wellknown.not_found_body(), wellknown.JSON_TYPE, 404)
            return _wk_result(request, card, wellknown.JSON_TYPE, 200)

    if wellknown.AGENT_SKILLS_PATH not in _wk_claimed:

        @_doc_route(
            wellknown.AGENT_SKILLS_PATH,
            summary="Agent Skills discovery index for this host's SKILL.md",
            media={"application/json": {"schema": {"type": "object"}}},
        )
        def _wk_agent_skills(request: Request):
            return _wk_result(
                request, wellknown.build_agent_skills_index(app), wellknown.JSON_TYPE, 200
            )

    @router.api_route(
        "/.well-known/{rest:path}", methods=DOC_ROUTE_METHODS, include_in_schema=False
    )
    def _wk_guard(rest: str, request: Request):
        return _wk_result(request, wellknown.not_found_body(), wellknown.JSON_TYPE, 404)

    for _wk_root in wellknown.ROOT_DISCOVERY_PATHS:
        if _wk_root in _wk_claimed:
            continue

        def _make_root_guard(_path=_wk_root):
            def _root_guard(request: Request):
                return _wk_result(request, wellknown.not_found_body(), wellknown.JSON_TYPE, 404)

            return _root_guard

        router.add_api_route(
            _wk_root,
            _make_root_guard(),
            methods=DOC_ROUTE_METHODS,
            include_in_schema=False,
        )

    # IMPORTANT: register router last so /{page_path:path}/llms.txt doesn't
    # shadow user-registered routes like /api/something.
    server.include_router(router)

    _allow_head_wherever_get_is_allowed(server)
    _apply_openapi_identity(server, app, config)


def _apply_openapi_identity(server: Any, app: Any, config: Any) -> None:
    """Say whose documentation this schema describes (2.9.3).

    Measured on a live host 2026-08-31: `info` was
    `{"title": "FastAPI", "version": "0.1.0"}` — FastAPI's defaults. An
    agent that fetches /openapi.json therefore learns the framework and
    nothing else, on a surface whose entire purpose is telling agents what
    a site is.

    Two rules, both about not lying:

    * **Never overwrite what the host set.** Only the literal FastAPI
      default (`"FastAPI"`) is replaced; any other title is the host's own
      answer and stands. Same for a description that is already non-empty.
    * **The description says DOCUMENTATION BACKEND.** A host whose app
      documents a Python library publishes a schema that an agent will
      otherwise read as that library's HTTP API — which it is not. The
      sentence is what stops that misreading.

    `info.version` is left at FastAPI's default unless the host injects
    one: the package does not know the host's version and will not invent
    it. The template passes its healthz app key through
    ``openapi_title``/``openapi_description``; that key lives on the host,
    not here.
    """
    try:
        title = getattr(config, "openapi_title", None) or getattr(app, "title", None)
        if title and getattr(server, "title", None) in (None, "", "FastAPI"):
            server.title = str(title)

        description = getattr(config, "openapi_description", None)
        if not description:
            name = getattr(server, "title", None) or "this site"
            description = (
                f"Machine-readable documentation surfaces for {name}: "
                "`/llms.txt` and per-page `/<page>/llms.txt` prose, the "
                "`/llms-small.txt` and `/llms-full.txt` corpus tiers, "
                "`/robots.txt` crawler policy and `/sitemap.xml`. "
                "This schema describes the DOCUMENTATION BACKEND of the "
                "site — not the API of whatever the site documents."
            )
        if not getattr(server, "description", None):
            server.description = description

        version = getattr(config, "openapi_version", None)
        if version:
            server.version = str(version)

        # FastAPI caches the generated document on first request; identity
        # set after that would never be published.
        server.openapi_schema = None
    except Exception:  # noqa: BLE001
        pass


def _flatten_routes(routes: Any, _depth: int = 0) -> list:
    """Every route reachable from a routing table, nested ones included.

    Starlette 1.x + FastAPI 0.14x do not flatten an included router into
    ``app.routes``: this package's own document routes sit inside an
    ``_IncludedRouter`` wrapper, reachable through ``original_router``.
    Older versions do flatten them. Walking both shapes is what keeps this
    module's behaviour — and the test that pins it — the same on either,
    instead of silently depending on which FastAPI a host installed.

    Depth-bounded and exception-proof: this runs at startup and on HEAD
    requests, and an unfamiliar router shape must cost nothing worse than
    a route this pass does not reach.
    """
    found: list = []
    if _depth > 3:
        return found
    try:
        for route in routes or []:
            found.append(route)
            for attr in ("original_router", "router"):
                nested = getattr(route, attr, None)
                nested_routes = getattr(nested, "routes", None)
                if nested_routes:
                    found.extend(_flatten_routes(nested_routes, _depth + 1))
                    break
            else:
                nested_routes = getattr(route, "routes", None)
                if nested_routes and nested_routes is not routes:
                    found.extend(_flatten_routes(nested_routes, _depth + 1))
    except Exception:  # noqa: BLE001
        pass
    return found


def _allow_head_wherever_get_is_allowed(server: Any) -> None:
    """Make HEAD work on every GET route of a FastAPI-backed app.

    Measured 2026-08-31, in-process on all three backends: a browser-UA
    ``HEAD /`` returned **405 Allow: GET** on FastAPI while Googlebot-UA
    and suppressed-UA HEAD returned 200 — and Flask *and Quart* were clean
    on all three. So this is not an ASGI property and not the lane split:

    * Werkzeug (Flask, Quart) adds HEAD to every GET rule automatically;
    * Starlette's own ``Route`` does the same (``if "GET" in methods:
      methods.add("HEAD")``);
    * **FastAPI's ``APIRoute`` does not** — and Dash's FastAPI backend
      registers its index route through it, as ``methods=["GET"]``.

    The User-agent only appeared to matter because a crawler never reaches
    that route: this package's own middleware answers the crawler lane
    itself, HEAD included, while a browser falls through to Dash's
    GET-only route and Starlette rejects the method before any of our code
    runs again. One backend disagreeing with the other two about a method
    RFC 9110 requires wherever GET is allowed is exactly the class of
    defect the adapter parity tests exist to catch.

    Only routes that already allow GET are touched, and only by adding
    HEAD — no route gains a method it did not already answer with the same
    handler.

    Called twice on purpose, and both calls are needed. Dash's eager
    routes (``/`` among them) exist by the time ``add_llms_routes`` runs,
    so the registration-time pass catches those. But **Dash's FastAPI
    backend registers its page catch-all from the ASGI lifespan startup
    event**, which fires after this module has finished: measured
    2026-08-31, the first pass fixed ``/`` while ``/guide`` still returned
    405. So the request path re-runs it for HEAD. The pass is idempotent
    and early-continues on every already-correct route, so the repeat is
    one set-membership test per route, on a method that is rare by nature.

    A path that ALREADY has a route answering HEAD is left alone, and that
    exclusion is load-bearing rather than an optimisation. This package
    registers each of its own document routes twice on purpose — a GET
    operation in the schema plus a HEAD route kept out of it — so that
    FastAPI stops emitting one operationId for both methods. Folding HEAD
    back into the GET route would undo exactly that, and it did: measured
    on Python 3.9's older FastAPI, every doc path came back as
    ``['GET', 'HEAD']`` and the schema regained six colliding operationIds.
    Newer FastAPI omits HEAD from the schema and hid the same mistake.

    Never raises: a routing table shape we did not expect must not take
    down startup, or a request, over a method fallback.
    """
    try:
        routes = _flatten_routes(getattr(server, "routes", []))
        answered = {
            getattr(route, "path", None)
            for route in routes
            if "HEAD" in (getattr(route, "methods", None) or ())
        }
        for route in routes:
            methods = getattr(route, "methods", None)
            if not methods or "GET" not in methods or "HEAD" in methods:
                continue
            if getattr(route, "path", None) in answered:
                # Something else already answers HEAD here — see above.
                continue
            try:
                methods.add("HEAD")
            except AttributeError:
                # A sequence rather than a set — leave it alone rather than
                # guess at the route class's contract.
                continue
    except Exception:  # noqa: BLE001
        pass
