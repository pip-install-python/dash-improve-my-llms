"""Per-request access control and viewer identity.

These cover the half of the package an application can break silently: a gate
that only covers some surfaces is not a gate, and the missing surface is
invisible until someone reads the wrong body.

Unit tests for the resolver live at the top; the end of the file drives real
requests through the Flask adapter, because "the handler returns the gate
document" and "the route serves the gate document with headers nothing will
cache" are different claims.
"""

from __future__ import annotations

import pytest

import dash_improve_my_llms as pkg
from dash_improve_my_llms import access


@pytest.fixture(autouse=True)
def _clean_access():
    """Every test starts with no access control configured."""
    access.reset()
    yield
    access.reset()


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------


def test_unconfigured_is_a_no_op():
    """The property that makes this safe to land mid-rollout."""
    assert access.resolve("/anything") == access.ALLOW
    assert access.is_listable("/anything") is True
    assert access.is_restricted() is False
    assert access.link_suffix() == ""
    assert access.viewer_identity() is None


def test_mark_hidden_still_wins():
    access.configure_access(lambda path: "allow")
    assert access.resolve("/admin", {"/admin"}) == access.DENY


def test_three_verdicts_are_passed_through():
    access.configure_access(lambda path: {"/a": "allow", "/g": "gated", "/d": "deny"}[path])
    assert access.resolve("/a") == access.ALLOW
    assert access.resolve("/g") == access.GATED
    assert access.resolve("/d") == access.DENY


def test_gated_stays_listable_and_denied_does_not():
    """A gated URL is public knowledge; only its content is restricted."""
    access.configure_access(lambda path: "gated" if path == "/g" else "deny")
    assert access.is_listable("/g") is True
    assert access.is_listable("/d") is False


def test_a_raising_check_degrades_to_gated(caplog):
    """Not allow (a bug would publish), not deny (a bug would 404 the site)."""

    def boom(path):
        raise RuntimeError("boom")

    access.configure_access(boom)
    assert access.resolve("/x") == access.GATED
    assert access.is_listable("/x") is True


def test_a_nonsense_verdict_degrades_to_gated():
    access.configure_access(lambda path: "banana")
    assert access.resolve("/x") == access.GATED


def test_a_broken_check_warns_once_per_path(caplog):
    """A crawler must not be able to fill the log by hammering one URL."""

    def boom(path):
        raise RuntimeError("boom")

    access.configure_access(boom)
    with caplog.at_level("WARNING"):
        for _ in range(5):
            access.resolve("/x")
    assert sum("access check raised" in r.message for r in caplog.records) == 1


# ---------------------------------------------------------------------------
# The gate document
# ---------------------------------------------------------------------------


def test_gate_document_prefers_the_application_copy():
    access.configure_access(lambda p: "gated", gate_doc=lambda p: f"# custom {p}")
    assert access.gate_document("/g") == "# custom /g"


def test_gate_document_falls_back_when_the_app_raises():
    def boom(path):
        raise RuntimeError("nope")

    access.configure_access(lambda p: "gated", gate_doc=boom)
    body = access.gate_document("/g", {"/g": {"name": "Guide", "description": "How to."}})
    assert "# Guide" in body and "How to." in body


def test_gate_document_falls_back_when_the_app_returns_nothing():
    access.configure_access(lambda p: "gated", gate_doc=lambda p: "   ")
    assert "# Guide" in access.gate_document("/g", {"/g": {"name": "Guide"}})


# ---------------------------------------------------------------------------
# link_suffix / decoration
# ---------------------------------------------------------------------------


def test_decorate_appends_and_respects_an_existing_query():
    access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
    assert access.decorate("https://h/llms.txt") == "https://h/llms.txt?key=K1"
    assert access.decorate("https://h/a?x=1") == "https://h/a?x=1&key=K1"


def test_link_suffix_tolerates_a_leading_question_mark():
    access.configure_access(lambda p: "allow", link_suffix=lambda: "?key=K1")
    assert access.link_suffix() == "?key=K1"


def test_a_raising_link_suffix_is_silently_empty():
    def boom():
        raise RuntimeError("boom")

    access.configure_access(lambda p: "allow", link_suffix=boom)
    assert access.link_suffix() == ""
    assert access.decorate("https://h/llms.txt") == "https://h/llms.txt"


def test_decorate_body_carries_authority_across_same_origin_documents():
    access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
    body = "- doc: https://example.com/guide/llms.txt\n- rel: /other/llms.txt"
    out = access.decorate_body(body, "https://example.com")
    assert "https://example.com/guide/llms.txt?key=K1" in out
    assert "/other/llms.txt?key=K1" in out


def test_decorate_body_never_leaks_the_key_to_another_host():
    """Regression: the relative pattern used to match the `//host/llms.txt`
    tail of an absolute URL, because `//` after `https:` reads as a path start —
    so a peer in the network directory was handed this site's capability."""
    access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
    body = (
        "- peer: https://leaflet.example.net/llms.txt\n"
        "- third party: https://www.dash-mantine-components.com/llms.txt"
    )
    assert access.decorate_body(body, "https://example.com") == body


def test_decorate_body_leaves_pages_and_existing_queries_alone():
    access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
    body = "- page: https://example.com/guide\n- raw: https://example.com/a/llms.txt?raw=1"
    assert access.decorate_body(body, "https://example.com") == body


