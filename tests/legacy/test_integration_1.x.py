"""
Integration tests for dash-improve-my-llms.

Tests the complete flow of all modules working together.
"""

import pytest
from dash import Dash, html, dcc
from dash_improve_my_llms import (
    add_llms_routes,
    mark_important,
    mark_hidden,
    is_hidden,
    register_page_metadata,
    LLMSConfig,
)
from dash_improve_my_llms.bot_detection import is_ai_training_bot, is_any_bot
from dash_improve_my_llms.robots_generator import RobotsConfig, generate_robots_txt
from dash_improve_my_llms.sitemap_generator import generate_sitemap_xml
from dash_improve_my_llms.html_generator import generate_static_page_html


def test_mark_hidden_integration():
    """Test mark_hidden functionality integration."""
    # Mark a page as hidden
    mark_hidden("/admin")
    mark_hidden("/settings")

    # Check they are hidden
    assert is_hidden("/admin") is True
    assert is_hidden("/settings") is True
    assert is_hidden("/public") is False


def test_robots_config_integration():
    """Test RobotsConfig with generate_robots_txt."""
    config = RobotsConfig(
        block_ai_training=True,
        allow_ai_search=True,
        crawl_delay=10,
        disallowed_paths=["/admin", "/api"],
    )

    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # Verify all config options are reflected
    assert "Crawl-delay: 10" in robots_content
    assert "Disallow: /admin" in robots_content
    assert "Disallow: /api" in robots_content
    assert "User-agent: GPTBot" in robots_content
    assert "Sitemap: https://example.com/sitemap.xml" in robots_content


def test_sitemap_with_hidden_pages():
    """Test sitemap generation excludes hidden pages."""
    # Mark pages as hidden
    mark_hidden("/admin")
    mark_hidden("/internal")

    pages = [
        {"path": "/", "name": "Home"},
        {"path": "/dashboard", "name": "Dashboard"},
        {"path": "/admin", "name": "Admin"},
        {"path": "/internal", "name": "Internal"},
    ]

    sitemap_content = generate_sitemap_xml(
        pages=pages, base_url="https://example.com", hidden_paths=["/admin", "/internal"]
    )

    # Hidden pages should not be in sitemap
    assert "https://example.com/" in sitemap_content
    assert "https://example.com/dashboard" in sitemap_content
    assert "https://example.com/admin" not in sitemap_content
    assert "https://example.com/internal" not in sitemap_content


def test_bot_detection_with_robots_txt():
    """Test bot detection works with robots.txt generation."""
    # Test various user agents
    gptbot_ua = "Mozilla/5.0 (compatible; GPTBot/1.0)"
    claude_ua = "ClaudeBot/1.0"
    google_ua = "Mozilla/5.0 (compatible; Googlebot/2.1)"

    # Detect bot types
    assert is_ai_training_bot(gptbot_ua) is True
    assert is_any_bot(claude_ua) is True
    assert is_any_bot(google_ua) is True

    # Generate robots.txt that blocks training bots
    config = RobotsConfig(block_ai_training=True, allow_ai_search=True)
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # Verify GPTBot is blocked but ClaudeBot (search) is allowed
    assert "User-agent: GPTBot\nDisallow: /" in robots_content
    assert "User-agent: ClaudeBot" in robots_content


def test_complete_workflow():
    """Test complete workflow: mark hidden, generate robots.txt and sitemap."""
    # Step 1: Configure pages
    pages = [
        {"path": "/", "name": "Home", "description": "Welcome"},
        {"path": "/dashboard", "name": "Dashboard", "description": "Main dashboard"},
        {"path": "/admin", "name": "Admin", "description": "Admin panel"},
    ]

    # Step 2: Mark admin as hidden
    mark_hidden("/admin")

    # Step 3: Configure robots
    robots_config = RobotsConfig(
        block_ai_training=True,
        allow_ai_search=True,
        crawl_delay=5,
        disallowed_paths=["/admin"],
    )

    # Step 4: Generate robots.txt
    robots_content = generate_robots_txt(
        config=robots_config,
        sitemap_url="https://myapp.com/sitemap.xml",
        base_url="https://myapp.com",
    )

    # Step 5: Generate sitemap (without hidden pages)
    visible_pages = [p for p in pages if not is_hidden(p["path"])]
    sitemap_content = generate_sitemap_xml(
        pages=visible_pages, base_url="https://myapp.com", hidden_paths=["/admin"]
    )

    # Verify robots.txt
    assert "Disallow: /admin" in robots_content
    assert "Crawl-delay: 5" in robots_content
    assert "User-agent: GPTBot" in robots_content

    # Verify sitemap excludes admin
    assert "https://myapp.com/" in sitemap_content
    assert "https://myapp.com/dashboard" in sitemap_content
    assert "https://myapp.com/admin" not in sitemap_content


