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

    def get(self, path: str, ua: str = BROWSER, accept: str = "*/*", extra_headers: dict = None):
        status, body, _ = self.get_full(path, ua=ua, accept=accept, extra_headers=extra_headers)
        return status, body

    def get_full(
        self, path: str, ua: str = BROWSER, accept: str = "*/*", extra_headers: dict = None
    ):
        """(status, body, headers) — headers matter for content negotiation.

        Redirects are never followed: Starlette's client follows them by
        default and Flask's does not, so a test asserting on a 302 would pass
        on one backend and fail on another for reasons unrelated to the code
        under test.
        """
        headers = {"User-Agent": ua, "Accept": accept, **(extra_headers or {})}

        if self.backend == "fastapi":
            response = self._client.get(path, headers=headers, follow_redirects=False)
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
    # 2.5.1 contract change: the browser title resolves exactly like the
    # crawler document's — this used to pin the bare page name, which is the
    # defect 2.5.0 fixed for crawlers and 2.5.1 fixes here.
    assert "<title>The Guide · Test App</title>" in body
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


# ---------------------------------------------------------------------------
# 2.5.0 — the crawler document must carry the same IDENTITY as the browser one
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_seo():
    """configure_seo is process-global; leaking it across tests would make the
    unconfigured no-op assertions pass for the wrong reason."""
    from dash_improve_my_llms import seo

    seo.reset()
    yield
    seo.reset()


ICONS = [
    "/assets/favicon/favicon.ico",
    {"href": "/assets/favicon/icon-192.png", "sizes": "192x192"},
    {"href": "/assets/favicon/apple-touch-icon.png", "rel": "apple-touch-icon", "sizes": "180x180"},
]


@pytest.mark.parametrize("backend", _backends())
def test_crawler_and_browser_agree_on_identity(backend):
    """The assertion the network was missing.

    Every SEO defect measured across the live fleet in August 2026 was one
    bug: the crawler document had drifted from the browser document. Browsers
    got 4-7 icon links and an og:image; Googlebot got zero of either, on every
    host, so search showed the generic globe. Content may differ between the
    two documents — that is what the prerender is for. Identity may not.
    """
    app = _build_app(backend)
    pkg.configure_seo(icons=ICONS, social_image="https://cdn.example/card.png")
    client = _Client(app, backend)

    _, crawler = client.get("/guide", ua=GOOGLEBOT)

    assert 'rel="icon"' in crawler
    assert 'sizes="192x192"' in crawler
    assert 'rel="apple-touch-icon"' in crawler
    assert 'property="og:image"' in crawler
    assert 'name="twitter:card"' in crawler
    # twitter:* must use name=, not property= — Twitter ignores property=.
    assert 'property="twitter:' not in crawler


@pytest.mark.parametrize("backend", _backends())
def test_crawler_title_keeps_the_site_name(backend):
    """A page shipped as "The Guide" to Google while the browser saw the app's
    own prefixed title, so the result was indistinguishable from every other
    page on the web with that heading."""
    app = _build_app(backend)
    client = _Client(app, backend)

    _, crawler = client.get("/guide", ua=GOOGLEBOT)
    assert "<title>The Guide · Test App</title>" in crawler
    # The H1 stays the page's own name — only the document title is qualified.
    assert "<h1>The Guide</h1>" in crawler


@pytest.mark.parametrize("backend", _backends())
def test_unconfigured_seo_adds_no_identity_tags(backend):
    """configure_seo is opt-in: an upgrade must not invent an icon or a card
    for a site that never declared one."""
    app = _build_app(backend)
    client = _Client(app, backend)

    _, crawler = client.get("/guide", ua=GOOGLEBOT)
    assert 'rel="icon"' not in crawler
    assert "og:image" not in crawler
    assert "twitter:" not in crawler


@pytest.mark.parametrize("backend", _backends())
def test_root_icon_paths_redirect_to_a_declared_icon(backend):
    """Google falls back to <origin>/favicon.ico when the page it crawled
    declares no icon. Dash's page catch-all answered all three well-known
    paths with the app shell (200 text/html) — a poisoned fallback, not a
    missing one."""
    app = _build_app(backend)
    pkg.configure_seo(icons=ICONS)
    client = _Client(app, backend)

    expected = {
        "/favicon.ico": "/assets/favicon/favicon.ico",
        "/apple-touch-icon.png": "/assets/favicon/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png": "/assets/favicon/apple-touch-icon.png",
    }
    for path, target in expected.items():
        status, _, headers = client.get_full(path)
        assert status == 302, f"{path} returned {status}"
        assert headers["location"].endswith(target), f"{path} -> {headers['location']}"


@pytest.mark.parametrize("backend", _backends())
def test_root_icon_paths_are_inert_without_configuration(backend):
    """No icons declared: the paths answer 404 rather than the app shell —
    a crawler that gets 404 correctly concludes "no icon" instead of parsing
    HTML where an image belongs."""
    app = _build_app(backend)
    client = _Client(app, backend)

    status, _, _ = client.get_full("/favicon.ico")
    assert status == 404


def test_app_registered_favicon_route_keeps_precedence():
    """An application that claimed /favicon.ico before improve() keeps it —
    the adapter skips paths that already have a route rather than stacking a
    duplicate rule and leaning on werkzeug's match order."""
    import dash
    from dash import Dash, html

    _reset_package_state()
    if hasattr(dash, "page_registry"):
        dash.page_registry.clear()
    if hasattr(dash, "_pages") and hasattr(dash._pages, "PAGE_REGISTRY"):
        dash._pages.PAGE_REGISTRY.clear()

    app = Dash(__name__, use_pages=True, pages_folder="")
    app.title = "Test App"
    dash.register_page("home", path="/", name="Home", layout=html.Div("home"))
    app.layout = html.Div([dash.page_container])

    app.server.add_url_rule("/favicon.ico", endpoint="user_favicon", view_func=lambda: "user-bytes")
    pkg.add_llms_routes(app, pkg.LLMSConfig(warn_missing_llms_doc=False))
    # Even with icons declared, the app's own route answers.
    pkg.configure_seo(icons=ICONS)

    response = app.server.test_client().get("/favicon.ico")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "user-bytes"


