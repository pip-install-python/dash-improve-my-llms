"""The operator policy panel (P1 of 2.7.0) — read-only, token-gated, 404-silent.

Reuses the adapter harness from test_adapters: a real pages app on the
Flask backend (one cross-backend gate check rides the parametrized
fixture there; the panel is backend-agnostic pure-string HTML, so the
content tests run once).
"""

from __future__ import annotations

import pytest

import dash_improve_my_llms as pkg
from dash_improve_my_llms import geo
from dash_improve_my_llms.robots_generator import RobotsConfig, generate_robots_txt

from test_adapters import _Client, _build_app, _normalize_shell  # noqa: E402 - the harness

TOKEN = "panel-secret-42"
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("DIMLL_PANEL_TOKEN", raising=False)
    geo.reset()
    yield
    geo.reset()


def _panel_app(**config_kwargs):
    config_kwargs.setdefault("panel", True)
    return _build_app("flask", **config_kwargs)


class TestPanelOff:
    def test_off_registers_nothing(self):
        """panel=False: the path behaves exactly as a build without the
        feature — whatever Dash's catch-all serves, byte-identical."""
        with_flag_off = _build_app("flask", panel=False)
        baseline = _build_app("flask")
        c1, c2 = _Client(with_flag_off, "flask"), _Client(baseline, "flask")
        s1, b1 = c1.get("/llms-policy")
        s2, b2 = c2.get("/llms-policy")
        assert s1 == s2
        assert _normalize_shell(b1) == _normalize_shell(b2)


class TestPanelGate:
    def test_no_token_configured_means_404_unconditionally(self):
        app = _panel_app()
        client = _Client(app, "flask")
        status, body = client.get("/llms-policy")
        assert status == 404
        status, body = client.get("/llms-policy?token=anything")
        assert status == 404

    def test_wrong_token_is_404_with_an_unrevealing_body(self, monkeypatch):
        monkeypatch.setenv("DIMLL_PANEL_TOKEN", TOKEN)
        app = _panel_app()
        client = _Client(app, "flask")
        status, body = client.get(f"/llms-policy?token={TOKEN}x")
        assert status == 404
        assert "panel" not in body.lower()
        assert "forbidden" not in body.lower()

    def test_env_token_is_read_per_request(self, monkeypatch):
        """Rotation without redeploy: the same running app honours the new
        value and kills the old one."""
        monkeypatch.setenv("DIMLL_PANEL_TOKEN", TOKEN)
        app = _panel_app()
        client = _Client(app, "flask")
        assert client.get(f"/llms-policy?token={TOKEN}")[0] == 200
        monkeypatch.setenv("DIMLL_PANEL_TOKEN", "rotated")
        assert client.get(f"/llms-policy?token={TOKEN}")[0] == 404
        assert client.get("/llms-policy?token=rotated")[0] == 200

    def test_config_token_beats_env(self, monkeypatch):
        monkeypatch.setenv("DIMLL_PANEL_TOKEN", "env-token")
        app = _panel_app(panel_token=TOKEN)
        client = _Client(app, "flask")
        assert client.get(f"/llms-policy?token={TOKEN}")[0] == 200
        assert client.get("/llms-policy?token=env-token")[0] == 404

    def test_header_transport_is_accepted(self, monkeypatch):
        monkeypatch.setenv("DIMLL_PANEL_TOKEN", TOKEN)
        app = _panel_app()
        client = _Client(app, "flask")
        status, _, headers = client.get_full(
            "/llms-policy", extra_headers={"X-LLMS-Panel-Token": TOKEN}
        )
        assert status == 200
        assert headers.get("cache-control") == "private, no-store"
        assert "noindex" in headers.get("x-robots-tag", "")