def test_html_generation_with_metadata():
    """Test HTML generation with complete metadata."""
    pages = [
        {"path": "/", "name": "Home"},
        {"path": "/test", "name": "Test Page"},
    ]

    page_metadata = {
        "name": "Test Page",
        "description": "This is a test page",
    }

    app_config = {
        "name": "My Dashboard App",
        "description": "A comprehensive dashboard",
        "base_url": "https://myapp.com",
    }

    marked_important = [
        {
            "page_path": "/test",
            "id": "main-content",
            "html_content": "<h2>Key Information</h2><p>Important details</p>",
        }
    ]

    html = generate_static_page_html(
        page_path="/test",
        page_metadata=page_metadata,
        all_pages=pages,
        app_config=app_config,
        marked_important=marked_important,
    )

    # Verify all components are present
    assert "<title>Test Page</title>" in html
    assert "This is a test page" in html
    assert "My Dashboard App" in html
    assert "<h2>Key Information</h2>" in html
    assert 'href="/"' in html
    assert 'href="/test/llms.txt"' in html
    assert '"@type": "WebApplication"' in html


def test_llms_config_with_app():
    """Test LLMSConfig integration."""
    config = LLMSConfig(
        enabled=True,
        max_depth=15,
        include_css=True,
        include_callbacks=True,
    )

    assert config.enabled is True
    assert config.max_depth == 15
    assert config.include_css is True
    assert config.include_callbacks is True


def test_page_metadata_registration():
    """Test page metadata registration and retrieval."""
    register_page_metadata(
        path="/test",
        name="Test Page",
        description="A comprehensive test page",
        author="Test Author",
    )

    # Metadata is stored in global registry
    from dash_improve_my_llms import _page_metadata

    assert "/test" in _page_metadata
    assert _page_metadata["/test"]["name"] == "Test Page"
    assert _page_metadata["/test"]["description"] == "A comprehensive test page"
    assert _page_metadata["/test"]["author"] == "Test Author"


def test_mark_important_with_extraction():
    """Test mark_important integration with text extraction."""
    from dash_improve_my_llms import extract_text_content

    layout = html.Div(
        [
            html.H1("Regular Title"),
            mark_important(
                html.Div(
                    [html.H2("Important Section"), html.P("Critical information")],
                    id="important-content",
                )
            ),
        ]
    )

    texts = extract_text_content(layout)

    # Important sections should be marked
    important_texts = [t for t in texts if t.startswith("[IMPORTANT]")]
    assert len(important_texts) > 0
    assert any("Important Section" in t for t in important_texts)


def test_bot_user_agent_detection_comprehensive():
    """Test comprehensive bot detection across all categories."""
    # AI Training Bots
    training_bots = [
        "Mozilla/5.0 (compatible; GPTBot/1.0)",
        "anthropic-ai",
        "Claude-Web/1.0",
        "CCBot/2.0",
        "Google-Extended",
    ]

    for ua in training_bots:
        assert is_ai_training_bot(ua) is True, f"Failed to detect training bot: {ua}"

    # Regular browsers should not be detected
    browsers = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
    ]

    for ua in browsers:
        assert is_any_bot(ua) is False, f"Incorrectly detected browser as bot: {ua}"


def test_hidden_components_tracking():
    """Test hidden components tracking."""
    from dash_improve_my_llms import mark_component_hidden, is_component_hidden

    # Mark components as hidden
    component = html.Div(
        [html.P("Secret API Key: sk-..."), html.P("Password: ...")], id="secrets"
    )

    mark_component_hidden(component)

    # Check it's tracked
    assert is_component_hidden("secrets") is True
    assert is_component_hidden("other") is False


def test_sitemap_priority_ordering():
    """Test that sitemap orders pages by priority correctly."""
    pages = [
        {"path": "/about", "name": "About"},  # Priority 0.7 (has 'about')
        {"path": "/", "name": "Home"},  # Priority 1.0 (homepage)
        {"path": "/dashboard", "name": "Dashboard"},  # Priority 0.9 (has 'dashboard')
        {"path": "/docs", "name": "Docs"},  # Priority 0.7 (has 'docs')
    ]

    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    # Split into URLs to check order
    url_pattern = "<loc>https://example.com"
    urls_in_order = []
    for line in sitemap.split("\n"):
        if url_pattern in line:
            urls_in_order.append(line.strip())

    # Check that homepage appears first (highest priority)
    assert "<loc>https://example.com/</loc>" in urls_in_order[0]

    # Check that dashboard appears before about/docs
    dashboard_idx = next(i for i, url in enumerate(urls_in_order) if "/dashboard" in url)
    about_idx = next(i for i, url in enumerate(urls_in_order) if "/about" in url)
    docs_idx = next(i for i, url in enumerate(urls_in_order) if "/docs" in url)

    assert dashboard_idx < about_idx
    assert dashboard_idx < docs_idx


