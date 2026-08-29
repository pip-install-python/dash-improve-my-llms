"""
Flask adapter for dash-improve-my-llms 2.0.

Translates between Flask's request/response cycle and the pure handlers
in handlers.py. All Flask-specific code lives here.
"""

from __future__ import annotations

from typing import Any, Dict

from . import _ledger, access
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
    should_prerender,
    wants_html_viewer,
)
from .seo import ROOT_ICON_PATHS, root_icon_target


def _doc_headers() -> Dict[str, str]:
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


def register_flask(app: Any, config: Any, state: Any) -> None:
    """
    Wire the 4 routes and the bot middleware into a Flask-backed Dash app.

    Args:
        app: The Dash app (app.server is a flask.Flask instance).
        config: LLMSConfig.
        state: Shared module-level state (page_metadata, hidden_pages).
    """
    from flask import Response, abort, redirect, request

    server = app.server

    @server.before_request
    def _bot_middleware():  # type: ignore[unused-ignore]
        result = handle_bot_request(
            path=request.path,
            user_agent=request.headers.get("User-Agent", ""),
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
            headers=normalize_headers(request.headers),
            method=request.method,
        )
        if result is None:
            return None
        return Response(
            result["body"],
            status=result["status"],
            mimetype=result["content_type"],
            headers=result.get("headers", {}),
        )

    def _emit(path: str, tier: str, status: int, body, verdict: str = "") -> None:
        """One read event for a document this adapter served.

        The package does no I/O with it — see _ledger. On a host with no
        listener registered this is a single truth-test.
        """
        if not _ledger.has_listeners():
            return
        _ledger.emit_read(
            path=path,
            method=request.method,
            tier=tier,
            status=status,
            body=body,
            verdict=verdict or _ledger.verdict_for_status(status),
            user_agent=request.headers.get("User-Agent", ""),
            headers=normalize_headers(request.headers),
        )

    if getattr(config, "prerender", True):

        @server.after_request
        def _prerender(response):  # type: ignore[unused-ignore]
            # The policy panel is operator chrome, not a page: private/
            # no-store, and never prerender-mutated (the context build
            # would invoke the app's access check for a non-page path).
            if getattr(config, "panel", False) and request.path == getattr(
                config, "panel_path", "/llms-policy"
            ):
                return response
            if not should_prerender(
                path=request.path,
                status=response.status_code,
                content_type=response.content_type or "",
            ):
                return response
            # Streamed/passthrough responses have no materialised body.
            if response.direct_passthrough or not response.is_sequence:
                return response

            # 2.8: this page route answers a browser and a crawler with
            # different bytes — the middleware above short-circuits machines
            # to the crawler document — so the header has to say so whether
            # or not the prerender ends up injecting anything.
            response.headers["Vary"] = merge_vary(
                response.headers.get("Vary", ""), "Accept", "User-Agent"
            )

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
                # llms.txt v2 discovery (2.7.1): the relations ride the
                # headers of the page response too.
                page_path_norm = request.path.rstrip("/") or "/"
                response.headers["Link"] = link_header_value(page_path_norm)
            return response

    @server.route("/<path:page_path>/llms.txt", methods=DOC_ROUTE_METHODS)
    @server.route("/llms.txt", defaults={"page_path": ""}, methods=DOC_ROUTE_METHODS)
    def _llms_txt(page_path: str):
        body, status = build_llms_txt_for_page(
            app=app,
            page_path=page_path,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
            state=state,
            include_nav=getattr(config, "llms_nav", True),
            user_agent=request.headers.get("User-Agent", ""),
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
                    _emit(request.path, "index" if not page_path else "page", status, html)
                    return Response(
                        html,
                        status=status,
                        mimetype="text/html",
                        headers=_doc_headers(),
                    )

        headers = _doc_headers()
        # 2.7.1: the digest that makes representation parity provable, and
        # the text/plain compatibility ramp (same bytes, compatible type —
        # a mainstream agent stack rejects text/markdown outright).
        digest = page_source_digest(
            f"/{page_path}" if page_path else "/",
            state.page_metadata,
            state.hidden_pages,
            state,
        )
        if digest and status == 200:
            headers[DIGEST_HEADER] = digest
        mimetype = (
            "text/plain" if wants_plain_text(request.headers.get("Accept", "")) else "text/markdown"
        )
        if status == 402:
            # W5: private/no-store + the app's payment challenge. Enrichment
            # only — the Markdown body is the funnel; header failures inside
            # offer_headers degrade to a header-bare 402, never a different
            # verdict.
            headers.update(
                access.offer_headers("/llms.txt" if not page_path else f"/{page_path}/llms.txt")
            )
        _emit(request.path, "index" if not page_path else "page", status, body)
        return Response(
            body,
            status=status,
            mimetype=mimetype,
            headers=headers,
        )

    if getattr(config, "llms_tiers", True):

        @server.route(
            TIER_DOC_PATHS["small"], defaults={"tier": "small"}, methods=DOC_ROUTE_METHODS
        )
        @server.route(TIER_DOC_PATHS["full"], defaults={"tier": "full"}, methods=DOC_ROUTE_METHODS)
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
            if status == 402:
                headers.update(access.offer_headers(tier_path))
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
                        _emit(tier_path, tier, status, html)
                        return Response(
                            html,
                            status=status,
                            mimetype="text/html",
                            headers=headers,
                        )

            _emit(tier_path, tier, status, body)
            return Response(
                body,
                status=status,
                mimetype=(
                    "text/plain"
                    if wants_plain_text(request.headers.get("Accept", ""))
                    else "text/markdown"
                ),
                headers=headers,
            )

    @server.route("/robots.txt", methods=DOC_ROUTE_METHODS)
    def _robots():
        body = build_robots_txt(app)
        _emit("/robots.txt", "policy", 200, body)
        return Response(body, mimetype="text/plain")

    if getattr(config, "panel", False):
        # P1: the read-only operator panel. A plain route check is airtight
        # here (unlike a Dash Pages layout); unauthorized is 404, never 403
        # — the panel does not advertise its own existence.
        @server.route(getattr(config, "panel_path", "/llms-policy"), methods=DOC_ROUTE_METHODS)
        def _llms_panel():
            from . import panel as _panel

            req_headers = normalize_headers(request.headers)
            if not _panel.authorized(config, req_headers, request.args.get("token", "")):
                return Response("404 Not Found", status=404, mimetype="text/plain")
            return Response(
                _panel.build_panel_html(
                    app=app, config=config, state=state, request_headers=req_headers
                ),
                mimetype="text/html",
                headers=_panel.panel_response_headers(),
            )

    @server.route("/sitemap.xml", methods=DOC_ROUTE_METHODS)
    def _sitemap():
        body = build_sitemap_xml(
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        _emit("/sitemap.xml", "sitemap", 200, body)
        return Response(body, mimetype="application/xml")

    # Well-known root icons. Dash's page catch-all answers these with the app
    # shell (200 text/html), so a search engine that falls back to
    # /favicon.ico — which is what it does when the page it CRAWLED declared
    # no icon — receives markup where an image should be. Redirect rather than
    # serve: the package has no business reading an application's asset folder,
    # and every consumer of these paths follows a redirect.
    #
    # An application that registered its own route for one of these paths
    # before improve() keeps it — werkzeug happens to match the earlier of
    # two identical rules, but relying on that would leave a dead duplicate
    # in the map. A route registered AFTER improve() cannot be honoured;
    # register such routes first, or pass configure_seo(root_icons=False).
    _claimed = {rule.rule for rule in server.url_map.iter_rules()}
    for _root_path in ROOT_ICON_PATHS:
        if _root_path in _claimed:
            continue

        def _root_icon(_path=_root_path):
            target = root_icon_target(_path)
            if not target:
                abort(404)
            return redirect(target, code=302)

        server.add_url_rule(
            _root_path,
            endpoint=f"_dimll_icon{_root_path.replace('/', '_').replace('.', '_')}",
            view_func=_root_icon,
            methods=DOC_ROUTE_METHODS,
        )
