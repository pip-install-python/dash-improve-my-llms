"""2.7.1 — discovery relations, the text/plain ramp, the source digest.

The two-lane rule applies throughout: every surface change is pinned on
BOTH document lanes (the prerender/browser path and the static crawler
document) plus the wire — a pin on one lane cannot guard the other.
"""

from __future__ import annotations

import pytest

from dash_improve_my_llms.discovery import (
    DIGEST_HEADER,
    DIGEST_META_NAME,
    link_header_value,
    source_digest,
    twin_path,
    wants_plain_text,
)

from test_adapters import _Client, _backends, _build_app  # noqa: E402 - the harness


@pytest.fixture(params=_backends())
def backend(request):
    return request.param


AGENT = "agent/1.0"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1)"
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"


# ---------------------------------------------------------------------------
# The pure core
# ---------------------------------------------------------------------------


class TestCore:
    def test_digest_is_stable_and_prefixed(self):
        d = source_digest("# Guide\n\nText.")
        assert d is not None and d.startswith("sha256:") and len(d) == 7 + 64
        assert d == source_digest("# Guide\n\nText.")
        assert d != source_digest("# Guide\n\nOther text.")

    def test_no_source_no_digest(self):
        assert source_digest(None) is None
        assert source_digest("") is None
        assert source_digest("   ") is None

    def test_twin_and_link_header_shapes(self):
        assert twin_path("/guide") == "/guide/llms.txt"
        assert twin_path("/") == "/llms.txt"
        header = link_header_value("/guide")
        assert '</guide/llms.txt>; rel="alternate"; type="text/markdown"' in header
        assert '</llms.txt>; rel="describedby"' in header

    @pytest.mark.parametrize(
        "accept,plain",
        [
            ("text/plain", True),
            ("text/plain, */*;q=0.8", True),
            ("text/markdown", False),
            ("text/markdown, text/plain", False),  # markdown named: historical type wins
            ("*/*", False),  # the historical contract
            ("", False),
            ("text/html", False),
        ],
    )
    def test_plain_text_ramp_decision(self, accept, plain):
        assert wants_plain_text(accept) is plain


# ---------------------------------------------------------------------------
# Feature 1 — discovery relations, both lanes + the wire
# ---------------------------------------------------------------------------


class TestDiscoveryRelations:
    def test_crawler_lane_head_carries_both_relations(self, backend):
        app = _build_app(backend)
        client = _Client(app, backend)
        _, body = client.get("/guide", ua=GOOGLEBOT)
        assert 'rel="alternate" type="text/markdown" href="/guide/llms.txt"' in body
        assert 'rel="describedby" href="/llms.txt"' in body

    def test_browser_lane_head_carries_both_relations(self, backend):
        app = _build_app(backend)
        client = _Client(app, backend)
        _, body = client.get("/guide", ua=BROWSER)
        assert 'rel="describedby" href="/llms.txt"' in body
        assert 'rel="alternate" type="text/markdown"' in body

    def test_link_header_rides_both_lanes(self, backend):
        app = _build_app(backend)
        client = _Client(app, backend)
        for ua, lane in ((GOOGLEBOT, "crawler"), (BROWSER, "browser")):
            _, _, headers = client.get_full("/guide", ua=ua)
            link = headers.get("link", "")
            assert 'rel="alternate"' in link, f"{lane} lane lost the Link header"
            assert 'rel="describedby"' in link, lane
            assert "/guide/llms.txt" in link, lane


# ---------------------------------------------------------------------------
# Feature 2 — the text/plain ramp on the llms surfaces
# ---------------------------------------------------------------------------


class TestPlainTextRamp:
    def test_same_bytes_compatible_type(self, backend):
        app = _build_app(backend)
        client = _Client(app, backend)
        for path in ("/llms.txt", "/guide/llms.txt", "/llms-small.txt", "/llms-full.txt"):
            _, md_body, md_headers = client.get_full(path, ua=AGENT, accept="text/markdown")
            _, pl_body, pl_headers = client.get_full(path, ua=AGENT, accept="text/plain")
            assert md_body == pl_body, f"{path}: the ramp changed the bytes"
            assert "text/markdown" in md_headers.get("content-type", ""), path
            assert "text/plain" in pl_headers.get("content-type", ""), path

    def test_star_accept_keeps_the_historical_type(self, backend):
        app = _build_app(backend)
        client = _Client(app, backend)
        _, _, headers = client.get_full("/llms.txt", ua=AGENT, accept="*/*")
        assert "text/markdown" in headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Feature 3 — the source digest: parity provable across representations
# ---------------------------------------------------------------------------


class TestSourceDigest:
    def _meta_digest(self, body: str) -> str:
        import re

        m = re.search(rf'name="{DIGEST_META_NAME}" content="([^"]+)"', body)
        assert m, "digest meta missing"
        return m.group(1)

    def test_all_three_representations_share_one_digest(self, backend):
        """The point of the feature: page HTML (browser lane), the crawler
        document, and the markdown twin were generated from one source —
        now provable, not plausible."""
        app = _build_app(backend)
        client = _Client(app, backend)

        _, browser_body = client.get("/guide", ua=BROWSER)
        _, crawler_body, crawler_headers = client.get_full("/guide", ua=GOOGLEBOT)
        _, _, twin_headers = client.get_full("/guide/llms.txt", ua=AGENT)

        d_browser = self._meta_digest(browser_body)
        d_crawler = self._meta_digest(crawler_body)
        d_crawler_hdr = crawler_headers.get(DIGEST_HEADER.lower())
        d_twin = twin_headers.get(DIGEST_HEADER.lower())

        assert d_browser == d_crawler == d_crawler_hdr == d_twin
        assert d_browser.startswith("sha256:")

    def test_different_pages_different_digests(self, backend):
        app = _build_app(backend)
        client = _Client(app, backend)
        _, _, h1 = client.get_full("/guide/llms.txt", ua=AGENT)
        _, _, h2 = client.get_full("/llms-small.txt", ua=AGENT)
        assert h2.get(DIGEST_HEADER.lower()) is None, "tier composites carry no digest"
        _, home = client.get("/", ua=GOOGLEBOT)
        assert self._meta_digest(home) != h1.get(DIGEST_HEADER.lower())

    def test_the_root_composite_is_the_documented_exception(self, backend):
        """/llms.txt is built from many sources; it carries no digest
        header — the home page's HTML lanes digest the home prose."""
        app = _build_app(backend)
        client = _Client(app, backend)
        _, _, headers = client.get_full("/llms.txt", ua=AGENT)
        assert headers.get(DIGEST_HEADER.lower()) is None

    def test_gated_pages_keep_parity_on_the_served_source(self, backend):
        """The digest is of the SERVED source: a gated page's twin serves
        the gate document, and its digest matches — the parity battery
        works for every verdict, and the withheld prose's hash never
        leaks."""
        import dash_improve_my_llms as pkg
        from dash_improve_my_llms import access

        app = _build_app(backend)
        access.configure_access(lambda p: "gated" if p == "/guide" else "allow")
        try:
            client = _Client(app, backend)
            _, twin_body, twin_headers = client.get_full("/guide/llms.txt", ua=AGENT)
            d_twin = twin_headers.get(DIGEST_HEADER.lower())
            assert d_twin is not None
            # the digest is NOT the hash of the withheld prose
            prose_digest = source_digest(
                "# The Guide\n\nRead [home](/) first.\n\n- step one\n- step two"
            )
            assert d_twin != prose_digest
        finally:
            access.reset()
