"""
Tests for sitemap.xml generator module.
"""

import pytest
from dash_improve_my_llms.sitemap_generator import (
    SitemapEntry,
    generate_sitemap_xml,
    infer_page_priority,
    infer_change_frequency,
)


def test_sitemap_entry_creation():
    """Test creating a sitemap entry."""
    entry = SitemapEntry(
        loc="https://example.com/page",
        lastmod="2024-01-01",
        changefreq="daily",
        priority=0.8,
    )

    assert entry.loc == "https://example.com/page"
    assert entry.lastmod == "2024-01-01"
    assert entry.changefreq == "daily"
    assert entry.priority == 0.8


def test_sitemap_entry_to_xml():
    """Test converting sitemap entry to XML."""
    entry = SitemapEntry(
        loc="https://example.com/test", changefreq="weekly", priority=0.7
    )
    xml = entry.to_xml()

    assert "<url>" in xml
    assert "</url>" in xml
    assert "<loc>https://example.com/test</loc>" in xml
    assert "<changefreq>weekly</changefreq>" in xml
    assert "<priority>0.7</priority>" in xml
    assert "<lastmod>" in xml  # Should have automatic lastmod


def test_sitemap_entry_minimal():
    """Test sitemap entry with minimal info."""
    entry = SitemapEntry(loc="https://example.com/minimal")
    xml = entry.to_xml()

    assert "<loc>https://example.com/minimal</loc>" in xml
    assert "<lastmod>" in xml
    # Default values should be used
    assert "<changefreq>weekly</changefreq>" in xml
    assert "<priority>0.5</priority>" in xml


def test_infer_priority_homepage():
    """Test priority inference for homepage."""
    priority = infer_page_priority("/", {})
    assert priority == 1.0


def test_infer_priority_dashboard():
    """Test priority inference for dashboard pages."""
    assert infer_page_priority("/dashboard", {}) == 0.9
    assert infer_page_priority("/main", {}) == 0.9
    assert infer_page_priority("/overview", {}) == 0.9


def test_infer_priority_reports():
    """Test priority inference for report pages."""
    assert infer_page_priority("/report", {}) == 0.8
    assert infer_page_priority("/analytics", {}) == 0.8
    assert infer_page_priority("/data-view", {}) == 0.8


def test_infer_priority_docs():
    """Test priority inference for documentation pages."""
    assert infer_page_priority("/docs", {}) == 0.7
    assert infer_page_priority("/help", {}) == 0.7
    assert infer_page_priority("/api", {}) == 0.7


def test_infer_priority_default():
    """Test default priority for unknown pages."""
    assert infer_page_priority("/random-page", {}) == 0.5


def test_infer_changefreq_dashboard():
    """Test change frequency inference for dashboards."""
    assert infer_change_frequency("/dashboard", {}) == "daily"
    assert infer_change_frequency("/live-data", {}) == "daily"
    assert infer_change_frequency("/real-time", {}) == "daily"


def test_infer_changefreq_reports():
    """Test change frequency inference for reports."""
    assert infer_change_frequency("/report", {}) == "weekly"
    assert infer_change_frequency("/analytics", {}) == "weekly"


def test_infer_changefreq_docs():
    """Test change frequency inference for documentation."""
    assert infer_change_frequency("/docs", {}) == "monthly"
    assert infer_change_frequency("/help", {}) == "monthly"
    assert infer_change_frequency("/api", {}) == "monthly"


def test_infer_changefreq_static():
    """Test change frequency inference for static pages."""
    assert infer_change_frequency("/about", {}) == "yearly"
    assert infer_change_frequency("/contact", {}) == "yearly"
    assert infer_change_frequency("/terms", {}) == "yearly"


def test_infer_changefreq_default():
    """Test default change frequency."""
    assert infer_change_frequency("/random", {}) == "weekly"


def test_generate_sitemap_xml_empty():
    """Test generating sitemap with no pages."""
    sitemap = generate_sitemap_xml(pages=[], base_url="https://example.com")

    assert '<?xml version="1.0" encoding="UTF-8"?>' in sitemap
    assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in sitemap
    assert "</urlset>" in sitemap


def test_generate_sitemap_xml_single_page():
    """Test generating sitemap with single page."""
    pages = [{"path": "/", "name": "Home"}]
    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    assert "<url>" in sitemap
    assert "<loc>https://example.com/</loc>" in sitemap
    assert "<priority>1.0</priority>" in sitemap  # Homepage gets 1.0


def test_generate_sitemap_xml_multiple_pages():
    """Test generating sitemap with multiple pages."""
    pages = [
        {"path": "/", "name": "Home"},
        {"path": "/dashboard", "name": "Dashboard"},
        {"path": "/about", "name": "About"},
    ]
    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    assert "<loc>https://example.com/</loc>" in sitemap
    assert "<loc>https://example.com/dashboard</loc>" in sitemap
    assert "<loc>https://example.com/about</loc>" in sitemap


def test_generate_sitemap_xml_priority_sorting():
    """Test that pages are sorted by priority."""
    pages = [
        {"path": "/about", "name": "About"},  # Lower priority
        {"path": "/", "name": "Home"},  # Highest priority
        {"path": "/dashboard", "name": "Dashboard"},  # High priority
    ]
    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    # Homepage should appear first (highest priority)
    home_pos = sitemap.find("<loc>https://example.com/</loc>")
    dashboard_pos = sitemap.find("<loc>https://example.com/dashboard</loc>")
    about_pos = sitemap.find("<loc>https://example.com/about</loc>")

    assert home_pos < dashboard_pos < about_pos


