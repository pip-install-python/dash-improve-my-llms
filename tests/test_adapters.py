"""
Integration tests that drive real requests through each backend adapter.

These exist because the adapters previously had **zero** coverage. Every
handler was unit-tested in isolation and passed, while the wiring that
actually decides what a crawler receives was never exercised — so a
regression that emptied the page body on a production site got through a
fully green suite.

Each test here goes through a real Dash app and a real HTTP client for the
backend under test. If a case can be expressed against a pure handler
instead, it belongs in another file; what's tested here is specifically that
the routes, middleware, and response rewriting are connected.
"""

from __future__ import annotations

import pytest

import dash_improve_my_llms as pkg

GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
GPTBOT = "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)"
BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

STUB = "This page contains interactive content that requires JavaScript"


# ---------------------------------------------------------------------------
# App construction
# ---------------------------------------------------------------------------


def _reset_package_state():
    pkg._state.page_metadata.clear()
    pkg._state.hidden_pages.clear()
    pkg._state.network = pkg.NetworkConfig()


def _build_app(backend: str, **config_kwargs):
    """A small pages app wired up the way a real consumer would wire one."""
    import dash
    from dash import Dash, html

    _reset_package_state()

    # dash.page_registry is process-global; clear it so tests don't leak pages
    # into each other.
    if hasattr(dash, "page_registry"):
        dash.page_registry.clear()
    if hasattr(dash, "_pages") and hasattr(dash._pages, "PAGE_REGISTRY"):
        dash._pages.PAGE_REGISTRY.clear()

    kwargs = {"use_pages": True, "pages_folder": ""}
    if backend != "flask":
        kwargs["backend"] = backend

    app = Dash(__name__, **kwargs)
    app.title = "Test App"
    app._base_url = "https://example.com"

    dash.register_page("home", path="/", name="Home", layout=html.Div("home"))
    dash.register_page("guide", path="/guide", name="Guide", layout=html.Div("guide"))
    dash.register_page("admin", path="/admin", name="Admin", layout=html.Div("admin"))

    pkg.register_page_metadata(
        "/", name="Home", description="The landing page.", llms_doc="# Home\n\nWelcome."
    )
    pkg.register_page_metadata(
        "/guide",
        name="The Guide",
        description="How to use it.",
        llms_doc="# The Guide\n\nRead [home](/) first.\n\n- step one\n- step two",
    )
    pkg.mark_hidden("/admin")

    app.layout = html.Div([dash.page_container])

    config_kwargs.setdefault("warn_missing_llms_doc", False)
    pkg.add_llms_routes(app, pkg.LLMSConfig(**config_kwargs))
    return app


def _lower(headers) -> dict:
    """Lowercase header keys — the three backends disagree on casing."""
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


class _Client:
    """One `get(path, ua)` interface over Flask, Quart and Starlette clients."""

    def __init__(self, app, backend: str):
        self.backend = backend
        if backend == "flask":
            self._client = app.server.test_client()
        elif backend == "quart":
            self._client = app.server.test_client()
        else:
            from starlette.testclient import TestClient

            # Dash's FastAPI backend registers its page catch-all from the
            # ASGI lifespan startup event, and TestClient only runs lifespan
            # when entered as a context manager. Skipping this makes every
            # non-root page 404 and looks like a routing bug in this package.
            self._client = TestClient(app.server)
            self._client.__enter__()

    def get(self, path: str, ua: str = BROWSER, accept: str = "*/*"):
        status, body, _ = self.get_full(path, ua=ua, accept=accept)
        return status, body

    def get_full(self, path: str, ua: str = BROWSER, accept: str = "*/*"):
        """(status, body, headers) — headers matter for content negotiation."""
        headers = {"User-Agent": ua, "Accept": accept}

        if self.backend == "fastapi":
            response = self._client.get(path, headers=headers)
            return response.status_code, response.text, _lower(response.headers)

        if self.backend == "quart":
            import asyncio

            async def _run():
                response = await self._client.get(path, headers=headers)
                return (
                    response.status_code,
                    await response.get_data(as_text=True),
                    _lower(response.headers),
                )

            return asyncio.get_event_loop().run_until_complete(_run())

        response = self._client.get(path, headers=headers)
        return (
            response.status_code,
            response.get_data(as_text=True),
            _lower(response.headers),
        )


