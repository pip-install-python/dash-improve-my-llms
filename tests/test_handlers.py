"""
Tests for dash_improve_my_llms.handlers — the pure functions at the
heart of 2.0.

These are framework-agnostic and don't need a Flask/FastAPI/Quart
server. They take plain dicts in and return plain dicts/strings out,
which makes them the cheapest possible tests to write.
"""

from __future__ import annotations

import pytest

from dash_improve_my_llms.handlers import (
    build_llms_txt_for_page,
    build_robots_txt,
    build_sitemap_xml,
    handle_bot_request,
    list_pages_missing_llms_doc,
)
from dash_improve_my_llms.robots_generator import RobotsConfig

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
        assert body.startswith("# Home")
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
        assert body.startswith("# Home")


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