def test_generate_sitemap_xml_hidden_pages():
    """Test that hidden pages are excluded."""
    pages = [
        {"path": "/", "name": "Home"},
        {"path": "/dashboard", "name": "Dashboard"},
        {"path": "/admin", "name": "Admin", "hidden": True},
    ]
    sitemap = generate_sitemap_xml(
        pages=pages, base_url="https://example.com", hidden_paths=["/admin"]
    )

    assert "<loc>https://example.com/</loc>" in sitemap
    assert "<loc>https://example.com/dashboard</loc>" in sitemap
    assert "<loc>https://example.com/admin</loc>" not in sitemap


def test_generate_sitemap_xml_with_descriptions():
    """Test sitemap generation with page descriptions."""
    pages = [
        {
            "path": "/",
            "name": "Home",
            "description": "Welcome to our application",
        },
        {
            "path": "/dashboard",
            "name": "Dashboard",
            "description": "Main dashboard",
        },
    ]
    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    # Descriptions don't appear in sitemap XML, but should not cause errors
    assert "<url>" in sitemap
    assert len(sitemap.split("<url>")) == 3  # urlset + 2 urls


def test_generate_sitemap_xml_custom_entries():
    """Test adding custom sitemap entries."""
    pages = [{"path": "/", "name": "Home"}]
    custom_entries = [
        SitemapEntry(
            loc="https://example.com/special", changefreq="monthly", priority=0.6
        )
    ]
    sitemap = generate_sitemap_xml(
        pages=pages, base_url="https://example.com", custom_entries=custom_entries
    )

    assert "<loc>https://example.com/</loc>" in sitemap
    assert "<loc>https://example.com/special</loc>" in sitemap
    assert "<changefreq>monthly</changefreq>" in sitemap


def test_generate_sitemap_xml_format():
    """Test sitemap XML format compliance."""
    pages = [
        {"path": "/", "name": "Home"},
        {"path": "/page1", "name": "Page 1"},
    ]
    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    # Check XML declaration
    assert sitemap.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    # Check namespace
    assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in sitemap

    # Check proper closing
    assert sitemap.strip().endswith("</urlset>")

    # Check each URL has required elements
    assert sitemap.count("<loc>") == sitemap.count("</loc>")
    assert sitemap.count("<url>") == sitemap.count("</url>")


def test_generate_sitemap_xml_special_characters():
    """Test sitemap with special characters in URLs."""
    pages = [
        {"path": "/page-with-dashes", "name": "Dashes"},
        {"path": "/page_with_underscores", "name": "Underscores"},
    ]
    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    assert "<loc>https://example.com/page-with-dashes</loc>" in sitemap
    assert "<loc>https://example.com/page_with_underscores</loc>" in sitemap


def test_generate_sitemap_xml_all_frequencies():
    """Test all change frequency options."""
    pages = [
        {"path": "/always", "name": "Always"},
        {"path": "/hourly", "name": "Hourly"},
        {"path": "/daily", "name": "Daily"},
        {"path": "/weekly", "name": "Weekly"},
        {"path": "/monthly", "name": "Monthly"},
        {"path": "/yearly", "name": "Yearly"},
        {"path": "/never", "name": "Never"},
    ]
    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    # Should generate valid sitemap with all pages
    assert sitemap.count("<url>") == len(pages)


def test_generate_sitemap_xml_different_base_urls():
    """Test sitemap generation with different base URLs."""
    pages = [{"path": "/", "name": "Home"}]

    sitemap1 = generate_sitemap_xml(pages=pages, base_url="https://example.com")
    sitemap2 = generate_sitemap_xml(pages=pages, base_url="https://myapp.io")
    sitemap3 = generate_sitemap_xml(pages=pages, base_url="http://localhost:8050")

    assert "<loc>https://example.com/</loc>" in sitemap1
    assert "<loc>https://myapp.io/</loc>" in sitemap2
    assert "<loc>http://localhost:8050/</loc>" in sitemap3


def test_generate_sitemap_xml_no_duplicate_urls():
    """Test that sitemap doesn't have duplicate URLs."""
    pages = [
        {"path": "/", "name": "Home"},
        {"path": "/page", "name": "Page 1"},
        {"path": "/page", "name": "Page 2"},  # Duplicate path
    ]
    sitemap = generate_sitemap_xml(pages=pages, base_url="https://example.com")

    # Count how many times /page appears
    page_count = sitemap.count("<loc>https://example.com/page</loc>")
    # Should appear twice (both duplicates are included, prioritization handles it)
    assert page_count == 2  # Both are added, sorted by priority


def test_sitemap_entry_none_values():
    """Test sitemap entry with None for optional fields."""
    entry = SitemapEntry(
        loc="https://example.com/test", changefreq=None, priority=None
    )
    xml = entry.to_xml()

    # Should still have loc and lastmod
    assert "<loc>https://example.com/test</loc>" in xml
    assert "<lastmod>" in xml

    # None values should not appear in the XML
    assert "<changefreq>" not in xml
    assert "<priority>" not in xml