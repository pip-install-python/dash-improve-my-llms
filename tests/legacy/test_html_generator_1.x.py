"""
Tests for HTML generation module.
"""

import pytest
from dash_improve_my_llms.html_generator import (
    generate_static_page_html,
    generate_index_template,
)


def test_generate_static_page_html_basic():
    """Test basic static HTML generation."""
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test Page", "description": "A test page"},
        all_pages=[{"path": "/", "name": "Home"}, {"path": "/test", "name": "Test Page"}],
        app_config={"name": "Test App"},
        marked_important=[],
    )

    assert "<!DOCTYPE html>" in html
    assert "<html lang=\"en\">" in html
    assert "<title>Test Page</title>" in html
    assert "A test page" in html


def test_generate_static_page_html_has_navigation():
    """Test that generated HTML includes navigation."""
    all_pages = [
        {"path": "/", "name": "Home"},
        {"path": "/dashboard", "name": "Dashboard"},
        {"path": "/about", "name": "About"},
    ]
    html = generate_static_page_html(
        page_path="/dashboard",
        page_metadata={"name": "Dashboard", "description": "Main dashboard"},
        all_pages=all_pages,
        app_config={"name": "Test App"},
        marked_important=[],
    )

    # Check navigation links
    assert "<nav" in html
    assert 'href="/"' in html
    assert 'href="/dashboard"' in html
    assert 'href="/about"' in html
    assert ">Home<" in html
    assert ">Dashboard<" in html
    assert ">About<" in html


def test_generate_static_page_html_current_page_marked():
    """Test that current page is marked in navigation."""
    all_pages = [
        {"path": "/", "name": "Home"},
        {"path": "/test", "name": "Test"},
    ]
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test"},
        all_pages=all_pages,
        app_config={"name": "Test App"},
        marked_important=[],
    )

    # Current page should have "current" class
    assert 'class="current"' in html


def test_generate_static_page_html_with_important_content():
    """Test HTML generation with important content sections."""
    marked_important = [
        {
            "page_path": "/test",
            "id": "main-content",
            "html_content": "<h2>Important Section</h2><p>Key information here</p>",
        }
    ]
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test"},
        all_pages=[{"path": "/test", "name": "Test"}],
        app_config={"name": "Test App"},
        marked_important=marked_important,
    )

    assert "<h2>Important Section</h2>" in html
    assert "<p>Key information here</p>" in html
    assert 'id="main-content"' in html


def test_generate_static_page_html_has_meta_tags():
    """Test that HTML has proper meta tags."""
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test Page", "description": "Test description"},
        all_pages=[],
        app_config={"name": "Test App"},
        marked_important=[],
    )

    assert '<meta charset="UTF-8">' in html
    assert '<meta name="viewport"' in html
    assert '<meta name="description" content="Test description">' in html
    assert '<meta name="robots" content="index, follow">' in html


def test_generate_static_page_html_has_ai_hints():
    """Test that HTML has AI discovery hints."""
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test"},
        all_pages=[],
        app_config={"name": "Test App"},
        marked_important=[],
    )

    # Check for AI discovery links
    assert 'rel="alternate"' in html
    assert 'type="text/markdown"' in html
    assert 'href="/test/llms.txt"' in html
    assert 'type="application/json"' in html
    assert 'href="/test/page.json"' in html


def test_generate_static_page_html_has_structured_data():
    """Test that HTML includes JSON-LD structured data."""
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test description"},
        all_pages=[],
        app_config={"name": "Test App", "base_url": "https://example.com"},
        marked_important=[],
    )

    assert '<script type="application/ld+json">' in html
    assert '"@context": "https://schema.org"' in html
    assert '"@type": "WebApplication"' in html
    assert '"name": "Test App"' in html


def test_generate_static_page_html_has_ai_note():
    """Test that HTML has note for AI agents."""
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test"},
        all_pages=[],
        app_config={"name": "Test App"},
        marked_important=[],
    )

    assert "Note for AI Agents" in html
    assert "llms.txt" in html
    assert "architecture.txt" in html
    assert "page.json" in html


def test_generate_static_page_html_has_footer():
    """Test that HTML has footer."""
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test"},
        all_pages=[],
        app_config={"name": "Test App"},
        marked_important=[],
    )

    assert "<footer>" in html
    assert "</footer>" in html
    assert "dash-improve-my-llms" in html


def test_generate_index_template_basic():
    """Test basic index template generation."""
    template = generate_index_template(
        app_config={"name": "Test App", "description": "A test application"},
        pages=[{"path": "/", "name": "Home"}],
    )

    assert "<!DOCTYPE html>" in template
    assert "{%metas%}" in template
    assert "{%title%}" in template
    assert "{%css%}" in template
    assert "{%app_entry%}" in template
    assert "{%scripts%}" in template