def _dash_supports_pluggable_backends() -> bool:
    """Dash gained `Dash(backend=...)` after 4.1 — 4.1.0 is Flask-only."""
    import inspect

    from dash import Dash

    return "backend" in inspect.signature(Dash.__init__).parameters


def _backends():
    """Test every backend this environment can actually run."""
    available = ["flask"]

    if not _dash_supports_pluggable_backends():
        return available

    for name, module in (("fastapi", "fastapi"), ("quart", "quart")):
        try:
            __import__(module)
        except ImportError:
            continue
        available.append(name)
    return available


def _params():
    """Mark combinations Dash itself is broken on as xfail, not failures.

    The table lives in the package because deployed apps get the same warning
    at startup; see dash_improve_my_llms/_compat.py for what was reproduced
    against stock Dash.
    """
    import dash

    from dash_improve_my_llms._compat import find_known_issue

    params = []
    for name in _backends():
        issue = find_known_issue(getattr(dash, "__version__", ""), name)
        marks = [pytest.mark.xfail(reason=issue, strict=False)] if issue else []
        params.append(pytest.param(name, marks=marks, id=name))
    return params


@pytest.fixture(params=_params())
def backend(request):
    return request.param


@pytest.fixture
def client(backend):
    return _Client(_build_app(backend), backend)


# ---------------------------------------------------------------------------
# The regression this whole file exists for
# ---------------------------------------------------------------------------


def test_crawler_receives_page_prose_not_the_stub(client):
    status, body = client.get("/guide", ua=GOOGLEBOT)
    assert status == 200
    assert STUB not in body
    assert "<h1>The Guide</h1>" in body
    assert "<li>step one</li>" in body


def test_prose_links_survive_into_the_html(client):
    """Links inside prose are the internal crawl graph; they must render."""
    _, body = client.get("/guide", ua=GOOGLEBOT)
    assert '<a href="/">home</a>' in body


def test_every_visible_page_has_a_distinct_body(client):
    """Guards against the 'thin near-duplicates' failure mode."""
    _, home = client.get("/", ua=GOOGLEBOT)
    _, guide = client.get("/guide", ua=GOOGLEBOT)

    home_main = home.split("<main>")[1].split("</main>")[0]
    guide_main = guide.split("<main>")[1].split("</main>")[0]

    assert home_main != guide_main
    assert "Welcome." in home_main
    assert "Read" in guide_main


# ---------------------------------------------------------------------------
# Universal prerender
# ---------------------------------------------------------------------------


def test_ordinary_browser_also_gets_the_prose_in_initial_html(client):
    """The anti-cloaking property: same content without a crawler UA."""
    status, body = client.get("/guide", ua=BROWSER)
    assert status == 200
    assert 'id="dimll-prerender"' in body
    assert "<h1>The Guide</h1>" in body
    # ...and it is still a working Dash app.
    assert "react-entry-point" in body
    assert "_dash-loading" in body


def test_prerender_sets_per_page_head_metadata(client):
    _, body = client.get("/guide", ua=BROWSER)
    assert "<title>The Guide</title>" in body
    assert 'content="How to use it."' in body
    assert '<link data-dimll-prerender="1" rel="canonical" ' in body
    assert "https://example.com/guide" in body


def test_prerender_can_be_disabled(backend):
    app = _build_app(backend, prerender=False)
    status, body = _Client(app, backend).get("/guide", ua=BROWSER)
    assert status == 200
    assert 'id="dimll-prerender"' not in body
    # The crawler path still works with prerender off.
    _, crawler_body = _Client(app, backend).get("/guide", ua=GOOGLEBOT)
    assert "<h1>The Guide</h1>" in crawler_body


def test_prerender_does_not_touch_non_page_routes(client):
    status, body = client.get("/sitemap.xml")
    assert status == 200
    assert "dimll-prerender" not in body


