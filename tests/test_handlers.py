"""
Tests for dash_improve_my_llms.handlers — the pure functions at the
heart of 2.0.

These are framework-agnostic and don't need a Flask/FastAPI/Quart
server. They take plain dicts in and return plain dicts/strings out,
which makes them the cheapest possible tests to write.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from dash_improve_my_llms import access
from dash_improve_my_llms.handlers import (
    TIER_DOC_PATHS,
    build_llms_full,
    build_llms_full_summary,
    build_llms_index,
    build_llms_small,
    build_llms_tier_doc,
    build_llms_txt_for_page,
    build_robots_txt,
    build_sitemap_xml,
    handle_bot_request,
    list_pages_missing_llms_doc,
    resolve_site_title,
)
from dash_improve_my_llms.robots_generator import RobotsConfig


@pytest.fixture(autouse=True)
def _clean_access():
    """Access control is process-global; no test may inherit another's."""
    access.reset()
    yield
    access.reset()


# ---------------------------------------------------------------------------
# build_llms_txt_for_page
# ---------------------------------------------------------------------------


class TestBuildLlmsTxt:
    def test_returns_prose_from_page_metadata(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body, status = build_llms_txt_for_page(
            app=fake_app,
            page_path="/",
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert status == 200
        # The root document is the site index; "Home" is a nav label, not
        # a site identity, so the H1 falls through to app.title.
        assert body.startswith("# Test App")
        assert "This is the landing page" in body

    def test_returns_stub_when_no_llms_doc(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body, status = build_llms_txt_for_page(
            app=fake_app,
            page_path="/about",
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert status == 200
        assert "No `LLMS_DOC` registered" in body
        assert "About" in body
        assert "About this app" in body

    def test_404_for_hidden_page(self, fake_app, fake_page_registry, page_metadata_sample):
        body, status = build_llms_txt_for_page(
            app=fake_app,
            page_path="/admin",
            page_metadata=page_metadata_sample,
            hidden_paths={"/admin"},
        )
        assert status == 404
        assert "not available" in body.lower()

    def test_404_for_unknown_path(self, fake_app, fake_page_registry, page_metadata_sample):
        body, status = build_llms_txt_for_page(
            app=fake_app,
            page_path="/nonexistent",
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert status == 404

    def test_normalizes_path_without_leading_slash(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body_with, _ = build_llms_txt_for_page(
            app=fake_app,
            page_path="/about",
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        body_without, _ = build_llms_txt_for_page(
            app=fake_app,
            page_path="about",
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert body_with == body_without

    def test_empty_path_treated_as_root(self, fake_app, fake_page_registry, page_metadata_sample):
        body, status = build_llms_txt_for_page(
            app=fake_app,
            page_path="",
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert status == 200
        assert body.startswith("# Test App")


# ---------------------------------------------------------------------------
# Site title resolution — the H1 of the root /llms.txt
# ---------------------------------------------------------------------------


class TestResolveSiteTitle:
    def test_registered_home_name_wins_over_app_title(self):
        assert resolve_site_title("my-package", "Some App") == "my-package"

    def test_generic_home_name_falls_through_to_app_title(self):
        # "Home" is a navbar label, not a site identity — never the H1
        # when a real title is available.
        assert resolve_site_title("Home", "my-package 2.0") == "my-package 2.0"

    def test_generic_labels_are_case_insensitive(self):
        assert resolve_site_title("HOME", "Real Title") == "Real Title"
        assert resolve_site_title("Index", "Real Title") == "Real Title"

    def test_dash_constructor_default_title_is_generic_too(self):
        # Dash() sets title="Dash" by default; that identifies nothing.
        assert resolve_site_title("my-package", "Dash") == "my-package"

    def test_all_generic_keeps_old_behaviour(self):
        # Nothing identifying anywhere — serve the home name as before
        # rather than inventing a title.
        assert resolve_site_title("Home", "Dash") == "Home"

    def test_nothing_registered_falls_back_to_placeholder(self):
        assert resolve_site_title(None, None) == "Dash Application"


class TestBuildLlmsIndexTitle:
    def test_home_named_home_uses_app_title_as_h1(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        # The fixture registers the home page as "Home" — the exact
        # production bug: llms.2plot.dev served "# Home" as its identity.
        body = build_llms_index(fake_app, page_metadata_sample, hidden_paths=set())
        assert body.startswith("# Test App\n")
        assert not body.startswith("# Home")

    def test_specific_home_name_becomes_the_h1(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        page_metadata_sample["/"]["name"] = "my-package"
        body = build_llms_index(fake_app, page_metadata_sample, hidden_paths=set())
        assert body.startswith("# my-package\n")


# ---------------------------------------------------------------------------
# Tiered corpus documents — /llms-small.txt and /llms-full.txt
# ---------------------------------------------------------------------------


class TestBuildLlmsSmall:
    def test_briefing_shape(self, fake_app, fake_page_registry, page_metadata_sample):
        """H1, home intro, one document link per visible page."""
        body = build_llms_small(fake_app, page_metadata_sample, hidden_paths=set())

        assert body.startswith("# Test App")
        assert "> Landing page" in body
        assert "This is the landing page." in body
        assert "## Pages" in body
        # Each line points at the page's *document* — the reader is an agent.
        assert "- [Home](https://example.com/llms.txt): Landing page" in body
        assert "- [About](https://example.com/about/llms.txt): About this app" in body

    def test_hidden_page_is_excluded(self, fake_app, fake_page_registry, page_metadata_sample):
        body = build_llms_small(fake_app, page_metadata_sample, hidden_paths={"/admin"})
        assert "/admin" not in body

    def test_advertises_the_index_and_the_full_corpus(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body = build_llms_small(fake_app, page_metadata_sample, hidden_paths=set())
        assert "Page index: https://example.com/llms.txt" in body
        assert "Full corpus: https://example.com/llms-full.txt" in body

    def test_pointers_are_list_items_not_one_run_on_paragraph(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        """Regression: consecutive lines are ONE paragraph in Markdown.

        The three pointers were emitted as bare adjacent lines, so every
        renderer collapsed them into "Page index: … Full corpus: … Network
        hub: …" — one run-on sentence, in the document whose entire job is
        to be read quickly.
        """
        from dash_improve_my_llms.markdown_renderer import render_markdown

        body = build_llms_small(fake_app, page_metadata_sample, hidden_paths=set())
        assert "\n- Page index: " in body
        assert "\n- Full corpus: " in body

        html = render_markdown(body)
        assert "<li>Page index:" in html
        assert "<li>Full corpus:" in html
        # The two pointers must not share a paragraph with each other.
        assert not re.search(r"<p>[^<]*Page index:.*?Full corpus:", html, re.S)

    def test_registered_llms_doc_is_served_verbatim(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        """An application that writes its own briefing owns the whole body."""
        page_metadata_sample["/llms-small.txt"] = {
            "llms_doc": "# Hand-written briefing\n\nExactly this."
        }
        body = build_llms_small(fake_app, page_metadata_sample, hidden_paths=set())
        assert body == "# Hand-written briefing\n\nExactly this."

    def test_pointer_urls_carry_the_request_authority(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
        body = build_llms_small(fake_app, page_metadata_sample, hidden_paths=set())
        assert "https://example.com/llms.txt?key=K1" in body
        assert "https://example.com/llms-full.txt?key=K1" in body

    def test_names_the_network_hub_when_one_exists(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        from dash_improve_my_llms.network import NetworkConfig

        network = NetworkConfig()
        network.name = "The 2plot network"
        network.hub_url = "https://2plot.dev"
        state = SimpleNamespace(page_metadata={}, hidden_pages=set(), network=network)

        body = build_llms_small(fake_app, page_metadata_sample, set(), state)
        assert "https://2plot.dev/llms.txt" in body
        assert "The 2plot network" in body


class TestBuildLlmsFull:
    def test_every_visible_pages_prose_is_present(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        assert "This is the landing page." in body
        assert "Should not appear." in body  # /admin is NOT hidden here

    def test_each_page_carries_a_source_comment(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        assert "<!-- / — https://example.com/llms.txt -->" in body
        assert "<!-- /about — https://example.com/about/llms.txt -->" in body

    def test_prose_less_page_gets_a_one_liner(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        assert "_No prose registered for `/about` — see /about/llms.txt._" in body

    def test_denied_page_is_omitted_entirely(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        access.configure_access(lambda p: "deny" if p == "/admin" else "allow")
        body = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        assert "Should not appear." not in body
        assert "/admin" not in body

    def test_gated_page_contributes_the_gate_stub_not_prose(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        """The corpus must never hold the text the per-page route withholds."""
        access.configure_access(
            lambda p: "gated" if p == "/admin" else "allow",
            gate_doc=lambda p: "# Members only\n\nRequest access.",
        )
        body = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        assert "Should not appear." not in body
        assert "Request access." in body
        # Still traceable to its own document.
        assert "<!-- /admin — https://example.com/admin/llms.txt -->" in body

    def test_size_cap_stops_the_corpus_and_indexes_the_rest(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set(), max_bytes=10)
        assert "## Not included (size cap)" in body
        assert "- [About](https://example.com/about/llms.txt)" in body
        # The bodies themselves stayed out.
        assert "This is the landing page." not in body

    def test_pages_within_budget_are_kept_before_the_cap_hits(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        full = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        capped = build_llms_full(
            fake_app,
            page_metadata_sample,
            hidden_paths=set(),
            max_bytes=len(full.encode("utf-8")),
        )
        assert "## Not included (size cap)" not in capped

    def test_no_navigation_block_inside_the_corpus(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        assert "Site index:" not in body

    def test_decorate_body_carries_authority_across_page_links(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
        body = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        assert "https://example.com/about/llms.txt?key=K1" in body


class TestBuildLlmsTierDoc:
    def test_unconfigured_access_serves_the_document(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body, status = build_llms_tier_doc(fake_app, "small", page_metadata_sample, set())
        assert status == 200
        assert body.startswith("# Test App")

        body, status = build_llms_tier_doc(fake_app, "full", page_metadata_sample, set())
        assert status == 200
        assert "full corpus" in body

    def test_denied_tier_is_404(self, fake_app, fake_page_registry, page_metadata_sample):
        access.configure_access(lambda p: "deny" if p == "/llms-full.txt" else "allow")
        body, status = build_llms_tier_doc(fake_app, "full", page_metadata_sample, set())
        assert status == 404
        assert "not available" in body.lower()

    def test_gated_tier_serves_the_gate_document_at_200(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        access.configure_access(
            lambda p: "gated" if p == "/llms-full.txt" else "allow",
            gate_doc=lambda p: f"# Gate for {p}",
        )
        body, status = build_llms_tier_doc(fake_app, "full", page_metadata_sample, set())
        assert status == 200
        assert body == "# Gate for /llms-full.txt"
        assert "landing page" not in body

    def test_mark_hidden_tier_path_is_404(self, fake_app, fake_page_registry, page_metadata_sample):
        body, status = build_llms_tier_doc(
            fake_app, "full", page_metadata_sample, {"/llms-full.txt"}
        )
        assert status == 404


class TestIndexTierAdvertisement:
    def test_index_advertises_both_tiers_above_the_page_listing(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        body = build_llms_index(fake_app, page_metadata_sample, hidden_paths=set())
        assert (
            "- [/llms-small.txt](https://example.com/llms-small.txt): "
            "compact briefing — start here if context is tight." in body
        )
        assert (
            "- [/llms-full.txt](https://example.com/llms-full.txt): "
            "every page's prose in one document (3 pages)." in body
        )
        assert body.index("/llms-small.txt") < body.index("## Pages")

    def test_advertisement_sits_under_its_own_heading(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        """Regression: an unlabelled list appended to the home page's prose
        reads as a continuation of whatever list that prose ended with."""
        body = build_llms_index(fake_app, page_metadata_sample, hidden_paths=set())
        heading = "## Other sizes of this document"
        assert heading in body
        assert body.index(heading) < body.index("- [/llms-small.txt]")
        assert body.index("- [/llms-full.txt]") < body.index("## Pages")

    def test_advertised_urls_are_decorated(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        access.configure_access(lambda p: "allow", link_suffix=lambda: "key=K1")
        body = build_llms_index(fake_app, page_metadata_sample, hidden_paths=set())
        assert "https://example.com/llms-small.txt?key=K1" in body
        assert "https://example.com/llms-full.txt?key=K1" in body

    def test_a_denied_tier_is_not_advertised(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        access.configure_access(lambda p: "deny" if p == "/llms-full.txt" else "allow")
        body = build_llms_index(fake_app, page_metadata_sample, hidden_paths=set())
        assert "/llms-full.txt" not in body
        assert "/llms-small.txt" in body


class TestBuildLlmsFullSummary:
    def test_names_the_size_the_count_and_the_way_out(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        corpus = build_llms_full(fake_app, page_metadata_sample, hidden_paths=set())
        card = build_llms_full_summary(fake_app, corpus)

        assert len(card.splitlines()) <= 20  # a card, not a corpus
        assert "3 pages" in card
        assert "/llms-full.txt?raw=1" in card
        assert "/llms-small.txt" in card
        assert "/llms.txt" in card
        # None of the corpus bodies leak into the card.
        assert "This is the landing page." not in card


# ---------------------------------------------------------------------------
# build_robots_txt
# ---------------------------------------------------------------------------


class TestBuildRobotsTxt:
    def test_uses_default_robots_config_when_absent(self, fake_app):
        body = build_robots_txt(fake_app)
        assert "User-agent: *" in body
        assert "Sitemap: https://example.com/sitemap.xml" in body

    def test_blocks_gptbot_when_configured(self, fake_app):
        fake_app._robots_config = RobotsConfig(block_ai_training=True)
        body = build_robots_txt(fake_app)
        assert "User-agent: GPTBot" in body

    def test_respects_custom_base_url(self, fake_app):
        fake_app._base_url = "https://mydomain.com"
        body = build_robots_txt(fake_app)
        assert "https://mydomain.com/sitemap.xml" in body

    def test_does_not_advertise_dropped_routes(self, fake_app):
        """2.0: /page.json, /architecture.*, /llms.toon are gone."""
        body = build_robots_txt(fake_app)
        assert "/page.json" not in body
        assert "/architecture.txt" not in body
        assert "/llms.toon" not in body


# ---------------------------------------------------------------------------
# build_sitemap_xml
# ---------------------------------------------------------------------------


class TestBuildSitemapXml:
    def test_includes_visible_pages(self, fake_app, fake_page_registry, page_metadata_sample):
        body = build_sitemap_xml(
            app=fake_app,
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert "<?xml" in body
        assert "<urlset" in body
        assert "https://example.com/about" in body

    def test_excludes_hidden_pages(self, fake_app, fake_page_registry, page_metadata_sample):
        body = build_sitemap_xml(
            app=fake_app,
            page_metadata=page_metadata_sample,
            hidden_paths={"/admin"},
        )
        assert "https://example.com/admin" not in body
        assert "https://example.com/about" in body  # not hidden, still in

    def test_uses_app_base_url(self, fake_app, fake_page_registry, page_metadata_sample):
        fake_app._base_url = "https://my.app"
        body = build_sitemap_xml(
            app=fake_app,
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert "https://my.app/" in body


# ---------------------------------------------------------------------------
# handle_bot_request
# ---------------------------------------------------------------------------


class TestHandleBotRequest:
    def test_returns_none_for_regular_browser(self, fake_app, page_metadata_sample):
        result = handle_bot_request(
            path="/",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)",
            app=fake_app,
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert result is None

    def test_returns_none_for_asset_request(self, fake_app, page_metadata_sample):
        result = handle_bot_request(
            path="/_dash-component-suites/some.js",
            user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)",
            app=fake_app,
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert result is None

    def test_returns_none_for_documentation_route(self, fake_app, page_metadata_sample):
        """Doc routes serve themselves — middleware lets them through."""
        for url in ["/llms.txt", "/about/llms.txt", "/robots.txt", "/sitemap.xml"]:
            result = handle_bot_request(
                path=url,
                user_agent="Mozilla/5.0 (compatible; GPTBot/1.0)",
                app=fake_app,
                page_metadata=page_metadata_sample,
                hidden_paths=set(),
            )
            assert result is None, f"docs route {url} should pass through"

    def test_training_bot_block_never_covers_the_tier_documents(
        self, fake_app, page_metadata_sample
    ):
        """Regression: "/llms-small.txt" does not end with "/llms.txt", so
        until the tier suffixes joined _DOC_ROUTE_SUFFIXES a site with
        block_ai_training=True served training bots a 403 on the very
        documents that exist for them."""
        fake_app._robots_config = RobotsConfig(block_ai_training=True)
        for path in ("/llms-small.txt", "/llms-full.txt"):
            result = handle_bot_request(
                path=path,
                user_agent="Mozilla/5.0 (compatible; GPTBot/1.0)",
                app=fake_app,
                page_metadata=page_metadata_sample,
                hidden_paths=set(),
            )
            assert result is None, f"tier doc {path} should pass through to its route"

    def test_blocks_training_bot_with_403(self, fake_app, page_metadata_sample):
        fake_app._robots_config = RobotsConfig(block_ai_training=True)
        result = handle_bot_request(
            path="/",
            user_agent="Mozilla/5.0 (compatible; GPTBot/1.0)",
            app=fake_app,
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert result is not None
        assert result["status"] == 403
        assert result["content_type"] == "text/plain"
        assert "403 Forbidden" in result["body"]

    def test_allows_training_bot_when_block_disabled(self, fake_app, page_metadata_sample):
        fake_app._robots_config = RobotsConfig(block_ai_training=False)
        result = handle_bot_request(
            path="/",
            user_agent="Mozilla/5.0 (compatible; GPTBot/1.0)",
            app=fake_app,
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        # Falls through to either None or a prerendered response;
        # the contract is just that we don't return 403.
        if result is not None:
            assert result["status"] != 403

    def test_returns_404_to_crawler_on_hidden_path(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        result = handle_bot_request(
            path="/admin",
            user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)",
            app=fake_app,
            page_metadata=page_metadata_sample,
            hidden_paths={"/admin"},
        )
        assert result is not None
        assert result["status"] == 404


# ---------------------------------------------------------------------------
# list_pages_missing_llms_doc
# ---------------------------------------------------------------------------


class TestListPagesMissingLlmsDoc:
    def test_returns_paths_without_llms_doc(self, fake_page_registry, page_metadata_sample):
        missing = list_pages_missing_llms_doc(page_metadata_sample, hidden_paths=set())
        # "/about" is the only one without llms_doc in the fixture; /admin has one
        # but the fixture's modules aren't real Python modules, so the resolver
        # falls back to metadata only.
        assert "/about" in missing
        assert "/" not in missing  # has llms_doc
        assert "/admin" not in missing  # has llms_doc

    def test_skips_hidden_pages(self, fake_page_registry, page_metadata_sample):
        # Remove llms_doc to make a page "missing"
        page_metadata_sample["/"].pop("llms_doc")
        missing_no_hide = list_pages_missing_llms_doc(page_metadata_sample, hidden_paths=set())
        missing_with_hide = list_pages_missing_llms_doc(page_metadata_sample, hidden_paths={"/"})
        assert "/" in missing_no_hide
        assert "/" not in missing_with_hide

    def test_empty_when_all_pages_have_docs(self, fake_page_registry, page_metadata_sample):
        # Give /about an llms_doc too
        page_metadata_sample["/about"]["llms_doc"] = "# About\n\nDocs."
        missing = list_pages_missing_llms_doc(page_metadata_sample, hidden_paths=set())
        assert missing == []


# ---------------------------------------------------------------------------
# directive stripping on the Markdown surface (regression, fixed in 2.3.3)
# ---------------------------------------------------------------------------


class TestDirectiveStrippingOnMarkdownSurface:
    def test_llms_txt_ships_no_directives(self, fake_app, fake_page_registry, page_metadata_sample):
        page_metadata_sample["/"]["llms_doc"] = (
            "# Home\n\n"
            ".. exec::docs.home.banner\n"
            "    :code: false\n\n"
            "Real prose.\n\n"
            "```\n.. exec::inside.a.fence\n```\n"
        )
        body, status = build_llms_txt_for_page(
            app=fake_app,
            page_path="/",
            page_metadata=page_metadata_sample,
            hidden_paths=set(),
        )
        assert status == 200
        assert ".. exec::docs.home.banner" not in body
        assert ":code:" not in body
        assert "Real prose." in body
        # A page documenting the directive keeps its fenced example.
        assert ".. exec::inside.a.fence" in body
