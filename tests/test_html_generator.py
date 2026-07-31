"""
Tests for the 2.0 static-HTML generator.

In 2.0 the signature is simpler than 1.x: the function takes
page_metadata (which may include `llms_doc`), the navigation list, and
the app_config — no more `marked_important` parameter, no more
component-tree dump.
"""

from __future__ import annotations

import pytest

from dash_improve_my_llms.html_generator import (
    _render_markdown_minimal,
    generate_static_page_html,
)

# ---------------------------------------------------------------------------
# Markdown subset renderer
# ---------------------------------------------------------------------------


class TestRenderMarkdownMinimal:
    def test_headings(self):
        out = _render_markdown_minimal("# H1\n\n## H2\n\n### H3")
        assert "<h1>H1</h1>" in out
        assert "<h2>H2</h2>" in out
        assert "<h3>H3</h3>" in out

    def test_paragraphs(self):
        out = _render_markdown_minimal("First para.\n\nSecond para.")
        assert "<p>First para.</p>" in out
        assert "<p>Second para.</p>" in out

    def test_bullet_list(self):
        out = _render_markdown_minimal("- one\n- two\n- three")
        assert "<ul>" in out
        assert "<li>one</li>" in out
        assert "<li>three</li>" in out
        assert "</ul>" in out

    def test_blockquote(self):
        out = _render_markdown_minimal("> a quote")
        assert "<blockquote>" in out
        assert "<p>a quote</p>" in out
        assert "</blockquote>" in out

    def test_inline_code(self):
        out = _render_markdown_minimal("call `foo()` here")
        assert "<code>foo()</code>" in out

    def test_bold(self):
        out = _render_markdown_minimal("this is **important**")
        assert "<strong>important</strong>" in out

    def test_escapes_html_in_content(self):
        """Raw HTML in the source must not be passed through unescaped."""
        out = _render_markdown_minimal("a <script>alert(1)</script> hazard")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_empty_input(self):
        assert _render_markdown_minimal("") == ""
        assert _render_markdown_minimal(None) == ""


# ---------------------------------------------------------------------------
# generate_static_page_html
# ---------------------------------------------------------------------------


@pytest.fixture
def app_config():
    return {"name": "Test App", "base_url": "https://example.com"}


@pytest.fixture
def all_pages():
    return [
        {"path": "/", "name": "Home"},
        {"path": "/about", "name": "About"},
    ]


class TestGenerateStaticPageHtml:
    def test_renders_title_and_description(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": "About this thing"},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert "About" in html
        assert "About this thing" in html
        assert "<title>About</title>" in html

    def test_includes_navigation(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": ""},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert 'href="/"' in html
        assert 'href="/about"' in html
        assert "Home" in html

    def test_marks_current_page(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": ""},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert 'class="current"' in html

    def test_includes_meta_tags(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": "Short desc"},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert '<meta charset="UTF-8">' in html
        assert '<meta name="viewport"' in html
        assert '<meta name="description" content="Short desc">' in html
        assert '<meta name="robots" content="index, follow">' in html

    def test_includes_schema_jsonld(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": "Short desc"},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert '<script type="application/ld+json">' in html
        assert '"@context": "https://schema.org"' in html
        # Each URL is a WebPage that belongs to the site. Typing every page as
        # WebApplication described the app, not the page, and gave 28 URLs the
        # same entity type with no relationship between them.
        assert '"@type": "WebPage"' in html
        assert '"isPartOf"' in html
        assert '"@type": "WebSite"' in html

    def test_schema_type_can_be_overridden_per_page(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "schema_type": "TechArticle"},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert '"@type": "TechArticle"' in html

    def test_jsonld_cannot_break_out_of_its_script_block(self, app_config, all_pages):
        """Page names come from author frontmatter — treat them as hostile."""
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={
                "name": "</script><script>alert(1)</script>",
                "description": "x",
            },
            all_pages=all_pages,
            app_config=app_config,
        )
        assert "</script><script>" not in html
        assert "\\u003c/script\\u003e" in html

    def test_description_falls_back_to_page_prose(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={
                "name": "About",
                "llms_doc": "# About\n\nWe build tools for Dash developers.",
            },
            all_pages=all_pages,
            app_config=app_config,
        )
        assert 'content="We build tools for Dash developers."' in html

    def test_includes_canonical_url(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": "d"},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert '<link rel="canonical" href="https://example.com/about">' in html

    def test_includes_opengraph_tags(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": "Short desc"},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert 'property="og:type"' in html
        assert 'property="og:title"' in html
        assert 'property="og:description"' in html

    def test_advertises_llms_txt_only(self, app_config, all_pages):
        """2.0: only /llms.txt is in <link rel="alternate">."""
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": ""},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert 'rel="alternate"' in html
        assert 'type="text/markdown"' in html
        # dropped routes must not appear in the HTML
        assert "/page.json" not in html
        assert "/architecture.txt" not in html
        assert "/llms.toon" not in html

    def test_renders_llms_doc_as_html(self, app_config, all_pages):
        """If llms_doc is in metadata, it's rendered as the page body."""
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={
                "name": "About",
                "description": "Short desc",
                "llms_doc": "# About\n\n> A page.\n\n- one\n- two",
            },
            all_pages=all_pages,
            app_config=app_config,
        )
        # The H1 from the LLMS_DOC becomes a real <h1>
        assert "<h1>About</h1>" in html
        assert "<blockquote>" in html
        assert "<p>A page.</p>" in html
        assert "<li>one</li>" in html

    def test_falls_back_when_no_llms_doc(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={"name": "About", "description": ""},
            all_pages=all_pages,
            app_config=app_config,
        )
        assert "interactive content that requires JavaScript" in html

    def test_escapes_html_in_title_and_description(self, app_config, all_pages):
        html = generate_static_page_html(
            page_path="/about",
            page_metadata={
                "name": "<script>alert(1)</script>",
                "description": "<img onerror=x>",
            },
            all_pages=all_pages,
            app_config=app_config,
        )
        assert "<script>alert(1)</script>" not in html  # raw must not appear
        assert "&lt;script&gt;" in html or "&lt;script" in html