def test_hidden_pages_are_not_prerendered(client):
    _, body = client.get("/admin", ua=BROWSER)
    assert 'id="dimll-prerender"' not in body


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_page_llms_txt(client):
    status, body = client.get("/guide/llms.txt")
    assert status == 200
    assert body.startswith("# The Guide")


def test_root_llms_txt_is_an_index_of_every_page(client):
    status, body = client.get("/llms.txt")
    assert status == 200
    assert "## Pages" in body
    assert "https://example.com/guide" in body
    assert "https://example.com/guide/llms.txt" in body
    # No double slash on the root entry.
    assert "example.com//llms.txt" not in body


def test_hidden_page_is_404_everywhere(client):
    assert client.get("/admin/llms.txt")[0] == 404
    assert client.get("/admin", ua=GOOGLEBOT)[0] == 404

    _, sitemap = client.get("/sitemap.xml")
    assert "/admin" not in sitemap

    _, index = client.get("/llms.txt")
    assert "/admin" not in index


def test_robots_and_sitemap(client):
    status, robots = client.get("/robots.txt")
    assert status == 200
    assert "Sitemap: https://example.com/sitemap.xml" in robots

    status, sitemap = client.get("/sitemap.xml")
    assert status == 200
    assert "<urlset" in sitemap
    assert "https://example.com/guide" in sitemap


# ---------------------------------------------------------------------------
# Bot policy
# ---------------------------------------------------------------------------


def test_training_bots_are_blocked_when_configured(backend):
    app = _build_app(backend)
    app._robots_config = pkg.RobotsConfig(block_ai_training=True)
    status, body = _Client(app, backend).get("/guide", ua=GPTBOT)
    assert status == 403
    assert "training" in body.lower()


def test_training_bots_are_allowed_by_default(client):
    status, _ = client.get("/guide", ua=GPTBOT)
    assert status == 200


# ---------------------------------------------------------------------------
# Network directory
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# llms.txt navigation + content negotiation
# ---------------------------------------------------------------------------

BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def test_page_llms_txt_carries_a_route_back_to_the_network(backend):
    """A page document fetched alone must not be a dead end for an agent."""
    app = _build_app(backend)
    pkg.register_network(
        name="Test network",
        hub_url="https://hub.example",
        peers=[{"name": "Sibling", "url": "https://sibling.example"}],
    )
    _, body = _Client(app, backend).get("/guide/llms.txt")

    assert "https://example.com/llms.txt" in body  # this site's index
    assert "https://hub.example/llms.txt" in body  # the network's index
    assert "https://example.com/sitemap.xml" in body


def test_nav_block_sits_after_the_title_not_before(client):
    _, body = client.get("/guide/llms.txt")
    assert body.startswith("# The Guide")
    assert body.index("Site index:") < body.index("step one")


def test_nav_can_be_disabled(backend):
    app = _build_app(backend, llms_nav=False)
    _, body = _Client(app, backend).get("/guide/llms.txt")
    assert "Site index:" not in body
    assert body.startswith("# The Guide")


def test_agents_receive_markdown_not_the_viewer(client):
    """The core contract of the whole route."""
    status, body, headers = client.get_full("/guide/llms.txt")
    assert status == 200
    assert "text/markdown" in headers.get("content-type", "").lower()
    assert "<!DOCTYPE html>" not in body
    assert "dv-banner" not in body


def test_crawlers_receive_markdown_even_when_accepting_html(client):
    _, body, headers = client.get_full("/guide/llms.txt", ua=GOOGLEBOT, accept=BROWSER_ACCEPT)
    assert "text/markdown" in headers.get("content-type", "").lower()
    assert "dv-banner" not in body


def test_browsers_receive_the_rendered_viewer(client):
    status, body, headers = client.get_full("/guide/llms.txt", ua=BROWSER, accept=BROWSER_ACCEPT)
    assert status == 200
    assert "text/html" in headers.get("content-type", "").lower()
    assert 'class="dv-banner"' in body
    # The document itself is still there, rendered.
    assert "<h1>The Guide</h1>" in body
    # And it must not compete with the real page in search results.
    assert "noindex" in body


