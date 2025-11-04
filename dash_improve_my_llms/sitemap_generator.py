"""
Generate sitemap.xml from registered Dash pages.

This module provides functionality to automatically generate sitemaps
from Dash page registry with intelligent priority and frequency inference.
"""

from datetime import datetime
from typing import Dict, List, Optional


class SitemapEntry:
    """Represents a single URL in the sitemap."""

    def __init__(
        self,
        loc: str,
        lastmod: Optional[str] = None,
        changefreq: Optional[str] = "weekly",
        priority: Optional[float] = 0.5,
    ):
        """
        Initialize a sitemap entry.

        Args:
            loc: Full URL of the page
            lastmod: Last modification date (YYYY-MM-DD)
            changefreq: How frequently the page changes
            priority: Priority relative to other pages (0.0-1.0)
        """
        self.loc = loc
        self.lastmod = lastmod or datetime.now().strftime("%Y-%m-%d")
        self.changefreq = changefreq
        self.priority = priority

    def to_xml(self) -> str:
        """
        Convert entry to XML format.

        Returns:
            XML string for this sitemap entry
        """
        xml = [
            "  <url>",
            f"    <loc>{self.loc}</loc>",
            f"    <lastmod>{self.lastmod}</lastmod>",
        ]

        # Only add changefreq if it's set and not None
        if self.changefreq is not None:
            xml.append(f"    <changefreq>{self.changefreq}</changefreq>")

        # Only add priority if it's set and not None
        if self.priority is not None:
            xml.append(f"    <priority>{self.priority:.1f}</priority>")

        xml.append("  </url>")

        return "\n".join(xml)


def infer_page_priority(path: str, metadata: Dict) -> float:
    """
    Infer priority based on page path and metadata.

    Priority scale:
    - 1.0: Homepage
    - 0.9: Primary dashboards/features
    - 0.8: Secondary pages
    - 0.7: Documentation
    - 0.5: Other pages

    Args:
        path: Page path
        metadata: Page metadata

    Returns:
        Priority value between 0.0 and 1.0
    """
    # Homepage always highest
    if path == "/":
        return 1.0

    # Check for keywords in path
    high_priority_keywords = ["dashboard", "main", "overview", "home"]
    medium_priority_keywords = ["report", "analytics", "data", "view"]
    low_priority_keywords = ["about", "help", "docs", "api", "settings"]

    path_lower = path.lower()

    if any(kw in path_lower for kw in high_priority_keywords):
        return 0.9
    elif any(kw in path_lower for kw in medium_priority_keywords):
        return 0.8
    elif any(kw in path_lower for kw in low_priority_keywords):
        return 0.7

    return 0.5


def infer_change_frequency(path: str, metadata: Dict) -> str:
    """
    Infer change frequency based on page type.

    Returns: always, hourly, daily, weekly, monthly, yearly, never

    Args:
        path: Page path
        metadata: Page metadata

    Returns:
        Change frequency string
    """
    path_lower = path.lower()

    # Real-time data pages
    if any(kw in path_lower for kw in ["dashboard", "live", "real-time", "realtime"]):
        return "daily"

    # Regular content
    if any(kw in path_lower for kw in ["report", "analytics", "data"]):
        return "weekly"

    # Documentation
    if any(kw in path_lower for kw in ["docs", "api", "help", "guide"]):
        return "monthly"

    # Static pages
    if any(kw in path_lower for kw in ["about", "contact", "terms", "privacy"]):
        return "yearly"

    return "weekly"


def generate_sitemap_xml(
    pages: List[Dict],
    base_url: str,
    custom_entries: Optional[List[SitemapEntry]] = None,
    hidden_paths: Optional[List[str]] = None,
) -> str:
    """
    Generate sitemap.xml from registered pages.

    Args:
        pages: List of page metadata from register_page_metadata()
        base_url: Base URL of the application
        custom_entries: Additional custom entries to include
        hidden_paths: List of paths to exclude from sitemap

    Returns:
        Complete sitemap.xml content
    """

    hidden_paths = hidden_paths or []
    entries = []

    # Add entries for registered pages
    for page in pages:
        path = page.get("path", "")

        # Skip hidden paths
        if path in hidden_paths:
            continue

        # Skip paths marked as hidden
        if page.get("hidden", False):
            continue

        entry = SitemapEntry(
            loc=f"{base_url}{path}",
            priority=infer_page_priority(path, page),
            changefreq=infer_change_frequency(path, page),
        )
        entries.append(entry)

    # Add custom entries
    if custom_entries:
        entries.extend(custom_entries)

    # Sort by priority (highest first)
    entries.sort(key=lambda e: e.priority, reverse=True)

    # Build XML
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "",
    ]

    for entry in entries:
        xml.append(entry.to_xml())
        xml.append("")

    xml.append("</urlset>")

    return "\n".join(xml)