def test_robots_txt_blocks_only_training_bots():
    """Test that robots.txt correctly differentiates bot types."""
    config = RobotsConfig(
        block_ai_training=True,  # Block training
        allow_ai_search=True,  # Allow search
        allow_traditional=True,  # Allow traditional
    )

    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # Training bots should be blocked
    assert "User-agent: GPTBot\nDisallow: /" in robots_content
    assert "User-agent: anthropic-ai\nDisallow: /" in robots_content

    # Search bots should be allowed (or at least not explicitly blocked)
    assert "User-agent: ClaudeBot\nDisallow: /" not in robots_content

    # Traditional bots are allowed by default User-agent: *
    assert "User-agent: *\nAllow: /" in robots_content


def test_integration_with_custom_base_url():
    """Test integration with custom base URLs."""
    base_url = "https://my-custom-app.io"

    # Generate robots.txt
    robots_content = generate_robots_txt(
        config=RobotsConfig(),
        sitemap_url=f"{base_url}/sitemap.xml",
        base_url=base_url,
    )

    # Generate sitemap
    sitemap_content = generate_sitemap_xml(
        pages=[{"path": "/", "name": "Home"}], base_url=base_url
    )

    # Verify custom base URL is used
    assert f"Sitemap: {base_url}/sitemap.xml" in robots_content
    assert f"{base_url}/llms.txt" in robots_content
    assert f"<loc>{base_url}/</loc>" in sitemap_content


def test_end_to_end_scenario():
    """Test complete end-to-end scenario."""
    # Setup: Create app configuration
    app_config = {
        "name": "Production Dashboard",
        "description": "Enterprise dashboard application",
        "base_url": "https://dashboard.company.com",
    }

    # Setup: Define pages
    pages = [
        {"path": "/", "name": "Home", "description": "Welcome page"},
        {"path": "/analytics", "name": "Analytics", "description": "Data analytics"},
        {"path": "/reports", "name": "Reports", "description": "Generate reports"},
        {"path": "/admin", "name": "Admin", "description": "Admin panel"},
        {"path": "/settings", "name": "Settings", "description": "User settings"},
    ]

    # Step 1: Hide sensitive pages
    mark_hidden("/admin")
    mark_hidden("/settings")

    # Step 2: Configure robot policies
    robots_config = RobotsConfig(
        block_ai_training=True,
        allow_ai_search=True,
        crawl_delay=10,
        disallowed_paths=["/admin", "/settings", "/api/*"],
    )

    # Step 3: Generate robots.txt
    robots_txt = generate_robots_txt(
        config=robots_config,
        sitemap_url=f"{app_config['base_url']}/sitemap.xml",
        base_url=app_config["base_url"],
    )

    # Step 4: Generate sitemap (exclude hidden)
    visible_pages = [p for p in pages if not is_hidden(p["path"])]
    sitemap_xml = generate_sitemap_xml(
        pages=visible_pages,
        base_url=app_config["base_url"],
        hidden_paths=["/admin", "/settings"],
    )

    # Step 5: Generate static HTML for a page
    static_html = generate_static_page_html(
        page_path="/analytics",
        page_metadata=pages[1],
        all_pages=visible_pages,
        app_config=app_config,
        marked_important=[],
    )

    # Verify: robots.txt
    assert "User-agent: GPTBot\nDisallow: /" in robots_txt
    assert "Crawl-delay: 10" in robots_txt
    assert "Disallow: /admin" in robots_txt
    assert "Disallow: /settings" in robots_txt

    # Verify: sitemap.xml
    assert "https://dashboard.company.com/" in sitemap_xml
    assert "https://dashboard.company.com/analytics" in sitemap_xml
    assert "https://dashboard.company.com/reports" in sitemap_xml
    assert "https://dashboard.company.com/admin" not in sitemap_xml
    assert "https://dashboard.company.com/settings" not in sitemap_xml

    # Verify: static HTML
    assert "<title>Analytics</title>" in static_html
    assert "Data analytics" in static_html
    assert "Production Dashboard" in static_html  # App name appears in JSON-LD
    assert 'href="/analytics/llms.txt"' in static_html

    print("\n✅ End-to-end integration test passed!")
    print(f"✅ Generated robots.txt ({len(robots_txt)} bytes)")
    print(f"✅ Generated sitemap.xml ({len(sitemap_xml)} bytes)")
    print(f"✅ Generated static HTML ({len(static_html)} bytes)")


if __name__ == "__main__":
    # Run the end-to-end test
    test_end_to_end_scenario()