def test_llms_txt_sets_vary_accept(client):
    """Without Vary a CDN can hand a cached HTML body to the next agent."""
    for accept in ("*/*", BROWSER_ACCEPT):
        _, _, headers = client.get_full("/guide/llms.txt", accept=accept)
        assert "accept" in headers.get("vary", "").lower()


def test_raw_query_forces_markdown_in_a_browser(client):
    _, body, headers = client.get_full("/guide/llms.txt?raw=1", ua=BROWSER, accept=BROWSER_ACCEPT)
    assert "text/markdown" in headers.get("content-type", "").lower()
    assert "dv-banner" not in body


def test_viewer_can_be_disabled(backend):
    app = _build_app(backend, llms_viewer=False)
    _, body, headers = _Client(app, backend).get_full(
        "/guide/llms.txt", ua=BROWSER, accept=BROWSER_ACCEPT
    )
    assert "text/markdown" in headers.get("content-type", "").lower()
    assert "dv-banner" not in body


def test_root_index_also_negotiates(client):
    _, md, md_headers = client.get_full("/llms.txt")
    assert "text/markdown" in md_headers.get("content-type", "").lower()
    assert "## Pages" in md

    _, html, html_headers = client.get_full("/llms.txt", ua=BROWSER, accept=BROWSER_ACCEPT)
    assert "text/html" in html_headers.get("content-type", "").lower()
    assert 'class="dv-banner"' in html


def test_hidden_page_llms_txt_is_still_404_in_a_browser(client):
    status, _, _ = client.get_full("/admin/llms.txt", ua=BROWSER, accept=BROWSER_ACCEPT)
    assert status == 404


# ---------------------------------------------------------------------------
# Tiered corpus documents — /llms-small.txt and /llms-full.txt
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_access():
    """Access control is process-global; no test may inherit another's."""
    from dash_improve_my_llms import access

    access.reset()
    yield
    access.reset()


def test_llms_small_serves_markdown(client):
    status, body, headers = client.get_full("/llms-small.txt")
    assert status == 200
    assert "text/markdown" in headers.get("content-type", "").lower()
    assert body.startswith("# Test App")
    # One document link per visible page, none for the hidden one.
    assert "https://example.com/guide/llms.txt" in body
    assert "/admin" not in body


def test_llms_full_is_the_whole_corpus(client):
    status, body, headers = client.get_full("/llms-full.txt")
    assert status == 200
    assert "text/markdown" in headers.get("content-type", "").lower()
    assert "Welcome." in body  # home prose
    assert "step one" in body  # guide prose
    assert "<!-- /guide — https://example.com/guide/llms.txt -->" in body
    assert "/admin" not in body  # hidden page: absent entirely


def test_root_index_advertises_both_tiers(client):
    _, body = client.get("/llms.txt")
    assert "https://example.com/llms-small.txt" in body
    assert "https://example.com/llms-full.txt" in body


def test_small_tier_negotiates_like_llms_txt(client):
    """Browser gets the viewer; ?raw=1 gets the document back."""
    status, html, headers = client.get_full("/llms-small.txt", ua=BROWSER, accept=BROWSER_ACCEPT)
    assert status == 200
    assert "text/html" in headers.get("content-type", "").lower()
    assert 'class="dv-banner"' in html
    # The view-raw link points at the tier document, not <tier>/llms.txt.
    assert "/llms-small.txt?raw=1" in html
    assert "llms-small.txt/llms.txt" not in html

    _, raw, raw_headers = client.get_full(
        "/llms-small.txt?raw=1", ua=BROWSER, accept=BROWSER_ACCEPT
    )
    assert "text/markdown" in raw_headers.get("content-type", "").lower()
    assert "dv-banner" not in raw


def test_browser_on_full_gets_a_summary_card_not_the_corpus(client):
    """The corpus can run to megabytes; a browser tab gets a card instead."""
    status, html, headers = client.get_full("/llms-full.txt", ua=BROWSER, accept=BROWSER_ACCEPT)
    assert status == 200
    assert "text/html" in headers.get("content-type", "").lower()
    assert "step one" not in html  # no page prose rendered
    assert "/llms-full.txt?raw=1" in html  # ...but the way to it is named

    # Agents keep receiving the corpus itself from the same URL.
    _, agent_body = client.get("/llms-full.txt", ua=GPTBOT)
    assert "step one" in agent_body