def test_decorate_body_is_a_no_op_without_authority():
    access.configure_access(lambda p: "allow")
    body = "- doc: https://example.com/guide/llms.txt"
    assert access.decorate_body(body, "https://example.com") == body


# ---------------------------------------------------------------------------
# Viewer identity
# ---------------------------------------------------------------------------


def test_identity_is_none_until_configured():
    assert access.viewer_identity() is None


def test_identity_is_normalised_and_capped():
    access.configure_viewer_identity(lambda: {"name": "x" * 500, "since": "y" * 500, "plan": "pro"})
    identity = access.viewer_identity()
    assert len(identity["name"]) == 120
    assert len(identity["since"]) == 60
    assert identity["plan"] == "pro"


def test_identity_without_a_name_is_nothing():
    access.configure_viewer_identity(lambda: {"since": "now"})
    assert access.viewer_identity() is None


def test_a_raising_identity_provider_renders_nothing():
    def boom():
        raise RuntimeError("boom")

    access.configure_viewer_identity(boom)
    assert access.viewer_identity() is None


def test_identity_makes_a_response_unshareable():
    assert access.is_restricted() is False
    access.configure_viewer_identity(lambda: {"name": "pip@example.com"})
    assert access.is_restricted() is True
    headers = access.private_headers()
    assert headers["Cache-Control"] == "private, no-store"
    assert "Cookie" in headers["Vary"]
    assert headers["X-Robots-Tag"] == "noindex"


# ---------------------------------------------------------------------------
# Through a real Flask app — the surfaces, and the headers
# ---------------------------------------------------------------------------


def _app():
    """A pages app with one open page and one the application will gate."""
    import dash
    from dash import Dash, html

    pkg._state.page_metadata.clear()
    pkg._state.hidden_pages.clear()
    pkg._state.network = pkg.NetworkConfig()
    if hasattr(dash, "page_registry"):
        dash.page_registry.clear()
    if hasattr(dash, "_pages") and hasattr(dash._pages, "PAGE_REGISTRY"):
        dash._pages.PAGE_REGISTRY.clear()

    app = Dash(__name__, use_pages=True, pages_folder="")
    app.title = "Test App"
    app._base_url = "https://example.com"
    dash.register_page("home", path="/", name="Home", layout=html.Div("home"))
    dash.register_page("guide", path="/guide", name="Guide", layout=html.Div("guide"))
    pkg.register_page_metadata(
        "/", name="Home", description="Landing.", llms_doc="# Home\n\nWelcome."
    )
    pkg.register_page_metadata(
        "/guide", name="Guide", description="How to.", llms_doc="# Guide\n\nSECRETPROSE here."
    )
    app.layout = html.Div([dash.page_container])
    pkg.add_llms_routes(app, pkg.LLMSConfig(warn_missing_llms_doc=False))
    return app


GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def test_gated_page_withholds_prose_on_every_surface():
    app = _app()
    access.configure_access(
        lambda p: "gated" if p == "/guide" else "allow",
        gate_doc=lambda p: "# Gated\n\nAsk for access.",
    )
    client = app.server.test_client()

    doc = client.get("/guide/llms.txt")
    assert doc.status_code == 200
    assert "SECRETPROSE" not in doc.get_data(as_text=True)
    assert "Ask for access" in doc.get_data(as_text=True)

    crawler = client.get("/guide", headers={"User-Agent": GOOGLEBOT})
    assert "SECRETPROSE" not in crawler.get_data(as_text=True)

    # Still listed: the URL is public even though the content is not.
    assert "/guide" in client.get("/sitemap.xml").get_data(as_text=True)
    assert "/guide" in client.get("/llms.txt").get_data(as_text=True)


def test_denied_page_is_404_and_delisted_everywhere():
    app = _app()
    access.configure_access(lambda p: "deny" if p == "/guide" else "allow")
    client = app.server.test_client()

    assert client.get("/guide/llms.txt").status_code == 404
    assert client.get("/guide", headers={"User-Agent": GOOGLEBOT}).status_code == 404
    assert "/guide" not in client.get("/sitemap.xml").get_data(as_text=True)
    assert "/guide" not in client.get("/llms.txt").get_data(as_text=True)


def test_authority_bearing_responses_are_never_shared_cached():
    app = _app()
    access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
    client = app.server.test_client()

    r = client.get("/guide/llms.txt")
    headers = {k.lower(): v for k, v in dict(r.headers).items()}
    assert headers["cache-control"] == "private, no-store"
    assert headers["x-robots-tag"] == "noindex"


def test_ordinary_responses_stay_cacheable():
    app = _app()
    client = app.server.test_client()
    headers = {k.lower(): v for k, v in dict(client.get("/guide/llms.txt").headers).items()}
    assert headers.get("vary") == "Accept"
    assert "cache-control" not in headers


def test_identity_renders_in_html_only():
    app = _app()
    access.configure_viewer_identity(
        lambda: {"name": "pip@example.com", "since": "09:15 UTC", "plan": "pro"}
    )
    client = app.server.test_client()

    html = client.get(
        "/guide/llms.txt",
        headers={
            "Accept": "text/html",
            "User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        },
    ).get_data(as_text=True)
    assert "pip@example.com" in html
    assert "session since" in html

    markdown = client.get("/guide/llms.txt").get_data(as_text=True)
    assert "pip@example.com" not in markdown
    assert "dv-banner" not in markdown
