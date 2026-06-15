"""
FastAPI adapter for dash-improve-my-llms 2.0.

Translates between FastAPI/Starlette's request/response cycle and the
pure handlers in handlers.py. Only this file knows about FastAPI types.
"""

from __future__ import annotations

from typing import Any

from .handlers import (
    build_llms_txt_for_page,
    build_robots_txt,
    build_sitemap_xml,
    handle_bot_request,
)


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
        from fastapi.responses import PlainTextResponse
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI backend detected but `fastapi` is not installed. "
            "Install with: pip install dash-improve-my-llms[fastapi]"
        ) from exc

    server = app.server

    @server.middleware("http")
    async def _bot_middleware(request: Request, call_next):
        result = handle_bot_request(
            path=request.url.path,
            user_agent=request.headers.get("user-agent", ""),
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        if result is None:
            return await call_next(request)
        return Response(
            content=result["body"],
            status_code=result["status"],
            media_type=result["content_type"],
            headers=result.get("headers", {}),
        )

    router = APIRouter()

    @router.get("/llms.txt", response_class=PlainTextResponse)
    def _llms_txt_root():
        body, status = build_llms_txt_for_page(
            app=app,
            page_path="",
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        return PlainTextResponse(body, status_code=status)

    @router.get("/{page_path:path}/llms.txt", response_class=PlainTextResponse)
    def _llms_txt(page_path: str):
        body, status = build_llms_txt_for_page(
            app=app,
            page_path=page_path,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        return PlainTextResponse(body, status_code=status)

    @router.get("/robots.txt", response_class=PlainTextResponse)
    def _robots():
        return PlainTextResponse(build_robots_txt(app))

    @router.get("/sitemap.xml")
    def _sitemap():
        body = build_sitemap_xml(
            app=app,
            page_metadata=state.page_metadata,
            hidden_paths=state.hidden_pages,
        )
        return Response(content=body, media_type="application/xml")

    # IMPORTANT: register router last so /{page_path:path}/llms.txt doesn't
    # shadow user-registered routes like /api/something.
    server.include_router(router)