def test_full_tier_chrome_does_not_describe_the_card_as_what_agents_get(client):
    """Regression: the viewer's raw-source line promises that agents receive
    "the Markdown below". On /llms-full.txt they receive the corpus instead,
    so the default sentence was a falsehood — on the one surface whose whole
    promise is that humans and machines are reading the same bytes."""
    _, html, _ = client.get_full("/llms-full.txt", ua=BROWSER, accept=BROWSER_ACCEPT)
    assert "receive the Markdown below" not in html
    assert "receive the full corpus itself" in html

    # The other two tiers do serve exactly what they render, and still say so.
    for path in ("/llms.txt", "/llms-small.txt"):
        _, other, _ = client.get_full(path, ua=BROWSER, accept=BROWSER_ACCEPT)
        assert "receive the Markdown below" in other, path


def test_every_tier_renders_the_same_chrome_in_the_same_order(client):
    """No test pinned the viewer's block order, which is how a reported
    "the tiers render inconsistent chrome" claim went unchecked."""
    for path in ("/llms.txt", "/llms-small.txt", "/llms-full.txt"):
        _, html, _ = client.get_full(path, ua=BROWSER, accept=BROWSER_ACCEPT)
        positions = [
            html.index('class="dv-banner"'),
            html.index('class="dv-raw"'),
            html.index('class="dv-doc"'),
            html.index('class="dv-foot"'),
        ]
        assert positions == sorted(positions), f"{path} chrome out of order"


def test_agents_receive_byte_identical_output_to_raw_on_every_tier(client):
    """The contract every tier does keep: ?raw=1 and an agent UA agree."""
    for path in ("/llms.txt", "/llms-small.txt", "/llms-full.txt"):
        _, agent_body = client.get(path, ua=GPTBOT)
        _, raw_body = client.get(f"{path}?raw=1", ua=BROWSER, accept=BROWSER_ACCEPT)
        assert agent_body == raw_body, path


def test_full_tier_is_noindex(client):
    _, _, headers = client.get_full("/llms-full.txt")
    assert "noindex" in headers.get("x-robots-tag", "").lower()


def test_tier_docs_bypass_the_training_bot_block(backend):
    """Regression: block_ai_training must not 403 the tier documents."""
    app = _build_app(backend)
    app._robots_config = pkg.RobotsConfig(block_ai_training=True)
    client = _Client(app, backend)

    status, body = client.get("/llms-full.txt", ua=GPTBOT)
    assert status == 200
    assert "step one" in body


def test_tier_docs_with_authority_are_never_shared_cached(backend):
    from dash_improve_my_llms import access

    app = _build_app(backend)
    access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
    _, _, headers = _Client(app, backend).get_full("/llms-small.txt")
    assert headers.get("cache-control") == "private, no-store"


def test_tiers_can_be_disabled(backend):
    app = _build_app(backend, llms_tiers=False)
    client = _Client(app, backend)
    for path in ("/llms-small.txt", "/llms-full.txt"):
        status, _, headers = client.get_full(path)
        content_type = headers.get("content-type", "").lower()
        # Whatever Dash serves for an unknown path (404, or the app shell),
        # it must not be the tier document.
        assert not (
            status == 200 and "text/markdown" in content_type
        ), f"{path} still served with llms_tiers=False"


def test_network_directory_reaches_llms_txt_and_html(backend):
    app = _build_app(backend)
    pkg.register_network(
        name="Test network",
        hub_url="https://hub.example",
        peers=[{"name": "Sibling", "url": "https://sibling.example"}],
        external=[{"name": "Upstream", "url": "https://upstream.example"}],
    )
    client = _Client(app, backend)

    _, index = client.get("/llms.txt")
    assert "## Network" in index
    assert "https://sibling.example/llms.txt" in index
    assert "## External references" in index

    _, page = client.get("/guide", ua=BROWSER)
    assert 'rel="related" href="https://sibling.example"' in page
    # Third-party links must not pass ranking signal.
    assert 'rel="nofollow noopener"' in page
