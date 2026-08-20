"""
Tests for the llms.txt navigation block, content negotiation, and viewer.

The load-bearing property across this whole file is that **an agent must
never receive the HTML**. The viewer is a convenience for people; the
Markdown is the product. Every ambiguous case is asserted to fall back to
Markdown, because serving HTML to something that wanted the document defeats
the purpose of the route, while serving Markdown to a browser is merely
plainer than intended.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from dash_improve_my_llms import bulletin as bulletin_mod
from dash_improve_my_llms.handlers import (
    build_page_nav_block,
    insert_nav_block,
    wants_html_viewer,
)
from dash_improve_my_llms.llms_viewer import render_llms_viewer
from dash_improve_my_llms.network import NetworkConfig, NetworkSite

BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
BROWSER_UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


# ---------------------------------------------------------------------------
# Navigation block
# ---------------------------------------------------------------------------


@pytest.fixture
def state_with_network():
    network = NetworkConfig()
    network.name = "The 2plot network"
    network.hub_url = "https://2plot.dev"
    network.add(NetworkSite("Sibling", "https://leaflet.2plot.dev", tier="peer"))
    return SimpleNamespace(page_metadata={}, hidden_pages=set(), network=network)


def test_nav_block_points_at_site_and_network_indexes(fake_app, state_with_network):
    """The whole reason this block exists: a way out of a single document."""
    block = build_page_nav_block(fake_app, "/guide", state_with_network)

    assert "https://example.com/llms.txt" in block
    assert "https://2plot.dev/llms.txt" in block
    assert "https://example.com/sitemap.xml" in block
    assert "The 2plot network" in block


def test_nav_block_without_a_network_still_gives_the_site_index(fake_app):
    state = SimpleNamespace(page_metadata={}, hidden_pages=set(), network=NetworkConfig())
    block = build_page_nav_block(fake_app, "/guide", state)

    assert "https://example.com/llms.txt" in block
    assert "Network index" not in block


def test_nav_block_is_compact():
    """It is prepended to every page document, so its token cost is paid
    on every fetch. Four lines is the budget."""
    app = SimpleNamespace(_base_url="https://example.com")
    network = NetworkConfig()
    network.name = "N"
    network.hub_url = "https://hub.example"
    state = SimpleNamespace(network=network)

    block = build_page_nav_block(app, "/guide", state)
    assert len(block.splitlines()) <= 4


class TestInsertNavBlock:
    def test_inserted_after_heading_and_blockquote(self):
        doc = "# Title\n\n> A tagline.\n\n## Body\n\nText."
        out = insert_nav_block(doc, "NAV")
        lines = [line for line in out.splitlines() if line.strip()]

        assert lines[0] == "# Title"
        assert lines[1] == "> A tagline."
        assert lines[2] == "NAV"
        assert lines[3] == "## Body"

    def test_inserted_after_heading_when_there_is_no_tagline(self):
        out = insert_nav_block("# Title\n\nText.", "NAV")
        lines = [line for line in out.splitlines() if line.strip()]
        assert lines == ["# Title", "NAV", "Text."]

    def test_multiline_blockquote_is_not_split(self):
        doc = "# T\n\n> one\n> two\n\nBody."
        lines = [line for line in insert_nav_block(doc, "NAV").splitlines() if line.strip()]
        assert lines == ["# T", "> one", "> two", "NAV", "Body."]

    def test_prepended_when_there_is_no_heading(self):
        out = insert_nav_block("Just prose.", "NAV")
        assert out.startswith("NAV")

    def test_empty_inputs(self):
        assert insert_nav_block("# T", "") == "# T"
        assert insert_nav_block("", "NAV").strip() == "NAV"


# ---------------------------------------------------------------------------
# Content negotiation — the safety-critical part
# ---------------------------------------------------------------------------


class TestWantsHtmlViewer:
    def test_browser_gets_html(self):
        assert wants_html_viewer(accept=BROWSER_ACCEPT, user_agent=BROWSER_UA) is True

    @pytest.mark.parametrize(
        "accept",
        [
            "",  # no header at all
            "*/*",  # curl, most HTTP SDKs
            "text/plain",
            "text/markdown",
            "application/json",
            "text/plain, */*",
            "text/html;q=0.5, text/plain;q=0.9",  # explicitly prefers plain
        ],
    )
    def test_non_browser_accepts_get_markdown(self, accept):
        assert wants_html_viewer(accept=accept, user_agent="") is False

    @pytest.mark.parametrize(
        "ua",
        [
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)",
            "ClaudeBot/1.0",
            "PerplexityBot/1.0",
            "python-requests/2.31",
            "curl/8.4.0",
        ],
    )
    def test_bots_get_markdown_even_claiming_to_accept_html(self, ua):
        """A crawler that sends a browser Accept header still wants the doc."""
        assert wants_html_viewer(accept=BROWSER_ACCEPT, user_agent=ua) is False

    def test_raw_query_forces_markdown(self):
        for query in ({"raw": "1"}, {"format": "md"}, {"format": "markdown"}):
            assert (
                wants_html_viewer(accept=BROWSER_ACCEPT, user_agent=BROWSER_UA, query=query)
                is False
            )

    def test_format_html_forces_html(self):
        assert (
            wants_html_viewer(accept="*/*", user_agent="curl/8", query={"format": "html"}) is True
        )

    def test_raw_wins_over_format_html(self):
        assert (
            wants_html_viewer(
                accept=BROWSER_ACCEPT,
                user_agent=BROWSER_UA,
                query={"raw": "1", "format": "html"},
            )
            is False
        )


# ---------------------------------------------------------------------------
# Viewer rendering
# ---------------------------------------------------------------------------


class TestRenderViewer:
    def _render(self, **kwargs):
        defaults = dict(
            markdown_body="# Page\n\n> Tag.\n\nBody text.",
            page_name="Page",
            app_name="Docs",
            raw_url="/guide/llms.txt",
            site_llms_url="https://example.com/llms.txt",
            network_llms_url="https://hub.example/llms.txt",
        )
        defaults.update(kwargs)
        return render_llms_viewer(**defaults)

    def test_contains_banner_and_rendered_document(self):
        html = self._render()
        assert 'class="dv-banner"' in html
        assert "<h1>Page</h1>" in html
        assert "Body text." in html

    def test_is_noindex(self):
        """The rendered view must not compete with the real page in search."""
        assert 'name="robots" content="noindex, follow"' in self._render()

    def test_links_back_to_raw_and_both_indexes(self):
        html = self._render()
        assert "/guide/llms.txt?raw=1" in html
        assert "https://example.com/llms.txt" in html
        assert "https://hub.example/llms.txt" in html

    def test_bulletin_content_is_escaped(self):
        """Bulletin data is remote — treat the publishing host as untrusted."""
        html = self._render(
            bulletin={
                "network": {"name": "<script>alert(1)</script>", "wordmark": []},
                "tips": [{"title": "<img onerror=x>", "body": "</style><script>"}],
                "whats_new": [],
            }
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
        assert "<img onerror=x>" not in html

    def test_bulletin_wordmark_is_escaped(self):
        html = self._render(
            bulletin={"network": {"name": "N", "wordmark": ["</pre><script>x</script>"]}}
        )
        assert "<script>x</script>" not in html
        assert "&lt;/pre&gt;" in html

    def test_renders_without_a_bulletin(self):
        html = self._render(bulletin=None)
        assert 'class="dv-banner"' in html
        assert "Tips for getting started" in html

    def test_theme_and_motion_aware(self):
        html = self._render()
        assert "prefers-color-scheme: dark" in html
        assert "prefers-reduced-motion" in html

    def test_no_external_requests(self):
        """Self-contained: a docs page must not depend on a CDN being up."""
        html = self._render()
        for marker in ('src="http', 'href="http://cdn', "@import", "fonts.googleapis"):
            assert marker not in html


class TestViewerOverrides:
    """build_llms_viewer_html computes raw_url/page_name from the page path;
    the tier documents are not page documents, so both are overridable."""

    def test_raw_url_override_lands_in_the_view_raw_link(self, fake_app):
        from dash_improve_my_llms.handlers import build_llms_viewer_html

        html = build_llms_viewer_html(
            app=fake_app,
            page_path="/llms-full.txt",
            markdown_body="# Full corpus\n\nCard.",
            page_metadata={},
            raw_url="/llms-full.txt",
            page_name="Full corpus",
        )
        assert html is not None
        assert "/llms-full.txt?raw=1" in html
        # The derived value would have pointed at a URL that serves nothing.
        assert "llms-full.txt/llms.txt" not in html

    def test_page_name_override_titles_the_view(self, fake_app):
        from dash_improve_my_llms.handlers import build_llms_viewer_html

        html = build_llms_viewer_html(
            app=fake_app,
            page_path="/llms-small.txt",
            markdown_body="# Briefing.",
            page_metadata={},
            raw_url="/llms-small.txt",
            page_name="Compact briefing",
        )
        assert html is not None
        assert "Compact briefing · llms.txt" in html


# ---------------------------------------------------------------------------
# Bulletin client
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_bulletin():
    yield
    bulletin_mod._config = bulletin_mod.BulletinConfig()
    bulletin_mod._cache = bulletin_mod._Cache()


class TestBulletin:
    def test_disabled_by_default(self):
        """An OSS package must not make outbound requests unasked."""
        assert bulletin_mod.BulletinConfig().enabled is False
        assert bulletin_mod.get_bulletin() is None

    def test_configure_without_url_stays_disabled(self):
        bulletin_mod.configure_bulletin(url=None)
        assert bulletin_mod.get_bulletin() is None

    def test_normalize_bounds_and_shapes_the_payload(self):
        out = bulletin_mod._normalize(
            {
                "network": {"name": "N", "url": "https://h.example", "tagline": "T"},
                "tips": [{"title": "a"}, {"title": "b"}] * 10,
                "whats_new": ["plain string item"],
            }
        )
        assert out["network"]["name"] == "N"
        assert len(out["tips"]) <= bulletin_mod._MAX_ITEMS
        assert out["whats_new"][0]["title"] == "plain string item"

    def test_normalize_survives_a_hostile_payload(self):
        out = bulletin_mod._normalize(
            {"network": "not a dict", "tips": "not a list", "whats_new": 42}
        )
        assert out["network"]["name"] == ""
        assert out["tips"] == []
        assert out["whats_new"] == []

    @pytest.mark.parametrize(
        "url", ["javascript:alert(1)", "data:text/html,x", "ftp://h/x", "/relative"]
    )
    def test_non_http_urls_are_dropped(self, url):
        assert bulletin_mod._clean_url(url) == ""

    def test_http_urls_are_kept(self):
        assert bulletin_mod._clean_url("https://h.example/x") == "https://h.example/x"

    def test_long_strings_are_truncated(self):
        out = bulletin_mod._clean("x" * 5000, 100)
        assert len(out) <= 101
        assert out.endswith("…")

    def test_newlines_are_flattened(self):
        assert "\n" not in bulletin_mod._clean("a\nb\r\nc", 100)

    def test_oversized_wordmark_is_bounded(self):
        lines = bulletin_mod._wordmark(["x" * 500] * 100)
        assert len(lines) <= bulletin_mod._MAX_WORDMARK_LINES
        assert all(len(line) <= bulletin_mod._MAX_WORDMARK_WIDTH for line in lines)

    def test_get_bulletin_never_blocks_on_a_dead_endpoint(self):
        """A down hub must not add latency to a documentation page."""
        bulletin_mod.configure_bulletin(url="http://127.0.0.1:9/never", ttl=0.01, timeout=0.05)
        start = time.monotonic()
        for _ in range(20):
            assert bulletin_mod.get_bulletin() is None
        assert time.monotonic() - start < 1.0

    def test_stale_data_is_served_while_refreshing(self):
        bulletin_mod.configure_bulletin(url="http://127.0.0.1:9/never", ttl=0.0)
        bulletin_mod._cache.data = {"network": {"name": "cached"}}
        bulletin_mod._cache.fetched_at = time.monotonic() - 100

        assert bulletin_mod.get_bulletin()["network"]["name"] == "cached"


# ---------------------------------------------------------------------------
# Morse wordmark
# ---------------------------------------------------------------------------


class TestMorseWordmark:
    def _svg(self, **kwargs):
        from dash_improve_my_llms.wordmark import render_morse_wordmark

        defaults = dict(word="plot", prefix="2", suffix=".ai", label="2plot.ai")
        defaults.update(kwargs)
        return render_morse_wordmark(**defaults)

    def test_encodes_the_word_correctly(self):
        """plot = .--. .-.. --- -  → 5 dots, 7 dashes."""
        svg = self._svg()
        assert svg.count("<circle") == 5
        # 7 morse dashes + the i-stem rectangle.
        assert svg.count("<rect") == 8

    def test_morse_table_is_right(self):
        from dash_improve_my_llms.wordmark import MORSE

        assert "".join(MORSE[c] + " " for c in "plot").strip() == ".--. .-.. --- -"

    def test_is_self_contained(self):
        """It renders inside a docs page behind a CSP, with no network."""
        svg = self._svg()
        assert "<image" not in svg
        assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "")
        assert "<script" not in svg
        assert "@import" not in svg

    def test_is_accessible(self):
        svg = self._svg()
        assert 'role="img"' in svg
        assert 'aria-label="2plot.ai"' in svg
        assert "<title>2plot.ai</title>" in svg

    def test_scales_with_a_viewbox_and_no_fixed_size(self):
        svg = self._svg()
        assert "viewBox=" in svg
        assert "width=" not in svg.split(">")[0]

    def test_arrow_replaces_a_trailing_i(self):
        assert "mk-arrow" in self._svg(suffix=".ai")
        assert "mk-arrow" not in self._svg(suffix=".dev")

    def test_arrow_can_be_forced_off(self):
        assert "mk-arrow" not in self._svg(suffix=".ai", arrow=False)

    def test_symbols_carry_staggered_animation_indexes(self):
        """The keying sweep needs a per-symbol index across the whole mark."""
        svg = self._svg()
        assert "--mk-i:0" in svg
        assert "--mk-i:11" in svg  # 12 symbols in "plot"

    def test_escapes_prefix_and_suffix(self):
        svg = self._svg(prefix="<script>", suffix="</svg>", label="x")
        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg

    def test_unencodable_characters_are_skipped(self):
        from dash_improve_my_llms.wordmark import render_morse_wordmark

        svg = render_morse_wordmark(word="a!b", prefix="", suffix="")
        # ! has no morse form; a and b still render.
        assert svg.count("<circle") + svg.count("<rect") > 0

    def test_empty_returns_nothing_so_the_caller_can_fall_back(self):
        from dash_improve_my_llms.wordmark import render_morse_wordmark

        assert render_morse_wordmark(word="", prefix="", suffix="") == ""


class TestWordmarkSpec:
    def _render(self, spec):
        from dash_improve_my_llms.wordmark import render_wordmark_spec

        return render_wordmark_spec(spec, "Fallback")

    def test_morse_dict(self):
        out = self._render({"morse": "plot", "prefix": "2", "suffix": ".ai"})
        assert "mk-wordmark" in out

    def test_ascii_list(self):
        out = self._render([" ## ", " ## "])
        assert "<pre" in out
        assert "##" in out

    def test_ascii_is_escaped(self):
        out = self._render(["</pre><script>x</script>"])
        assert "<script>" not in out

    def test_unusable_specs_return_empty(self):
        for spec in (None, {}, [], "a string", 42, {"morse": ""}):
            assert self._render(spec) == ""


class TestBulletinWordmarkNormalization:
    def test_accepts_a_morse_dict(self):
        out = bulletin_mod._wordmark(
            {"morse": "plot", "prefix": "2", "suffix": ".ai", "arrow": True}
        )
        assert out["morse"] == "plot"
        assert out["arrow"] is True

    def test_non_boolean_arrow_falls_back_to_auto(self):
        out = bulletin_mod._wordmark({"morse": "plot", "arrow": "yes"})
        assert out["arrow"] is None

    def test_still_accepts_ascii_lists(self):
        assert bulletin_mod._wordmark(["##", "##"]) == ["##", "##"]

    def test_junk_returns_none(self):
        for raw in (None, "string", 42, {}, {"morse": ""}):
            assert bulletin_mod._wordmark(raw) is None


class TestWordmarkAlignment:
    """Columns sit on the *text's* baseline.

    Three arrangements were tried and two were wrong, so all three are pinned
    here. Centring each column put a single-symbol letter (T = one dash) in
    the middle of the mark with space above and below, reading as a stray
    element. Hanging every column from a common top edge is the same fault
    inverted — short columns dangle clear of the bottom. Sitting them on the
    baseline the adjacent glyphs already rest on is what makes the block read
    as part of the word.
    """

    def _svg(self):
        from dash_improve_my_llms.wordmark import render_morse_wordmark

        return render_morse_wordmark(word="plot", prefix="2", suffix="ai")

    def _extents(self):
        """{symbol index: (top, bottom)} for every morse symbol.

        Coordinates can be negative — the tallest column rises above y=0 once
        the block sits on the text baseline — so the patterns must accept a
        leading minus. An earlier version of this helper did not, and silently
        matched nothing.
        """
        import re

        from dash_improve_my_llms.wordmark import _DASH_H, _DOT_R

        svg = self._svg()
        extents = {}
        for match in re.finditer(r'<(circle|rect) class="mk-sym[^>]*>', svg):
            tag = match.group(0)
            index = int(re.search(r"--mk-i:(\d+)", tag).group(1))
            if match.group(1) == "circle":
                top = float(re.search(r'cy="(-?[\d.]+)"', tag).group(1)) - _DOT_R
                height = _DOT_R * 2
            else:
                top = float(re.search(r'y="(-?[\d.]+)"', tag).group(1))
                height = _DASH_H
            extents[index] = (top, top + height)
        return extents

    def test_every_column_ends_on_the_shared_baseline(self):
        from dash_improve_my_llms.wordmark import _BASELINE

        extents = self._extents()
        # "plot" = .--. / .-.. / --- / -  → columns end at symbol 3, 7, 10, 11.
        for last in (3, 7, 10, 11):
            assert extents[last][1] == pytest.approx(_BASELINE)

    def test_that_baseline_is_the_text_baseline(self):
        """Derived from the font, not a hardcoded number that can drift."""
        from dash_improve_my_llms.wordmark import _BASELINE, _CAP_HALF, _CY

        assert _BASELINE == pytest.approx(_CY + _CAP_HALF)

    def test_the_single_dash_letter_rests_on_the_baseline(self):
        from dash_improve_my_llms.wordmark import _BASELINE, _CY

        top, bottom = self._extents()[11]  # T, the last letter of "plot"
        assert bottom == pytest.approx(_BASELINE)
        # ...and hangs below the mark's middle rather than from the top.
        assert top > _CY - _BASELINE / 2

    def test_symbols_within_a_column_stack_downward(self):
        extents = self._extents()
        tops = [extents[i][0] for i in range(4)]  # P = .--.
        assert tops == sorted(tops)
        assert len(set(tops)) == 4

    def test_the_viewbox_grows_upward_instead_of_clipping(self):
        """The tallest column rises above y=0; a fixed height would crop it."""
        import re

        from dash_improve_my_llms.wordmark import _VPAD

        svg = self._svg()
        min_y, height = (
            float(v) for v in re.search(r'viewBox="0 (-?[\d.]+) [\d.]+ ([\d.]+)"', svg).groups()
        )
        extents = self._extents()
        highest = min(top for top, _ in extents.values())
        lowest = max(bottom for _, bottom in extents.values())

        assert highest < 0, "expected a column above the origin for this case"
        # The invariant is containment, not an exact figure — the viewBox is
        # emitted rounded to whole units, so asserting equality here would be
        # testing the number formatting rather than that nothing is cropped.
        assert min_y <= highest - _VPAD + 1
        assert min_y + height >= lowest + _VPAD - 1


def test_the_banner_never_repeats_the_brand_as_the_page_line():
    """On the root /llms.txt the page name IS the site name (the network
    rule puts the brand in the home page's registered name), and the banner
    used to open with the same string twice — once as the brand chip, once
    as the page line. Same name -> one line; a real page name still shows."""
    from dash_improve_my_llms.llms_viewer import render_llms_viewer

    brand = "pkg — tagline of the site"
    doubled = render_llms_viewer(
        markdown_body="# Hi", page_name=brand, app_name=brand, raw_url="/llms.txt"
    )
    assert 'class="dv-app"' in doubled, "the brand chip must survive"
    assert 'class="dv-page"' not in doubled, "the page line repeated the brand chip"

    inner = render_llms_viewer(
        markdown_body="# Hi", page_name="Analytics", app_name=brand, raw_url="/a/llms.txt"
    )
    assert "dv-page" in inner and "Analytics" in inner
