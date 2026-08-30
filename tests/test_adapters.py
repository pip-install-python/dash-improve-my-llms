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


def _normalize_shell(body: str) -> str:
    """Strip dash's per-request nonce before byte comparison.

    Dash 4.4.1's index embeds a fresh `"end_id":"<random>~<hash>"` on every
    request, so two consecutive fetches of the SAME url differ by design.
    Tests asserting "this knob changes nothing" must compare everything
    EXCEPT that nonce — comparing raw bytes passes on <=4.4.0 and fails on
    4.4.1 for reasons unrelated to the knob under test (CD run #14's
    matrix failure, 2026-08-23).
    """
    import re

    return re.sub(r'"end_id":"[^"]*"', '"end_id":"NORMALIZED"', body)


def _lower(headers) -> dict:
    """Lowercase header keys — the three backends disagree on casing."""
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


def _package_claimed_paths(app, backend: str) -> set:
    """The root-icon paths THIS package registered, not the app or Dash.

    `add_llms_routes` deliberately skips any icon path something else
    already claimed, so a test that asserted on all of ROOT_ICON_PATHS
    would be asserting on Dash's routes half the time.
    """
    server = app.server
    if backend == "fastapi":
        return {
            getattr(route, "path", None)
            for route in server.routes
            if getattr(getattr(route, "endpoint", None), "__name__", "") == "_root_icon"
        }
    return {
        str(rule.rule)
        for rule in server.url_map.iter_rules()
        if rule.endpoint.startswith("_dimll_icon")
    }


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
        """(status, body, headers) — headers matter for content negotiation."""
        return self.request("GET", path, ua=ua, accept=accept, extra_headers=extra_headers)

    def head_full(
        self, path: str, ua: str = BROWSER, accept: str = "*/*", extra_headers: dict = None
    ):
        """(status, body, headers) for a HEAD — see TestHeadParity."""
        return self.request("HEAD", path, ua=ua, accept=accept, extra_headers=extra_headers)

    def request(
        self,
        method: str,
        path: str,
        ua: str = BROWSER,
        accept: str = "*/*",
        extra_headers: dict = None,
    ):
        """(status, body, headers) for any method.

        Redirects are never followed: Starlette's client follows them by
        default and Flask's does not, so a test asserting on a 302 would pass
        on one backend and fail on another for reasons unrelated to the code
        under test.
        """
        headers = {"User-Agent": ua, "Accept": accept, **(extra_headers or {})}

        if self.backend == "fastapi":
            response = self._client.request(method, path, headers=headers, follow_redirects=False)
            return response.status_code, response.text, _lower(response.headers)

        if self.backend == "quart":
            import asyncio

            async def _run():
                response = await self._client.open(path, method=method, headers=headers)
                return (
                    response.status_code,
                    await response.get_data(as_text=True),
                    _lower(response.headers),
                )

            return asyncio.get_event_loop().run_until_complete(_run())

        response = self._client.open(path, method=method, headers=headers)
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
    for a site that never declared one.

    `twitter:url` is the one exception, and it is not an identity tag: the
    document's own URL is known without any configuration at all, and the
    card set (`twitter:card`, `:title`, `:image`, …) still appears only
    when a social image is declared."""
    app = _build_app(backend)
    client = _Client(app, backend)

    _, crawler = client.get("/guide", ua=GOOGLEBOT)
    assert 'rel="icon"' not in crawler
    assert "og:image" not in crawler
    for tag in ("twitter:card", "twitter:title", "twitter:description", "twitter:image"):
        assert tag not in crawler
    assert '<meta name="twitter:url"' in crawler


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
            assert _normalize_shell(plain) == _normalize_shell(
                with_country
            ), f"{path} varied by country while unconfigured"


class TestCrawlerLaneH1:
    """Re-soak #5's lane lesson: a crawler fetch never sees the prerender
    block, so a prerender-side pin alone cannot guard the document bots
    receive. This is the end-to-end pin on the CRAWLER lane."""

    def test_the_served_crawler_document_has_exactly_one_h1(self, backend):
        app = _build_app(backend)
        client = _Client(app, backend)
        # /guide's llms_doc opens with its own markdown H1 (see _build_app)
        status, body = client.get("/guide", ua="Mozilla/5.0 (compatible; Googlebot/2.1)")
        assert status == 200
        assert body.count("<h1") == 1, "the crawler lane serves duplicate h1s"


class TestHeadParity:
    """B7: every crawler-facing route answers HEAD, on every backend.

    Through 2.7.1 the FastAPI adapter registered all of its routes with
    `@router.get(...)`. Starlette answers an undeclared method with 405,
    while Werkzeug (Flask, and Quart by descent) derives HEAD from every
    GET automatically — so `HEAD /llms.txt` returned 200 on a Flask host
    and 405 on an ASGI one, from the same package version. Monitors and
    preflighting crawlers got the 405.

    On the body: this asserts status and content-type parity but stops
    short of requiring an empty body at the client, because the three
    stacks discard it at three different layers and none of those layers
    is ours. Werkzeug empties it in the response (`wrappers/response.py`,
    `get_app_iter`), so Flask's client sees b"". Starlette emits it and
    httpx's ASGI transport drops it (`httpx/_transports/asgi.py`), so the
    FastAPI client also sees b"". Quart emits it and nothing in the test
    path removes it, so Quart's client sees the whole document — while
    the wire does not, because every ASGI server suppresses a HEAD body
    (`hypercorn/protocol/http_stream.py`, `suppress_body`; uvicorn's
    `h11_impl.py` sends `b"" if method == "HEAD"`). Measured on hypercorn's real H11Protocol, HEAD
    /llms.txt is 200 with zero body bytes. Forcing the clients to agree
    would mean stripping bodies inside two adapters purely to satisfy
    this assertion; the disjunction below still catches a truncated or
    substituted body, which is the failure worth catching.
    """

    SWEEP = (
        "/llms.txt",
        "/guide/llms.txt",
        "/llms-small.txt",
        "/llms-full.txt",
        "/robots.txt",
        "/sitemap.xml",
    )

    def test_head_is_never_method_not_allowed(self, client):
        """The regression itself, stated as bluntly as it happened."""
        for path in self.SWEEP:
            status, _, _ = client.head_full(path)
            assert status != 405, f"HEAD {path} is 405 on {client.backend}"

    def test_head_matches_get_status_and_content_type(self, client):
        for path in self.SWEEP:
            get_status, _, get_headers = client.get_full(path)
            head_status, _, head_headers = client.head_full(path)

            assert head_status == get_status, (
                f"HEAD {path} returned {head_status}, GET returned {get_status} "
                f"on {client.backend}"
            )
            assert head_headers.get("content-type") == get_headers.get("content-type"), (
                f"HEAD {path} content-type {head_headers.get('content-type')!r} != "
                f"GET {get_headers.get('content-type')!r} on {client.backend}"
            )

    def test_head_body_is_empty_or_the_get_body(self, client):
        """Never a truncated or substituted body — see the class docstring
        for why this is a disjunction rather than `== ""`."""
        for path in self.SWEEP:
            _, get_body, _ = client.get_full(path)
            _, head_body, _ = client.head_full(path)
            assert head_body in ("", get_body), f"HEAD {path} served a third body"

    def test_head_reaches_the_panel_route(self, backend):
        """The panel is registered on a separate config branch, so the
        sweep above never touches it."""
        app = _build_app(backend, panel=True, panel_token="s3cret")
        client = _Client(app, backend)

        get_status, _, get_headers = client.get_full("/llms-policy?token=s3cret")
        head_status, _, head_headers = client.head_full("/llms-policy?token=s3cret")

        assert get_status == 200
        assert head_status == get_status, f"HEAD on the panel is {head_status} on {backend}"
        assert head_headers.get("content-type") == get_headers.get("content-type")

    def test_head_reaches_the_root_icon_routes(self, backend):
        """These already declared HEAD before B7 — this pins that they keep
        it while the other routes are being changed around them."""
        from dash_improve_my_llms.seo import ROOT_ICON_PATHS

        app = _build_app(backend)
        client = _Client(app, backend)
        claimed = _package_claimed_paths(app, backend)

        for path in ROOT_ICON_PATHS:
            if path not in claimed:
                continue  # the app, or Dash, owns this path — not ours to assert on
            get_status, _, _ = client.get_full(path)
            head_status, _, _ = client.head_full(path)
            assert head_status == get_status, f"HEAD {path} is {head_status} on {backend}"


# ---------------------------------------------------------------------------
# 2.8 item 3 — Vary: User-Agent
# ---------------------------------------------------------------------------


class TestVaryHeader:
    """The same URL answers a browser and a crawler with different bytes.

    Through 2.7.x the package told no cache so: `_doc_headers()` emitted
    `Vary: Accept` alone, and the page routes emitted nothing at all. It
    went unnoticed only because the edge in front of these hosts marked
    every document response DYNAMIC; a shared cache that did not would
    hand a crawler the document built for a browser, or the reverse.
    """

    @pytest.mark.parametrize("path", ["/", "/llms.txt", "/guide/llms.txt", "/llms-full.txt"])
    def test_vary_names_both_accept_and_user_agent(self, client, path):
        _, _, headers = client.get_full(path, ua=BROWSER)
        vary = {token.strip().lower() for token in headers.get("vary", "").split(",")}
        assert "accept" in vary, f"{path} lost Vary: Accept"
        assert "user-agent" in vary, f"{path} does not declare the UA split"

    def test_the_crawler_document_declares_it_too(self, client):
        """The response that IS the split has the most to say about it."""
        _, _, headers = client.get_full("/guide", ua=GOOGLEBOT)
        vary = {token.strip().lower() for token in headers.get("vary", "").split(",")}
        assert {"accept", "user-agent"} <= vary

    def test_it_does_not_clobber_tokens_the_backend_already_set(self, client):
        """Dash and the backends put their own tokens there."""
        from dash_improve_my_llms.handlers import merge_vary

        assert merge_vary("Accept-Encoding", "Accept", "User-Agent") == (
            "Accept-Encoding, Accept, User-Agent"
        )
        assert merge_vary("accept", "Accept", "User-Agent") == "accept, User-Agent"
        assert merge_vary("", "Accept", "User-Agent") == "Accept, User-Agent"


# ---------------------------------------------------------------------------
# 2.8 item 5 — one read event per document response, on every adapter
# ---------------------------------------------------------------------------


class TestReadEvents:
    """Exactly one event per response, with the fields actually filled in.

    Asserting mere presence would pass against a stub, so the tier, lane,
    verdict and byte count are all checked against the response they
    describe — `bytes` in particular, because a ledger that reports the
    wrong size is worse than one that reports nothing.
    """

    SWEEP = [
        ("/llms.txt", "index"),
        ("/guide/llms.txt", "page"),
        ("/llms-small.txt", "small"),
        ("/llms-full.txt", "full"),
        ("/robots.txt", "policy"),
        ("/sitemap.xml", "sitemap"),
    ]

    @pytest.fixture
    def recorded(self):
        from dash_improve_my_llms import _ledger

        _ledger.reset()
        events = []
        _ledger.on_document_read(events.append)
        yield events
        _ledger.reset()

    @pytest.mark.parametrize("path,tier", SWEEP)
    def test_one_event_per_document_response(self, client, recorded, path, tier):
        status, body, _ = client.get_full(path, ua=GPTBOT)
        assert status == 200
        assert len(recorded) == 1, f"{path} emitted {len(recorded)} events, expected 1"
        event = recorded[0]
        assert event["tier"] == tier
        assert event["verdict"] == "served"
        assert event["status"] == 200
        assert event["vendor_key"] == "gptbot"
        assert event["bot_type"] == "training"
        assert event["lane"] == "crawler"
        assert event["bytes"] == len(body.encode("utf-8"))

    def test_the_crawler_html_lane_emits_html(self, client, recorded):
        status, body, _ = client.get_full("/guide", ua=GOOGLEBOT)
        assert status == 200
        assert len(recorded) == 1
        event = recorded[0]
        assert event["tier"] == "html"
        assert event["lane"] == "crawler"
        assert event["verdict"] == "served"
        assert event["vendor_key"] == "googlebot"
        assert event["bytes"] == len(body.encode("utf-8"))

    def test_an_absent_user_agent_on_the_root_is_recorded_as_a_machine(self, client, recorded):
        """2.8 item 2's new lane has to reach the ledger too."""
        status, _, _ = client.get_full("/", ua="")
        assert status == 200
        assert len(recorded) == 1
        assert recorded[0]["lane"] == "crawler"
        assert recorded[0]["bot_type"] == "unknown"
        assert recorded[0]["vendor_key"] is None

    def test_a_browser_page_view_is_not_a_document_read(self, client, recorded):
        """The prerendered shell is the application answering, not us."""
        status, _, _ = client.get_full("/guide", ua=BROWSER)
        assert status == 200
        assert recorded == []

    def test_a_blocked_crawler_is_recorded_as_blocked(self, backend, recorded):
        app = _build_app(backend)
        app._robots_config = pkg.RobotsConfig(block_ai_training=True)
        status, _, _ = _Client(app, backend).get_full("/guide", ua=GPTBOT)
        assert status == 403
        assert len(recorded) == 1
        assert recorded[0]["verdict"] == "blocked"
        assert recorded[0]["status"] == 403
        assert recorded[0]["vendor_key"] == "gptbot"

    def test_a_rate_limited_crawler_is_recorded_as_rate_limited(self, backend, recorded):
        from dash_improve_my_llms import _rate_limit

        _rate_limit.reset()
        app = _build_app(backend, rate_limit_per_minute=1)
        client = _Client(app, backend)
        assert client.get_full("/llms-full.txt", ua=GPTBOT)[0] == 200
        status, _, _ = client.get_full("/llms-full.txt", ua=GPTBOT)
        assert status == 429
        assert recorded[-1]["verdict"] == "rate_limited"
        assert recorded[-1]["status"] == 429
        _rate_limit.reset()

    # ---------------------------------------------------------------
    # 2.9.0 item 1 — the resolved posture on every row
    # ---------------------------------------------------------------

    @pytest.mark.parametrize("path,tier", SWEEP)
    def test_every_document_event_names_a_policy(self, client, recorded, path, tier):
        """The invariant. Through 2.8.x `policy` started life as None and
        became a string only for a registry vendor on a host that had a
        RobotsConfig — and the adapters, which serve these six documents,
        passed no policy at all. So a ledger rolling up by
        (vendor, verified, policy) had None on every row of a default
        host and could not say what posture a read was served under."""
        assert client.get_full(path, ua=GPTBOT)[0] == 200
        assert len(recorded) == 1
        assert recorded[0]["policy"] in ("allow", "meter", "block")

    def test_the_crawler_html_event_names_a_policy(self, client, recorded):
        """The middleware's own lane, not an adapter route."""
        assert client.get_full("/guide", ua=GOOGLEBOT)[0] == 200
        assert recorded[0]["policy"] == "allow"

    def test_a_default_host_serving_googlebot_records_allow(self, backend, recorded):
        app = _build_app(backend)
        app._robots_config = pkg.RobotsConfig()
        assert _Client(app, backend).get_full("/guide", ua=GOOGLEBOT)[0] == 200
        assert recorded[0]["policy"] == "allow"

    def test_a_blocked_vendor_records_block_on_its_403(self, backend, recorded):
        app = _build_app(backend)
        app._robots_config = pkg.RobotsConfig(block_ai_training=True)
        assert _Client(app, backend).get_full("/guide", ua=GPTBOT)[0] == 403
        assert recorded[0]["verdict"] == "blocked"
        assert recorded[0]["policy"] == "block"

    def test_a_metered_vendor_records_meter(self, backend, recorded):
        app = _build_app(backend)
        app._robots_config = pkg.RobotsConfig(vendor_policy={"gptbot": "meter"})
        assert _Client(app, backend).get_full("/guide", ua=GPTBOT)[0] == 200
        assert recorded[0]["policy"] == "meter"

    def test_an_absent_user_agent_records_the_unknown_ai_posture(self, backend, recorded):
        """2.8 moved the unidentified onto the crawler lane; 2.9.0 lets
        `default_unknown_ai` govern them. An unnamed agent IS the unknown
        AI the knob names."""
        app = _build_app(backend)
        app._robots_config = pkg.RobotsConfig(default_unknown_ai="meter")
        assert _Client(app, backend).get_full("/", ua="")[0] == 200
        assert recorded[0]["bot_type"] == "unknown"
        assert recorded[0]["policy"] == "meter"

    def test_a_cli_tool_is_exempt_from_the_unknown_ai_posture(self, backend, recorded):
        """curl is the paste-into-chat lane, not an unenumerated crawler:
        metering a person's terminal is not what the knob is for."""
        app = _build_app(backend)
        app._robots_config = pkg.RobotsConfig(default_unknown_ai="meter")
        assert _Client(app, backend).get_full("/", ua="curl/8.4.0")[0] == 200
        assert recorded[0]["policy"] == "allow"

    def test_a_host_with_no_robots_config_records_allow(self, backend, recorded):
        """The document went out; None never described that."""
        app = _build_app(backend)
        assert getattr(app, "_robots_config", None) is None
        assert _Client(app, backend).get_full("/llms.txt", ua=GPTBOT)[0] == 200
        assert recorded[0]["policy"] == "allow"

    def test_a_monitor_is_named_and_allowed(self, backend, recorded):
        """2.9.0 item 3 on the wire: a health check reads as `monitor`,
        carries a vendor key, and is never blocked."""
        app = _build_app(backend)
        app._robots_config = pkg.RobotsConfig(block_ai_training=True, allow_traditional=False)
        pingdom = "Pingdom.com_bot_version_1.4_(http://www.pingdom.com/)"
        assert _Client(app, backend).get_full("/guide", ua=pingdom)[0] == 200
        assert recorded[0]["bot_type"] == "monitor"
        assert recorded[0]["vendor_key"] == "pingdom"
        assert recorded[0]["policy"] == "allow"

    # ---------------------------------------------------------------
    # 2.9.2 — the vendor's class reaches the row
    # ---------------------------------------------------------------

    @pytest.mark.parametrize(
        "ua,vendor_class",
        [
            (GPTBOT, "training"),
            (GOOGLEBOT, "traditional"),
            ("Pingdom.com_bot_version_1.4_(http://www.pingdom.com/)", "monitor"),
            ("Claude-User/1.0", "search"),
            ("curl/8.4.0", None),
            ("", None),
        ],
    )
    def test_every_event_carries_the_vendor_class(self, backend, recorded, ua, vendor_class):
        """`classify()` computed it and `build_event` held it, but it was
        never put in the event — so a consumer storing
        `{k: event[k] for k in EVENT_FIELDS}` dropped the class at the app
        boundary on every host, and every rollup's per-vendor class was
        null. None where no vendor matched: a generic `bot` token gives a
        bot_type without saying whose."""
        from dash_improve_my_llms.bot_detection import classify

        app = _build_app(backend)
        assert _Client(app, backend).get_full("/llms.txt", ua=ua)[0] == 200
        assert len(recorded) == 1
        assert recorded[0]["vendor_class"] == vendor_class
        assert recorded[0]["vendor_class"] == classify(ua)["vendor_class"]

    def test_the_class_rides_the_middleware_lane_too(self, backend, recorded):
        """Not only the adapter routes — the crawler-HTML branch emits its
        own event and must carry the same field."""
        app = _build_app(backend)
        assert _Client(app, backend).get_full("/guide", ua=GOOGLEBOT)[0] == 200
        assert recorded[0]["tier"] == "html"
        assert recorded[0]["vendor_class"] == "traditional"

    def test_the_class_is_present_on_a_blocked_event(self, backend, recorded):
        app = _build_app(backend)
        app._robots_config = pkg.RobotsConfig(block_ai_training=True)
        assert _Client(app, backend).get_full("/guide", ua=GPTBOT)[0] == 403
        assert recorded[0]["vendor_class"] == "training"
        assert recorded[0]["policy"] == "block"

    def test_a_raising_callback_leaves_the_response_untouched(self, client):
        from dash_improve_my_llms import _ledger

        _ledger.reset()
        _ledger.on_document_read(lambda event: (_ for _ in ()).throw(RuntimeError("broken")))
        try:
            with pytest.warns(RuntimeWarning):
                status, body, _ = client.get_full("/llms.txt", ua=GPTBOT)
            assert status == 200
            assert "# Test App" in body
        finally:
            _ledger.reset()

    def test_with_no_listener_the_routes_are_unchanged(self, client):
        from dash_improve_my_llms import _ledger

        _ledger.reset()
        assert _ledger.has_listeners() is False
        for path, _tier in self.SWEEP:
            assert client.get_full(path, ua=GPTBOT)[0] == 200