def test_generate_index_template_has_ai_discovery():
    """Test that index template has AI discovery links."""
    template = generate_index_template(
        app_config={"name": "Test App", "description": "Test"},
        pages=[],
    )

    assert 'rel="alternate"' in template
    assert 'href="/llms.txt"' in template
    assert 'rel="sitemap"' in template
    assert 'href="/sitemap.xml"' in template


def test_generate_index_template_has_open_graph():
    """Test that index template has Open Graph tags."""
    template = generate_index_template(
        app_config={"name": "Test App", "description": "Test description"},
        pages=[],
    )

    assert 'property="og:type"' in template
    assert 'property="og:title"' in template
    assert 'property="og:description"' in template


def test_generate_index_template_has_structured_data():
    """Test that index template has structured data."""
    template = generate_index_template(
        app_config={
            "name": "Test App",
            "description": "Test",
            "base_url": "https://example.com",
        },
        pages=[],
    )

    assert '<script type="application/ld+json">' in template
    assert '"@context": "https://schema.org"' in template
    assert '"@type": "WebApplication"' in template


def test_generate_index_template_has_noscript():
    """Test that index template has noscript fallback."""
    template = generate_index_template(
        app_config={"name": "Test App", "description": "Test"},
        pages=[
            {"path": "/", "name": "Home", "description": "Home page"},
            {"path": "/about", "name": "About", "description": "About us"},
        ],
    )

    assert "<noscript>" in template
    assert "</noscript>" in template
    assert "requires JavaScript" in template

    # Check pages are listed in noscript
    assert ">Home<" in template
    assert ">About<" in template


def test_generate_index_template_navigation_structure():
    """Test that index template has navigation structured data."""
    pages = [
        {"path": "/", "name": "Home", "description": "Home"},
        {"path": "/dashboard", "name": "Dashboard", "description": "Dashboard"},
    ]
    template = generate_index_template(
        app_config={"name": "Test", "description": "Test", "base_url": "https://example.com"},
        pages=pages,
    )

    assert '"@type": "SiteNavigationElement"' in template
    assert '"name": "Main Navigation"' in template


def test_generate_static_page_html_no_content():
    """Test HTML generation with no important content."""
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test"},
        all_pages=[],
        app_config={"name": "Test App"},
        marked_important=[],
    )

    # Should still be valid HTML
    assert "<!DOCTYPE html>" in html
    assert "<main>" in html
    assert "requires JavaScript" in html


def test_generate_static_page_html_multiple_important_sections():
    """Test HTML with multiple important content sections."""
    marked_important = [
        {
            "page_path": "/test",
            "id": "section1",
            "html_content": "<h2>Section 1</h2>",
        },
        {
            "page_path": "/test",
            "id": "section2",
            "html_content": "<h2>Section 2</h2>",
        },
        {
            "page_path": "/other",  # Different page, should be ignored
            "id": "section3",
            "html_content": "<h2>Section 3</h2>",
        },
    ]
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test"},
        all_pages=[],
        app_config={"name": "Test App"},
        marked_important=marked_important,
    )

    assert "<h2>Section 1</h2>" in html
    assert "<h2>Section 2</h2>" in html
    assert "<h2>Section 3</h2>" not in html  # Different page


def test_generate_static_page_html_has_styles():
    """Test that generated HTML has inline styles."""
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test", "description": "Test"},
        all_pages=[],
        app_config={"name": "Test App"},
        marked_important=[],
    )

    assert "<style>" in html
    assert "</style>" in html
    assert "font-family:" in html
    assert "max-width:" in html


def test_generate_index_template_dash_placeholders():
    """Test that index template has all Dash placeholders."""
    template = generate_index_template(
        app_config={"name": "Test", "description": "Test"},
        pages=[],
    )

    # Check all required Dash placeholders
    assert "{%metas%}" in template
    assert "{%title%}" in template
    assert "{%favicon%}" in template
    assert "{%css%}" in template
    assert "{%app_entry%}" in template
    assert "{%config%}" in template
    assert "{%scripts%}" in template
    assert "{%renderer%}" in template


def test_generate_static_page_html_escapes_html():
    """Test that HTML properly handles content."""
    marked_important = [
        {
            "page_path": "/test",
            "id": "content",
            "html_content": "<p>Test & Content</p>",
        }
    ]
    html = generate_static_page_html(
        page_path="/test",
        page_metadata={"name": "Test & Page", "description": "Test < Description"},
        all_pages=[],
        app_config={"name": "Test App"},
        marked_important=marked_important,
    )

    # Should include the content (not escaped in marked_important as it's trusted HTML)
    assert "<p>Test & Content</p>" in html