@pytest.mark.parametrize("backend", _backends())
def test_schema_type_and_publisher_reach_the_crawler(backend):
    """schema_type has been supported since 2.0 and set by nobody; sameAs is
    how a family of domains says it is one entity rather than N sites."""
    app = _build_app(backend)
    pkg.configure_seo(
        publisher="Example LLC",
        same_as=["https://pypi.org/project/example", "https://github.com/e/x"],
    )
    pkg.register_page_metadata("/guide", schema_type="TechArticle")
    client = _Client(app, backend)

    _, crawler = client.get("/guide", ua=GOOGLEBOT)
    assert '"@type": "TechArticle"' in crawler
    assert '"publisher"' in crawler
    assert "https://pypi.org/project/example" in crawler
    assert '"@type": "BreadcrumbList"' in crawler


@pytest.mark.parametrize("backend", _backends())
def test_per_page_card_overrides_the_site_default(backend):
    app = _build_app(backend)
    pkg.configure_seo(social_image="https://cdn.example/site.png")
    pkg.register_page_metadata("/guide", og_image="https://cdn.example/guide.png")
    client = _Client(app, backend)

    _, crawler = client.get("/guide", ua=GOOGLEBOT)
    assert "https://cdn.example/guide.png" in crawler
    assert "https://cdn.example/site.png" not in crawler


@pytest.mark.parametrize("backend", _backends())
def test_corpus_can_be_brought_under_the_training_block(backend):
    """P6 end to end: until 2.5 the documentation routes short-circuited
    before policy ran, so block_ai_training protected every surface EXCEPT
    the corpus — the one worth metering."""
    app = _build_app(backend)
    app._robots_config = pkg.RobotsConfig(block_ai_training=True, block_ai_training_docs=True)
    client = _Client(app, backend)

    for path in ("/llms.txt", "/llms-small.txt", "/llms-full.txt"):
        status, _ = client.get(path, ua=GPTBOT)
        assert status == 403, f"{path} returned {status}"

    # The policy channel is never gated: robots.txt is where the block is
    # announced, and a bot that receives 403 for it treats the site as
    # having no rules at all (RFC 9309).
    for path in ("/robots.txt", "/sitemap.xml"):
        status, _ = client.get(path, ua=GPTBOT)
        assert status == 200, f"{path} returned {status}"

    # Default posture is unchanged: the documents still serve.
    app._robots_config = pkg.RobotsConfig(block_ai_training=True)
    for path in ("/llms.txt", "/llms-small.txt", "/llms-full.txt"):
        status, _ = client.get(path, ua=GPTBOT)
        assert status == 200, f"{path} returned {status}"


# ---------------------------------------------------------------------------
# 2.7.0/G1 — geo across all three backends
# ---------------------------------------------------------------------------


class TestGeoAcrossAdapters:
    """The 451 must hold on every surface through every backend — the dict
    return shape means the adapters need zero changes, and this class is
    the proof."""

    @pytest.fixture(autouse=True)
    def _clean_geo(self):
        from dash_improve_my_llms import geo

        geo.reset()
        yield
        geo.reset()

    # Every surface class the package touches: page, doc family, policy
    # files, root icon path, asset, pages-router POST target.
    SWEEP = (
        "/",
        "/about",
        "/llms.txt",
        "/llms-small.txt",
        "/llms-full.txt",
        "/about/llms.txt",
        "/robots.txt",
        "/sitemap.xml",
        "/favicon.ico",
        "/assets/style.css",
    )

    def test_denied_country_gets_451_on_every_surface(self, backend):
        from dash_improve_my_llms import geo

        app = _build_app(backend)
        geo.configure_geo(deny_countries=["KP"])
        client = _Client(app, backend)

        for path in self.SWEEP:
            status, body, headers = client.get_full(path, extra_headers={"CF-IPCountry": "KP"})
            assert status == 451, f"{path} returned {status} on {backend}"
            assert "Unavailable For Legal Reasons" in body, path
            assert headers.get("cache-control") == "no-store", path

    def test_allowed_country_matches_unconfigured_statuses(self, backend):
        """The other half of the sweep: an allowed country's statuses are
        exactly what an unconfigured build serves."""
        from dash_improve_my_llms import geo

        app = _build_app(backend)
        client = _Client(app, backend)
        baseline = {p: client.get_full(p)[0] for p in self.SWEEP}

        geo.configure_geo(deny_countries=["KP"])
        for path in self.SWEEP:
            status, _, _ = client.get_full(path, extra_headers={"CF-IPCountry": "US"})
            assert status == baseline[path], f"{path} drifted on {backend}"

    def test_geo_unset_is_byte_identical(self, backend):
        """The standing release rule, asserted on bodies, not just
        statuses: with geo unconfigured, a request carrying a country
        header serves the same bytes as one without."""
        app = _build_app(backend)
        client = _Client(app, backend)

        for path in ("/", "/llms.txt", "/robots.txt", "/sitemap.xml"):
            _, plain, _ = client.get_full(path)
            _, with_country = client.get(path, extra_headers={"CF-IPCountry": "KP"})
            assert plain == with_country, f"{path} varied by country while unconfigured"