class TestPanelContent:
    def _get(self, monkeypatch, app=None, extra_headers=None):
        monkeypatch.setenv("DIMLL_PANEL_TOKEN", TOKEN)
        app = app or _panel_app()
        client = _Client(app, "flask")
        status, body, headers = client.get_full(
            f"/llms-policy?token={TOKEN}", extra_headers=extra_headers or {}
        )
        assert status == 200
        return app, body

    def test_all_sections_render(self, monkeypatch):
        _, body = self._get(monkeypatch)
        for anchor in (
            "Identity",
            "Vendor policy",
            "Tier documents",
            "Access control",
            "Geo guardrail",
            "Rate limiting",
            "Network",
        ):
            assert f"<h2>{anchor}</h2>" in body, anchor

    def test_vendor_table_agrees_with_robots_txt(self, monkeypatch):
        """The anti-drift assertion: for every vendor the panel shows, its
        effective policy matches the directive robots.txt emits."""
        import re

        app, body = self._get(monkeypatch)
        robots = generate_robots_txt(
            config=getattr(app, "_robots_config", None) or RobotsConfig(),
            sitemap_url="https://example.com/sitemap.xml",
            base_url="https://example.com",
        )
        rows = re.findall(
            r"<tr><td>([^<]+)</td><td>[^<]*</td><td>[^<]*</td>" r"<td class='policy-(\w+)'>", body
        )
        assert rows, "vendor table missing"
        for display, policy in rows:
            directive = {"allow": "Allow", "block": "Disallow"}.get(policy)
            if directive is None:
                continue  # meter renders Allow; covered by W2's tests
            # every robots token of the display'd vendor must carry the
            # matching directive — sample via the display name's first token
            if f"User-agent: {display}" in robots:
                assert f"User-agent: {display}\n{directive}: /" in robots, display

    def test_geo_section_shows_the_resolution_line(self, monkeypatch):
        geo.configure_geo(deny_countries=["KP"])
        _, body = self._get(monkeypatch, extra_headers={"CF-IPCountry": "DE"})
        assert "This request resolved to" in body
        assert "DE (via cf-ipcountry)" in body

    def test_access_callbacks_are_named_but_never_invoked(self, monkeypatch):
        """Invoking a request-scoped check outside its request is the exact
        failure access.py's docstring warns about."""
        from dash_improve_my_llms import access

        calls = []

        def landmine(path):
            calls.append(path)
            raise AssertionError("panel invoked the access check")

        access.configure_access(landmine)
        try:
            _, body = self._get(monkeypatch)
            assert "landmine" in body
            assert calls == []
        finally:
            access.reset()

    def test_never_displays_what_robots_never_names(self, monkeypatch):
        _, body = self._get(monkeypatch)
        assert "anthropic-ai" not in body
        assert "Claude-Web" not in body

    def test_copy_paste_hints_are_present(self, monkeypatch):
        _, body = self._get(monkeypatch)
        assert "configure_geo(deny_countries=" in body
        assert "vendor_policy" in body


class TestPanelInvisibility:
    def test_absent_from_every_generated_surface(self, monkeypatch):
        monkeypatch.setenv("DIMLL_PANEL_TOKEN", TOKEN)
        app = _panel_app()
        client = _Client(app, "flask")
        _, robots = client.get("/robots.txt")
        _, sitemap = client.get("/sitemap.xml")
        _, index = client.get("/llms.txt", ua="agent/1.0")
        for surface, name in ((robots, "robots"), (sitemap, "sitemap"), (index, "llms index")):
            assert "llms-policy" not in surface, f"panel leaked into {name}"


class TestPanelBlockedByGeo:
    def test_denied_country_gets_451_even_with_the_right_token(self, monkeypatch):
        """451 on everything includes the operator standing in a denied
        country — intended."""
        monkeypatch.setenv("DIMLL_PANEL_TOKEN", TOKEN)
        app = _panel_app()
        geo.configure_geo(deny_countries=["KP"])
        client = _Client(app, "flask")
        status, _, _ = client.get_full(
            f"/llms-policy?token={TOKEN}", extra_headers={"CF-IPCountry": "KP"}
        )
        assert status == 451
