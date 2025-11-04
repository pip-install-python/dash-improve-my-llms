"""
Tests for robots.txt generator module.
"""

import pytest
from dash_improve_my_llms.robots_generator import (
    RobotsConfig,
    generate_robots_txt,
)


def test_robots_config_defaults():
    """Test default RobotsConfig values."""
    config = RobotsConfig()

    assert config.block_ai_training is True
    assert config.allow_ai_search is True
    assert config.allow_traditional is True
    assert config.crawl_delay is None
    assert config.custom_rules == []
    assert config.disallowed_paths == []


def test_robots_config_custom():
    """Test custom RobotsConfig values."""
    config = RobotsConfig(
        block_ai_training=False,
        allow_ai_search=False,
        allow_traditional=False,
        crawl_delay=5,
        custom_rules=["User-agent: CustomBot", "Disallow: /custom"],
        disallowed_paths=["/admin", "/api"],
    )

    assert config.block_ai_training is False
    assert config.allow_ai_search is False
    assert config.allow_traditional is False
    assert config.crawl_delay == 5
    assert len(config.custom_rules) == 2
    assert len(config.disallowed_paths) == 2


def test_generate_robots_txt_default():
    """Test robots.txt generation with default config."""
    config = RobotsConfig()
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # Check basic structure
    assert "User-agent: *" in robots_content
    assert "Allow: /" in robots_content
    assert "Sitemap: https://example.com/sitemap.xml" in robots_content

    # Check AI training bots are blocked by default
    assert "User-agent: GPTBot" in robots_content
    assert "User-agent: anthropic-ai" in robots_content
    assert "User-agent: CCBot" in robots_content
    assert "User-agent: Google-Extended" in robots_content

    # Check each blocked bot has Disallow
    assert robots_content.count("User-agent: GPTBot\nDisallow: /") > 0


def test_generate_robots_txt_allow_all():
    """Test robots.txt when allowing all bots."""
    config = RobotsConfig(
        block_ai_training=False, allow_ai_search=True, allow_traditional=True
    )
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # Should still have basic structure
    assert "User-agent: *" in robots_content
    assert "Allow: /" in robots_content

    # Should NOT block AI training bots
    assert "User-agent: GPTBot\nDisallow: /" not in robots_content
    assert "User-agent: anthropic-ai\nDisallow: /" not in robots_content


def test_generate_robots_txt_with_crawl_delay():
    """Test robots.txt with crawl delay."""
    config = RobotsConfig(crawl_delay=10)
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    assert "Crawl-delay: 10" in robots_content


def test_generate_robots_txt_with_disallowed_paths():
    """Test robots.txt with disallowed paths."""
    config = RobotsConfig(disallowed_paths=["/admin", "/api", "/private"])
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    assert "Disallow: /admin" in robots_content
    assert "Disallow: /api" in robots_content
    assert "Disallow: /private" in robots_content


def test_generate_robots_txt_with_custom_rules():
    """Test robots.txt with custom rules."""
    config = RobotsConfig(
        custom_rules=[
            "User-agent: MyBot",
            "Allow: /special",
            "Disallow: /no-mybot",
        ]
    )
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    assert "User-agent: MyBot" in robots_content
    assert "Allow: /special" in robots_content
    assert "Disallow: /no-mybot" in robots_content


def test_robots_txt_has_ai_search_bots():
    """Test that AI search bots are explicitly allowed."""
    config = RobotsConfig(allow_ai_search=True)
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # Check AI search bots are mentioned
    assert "User-agent: ChatGPT-User" in robots_content or "AI Search" in robots_content
    assert "User-agent: ClaudeBot" in robots_content or "AI Search" in robots_content
    assert "User-agent: PerplexityBot" in robots_content or "AI Search" in robots_content


def test_robots_txt_has_documentation_links():
    """Test that robots.txt includes AI-friendly documentation links."""
    config = RobotsConfig()
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    assert "https://example.com/llms.txt" in robots_content
    assert "https://example.com/architecture.txt" in robots_content
    assert "https://example.com/page.json" in robots_content


def test_robots_txt_sitemap_reference():
    """Test that sitemap is properly referenced."""
    config = RobotsConfig()
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://myapp.com/sitemap.xml",
        base_url="https://myapp.com",
    )

    assert "Sitemap: https://myapp.com/sitemap.xml" in robots_content


def test_robots_txt_blocks_specific_training_bots():
    """Test that specific AI training bots are blocked."""
    config = RobotsConfig(block_ai_training=True)
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # Check all major training bots
    training_bots = [
        "GPTBot",
        "anthropic-ai",
        "Claude-Web",
        "CCBot",
        "Google-Extended",
        "FacebookBot",
        "ByteSpider",
    ]

    for bot in training_bots:
        assert f"User-agent: {bot}" in robots_content


def test_robots_txt_format():
    """Test that robots.txt has proper format."""
    config = RobotsConfig()
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # Check it starts with comment
    assert robots_content.startswith("#")

    # Check it has proper sections
    assert "User-agent:" in robots_content
    assert "Disallow:" in robots_content or "Allow:" in robots_content
    assert "Sitemap:" in robots_content

    # Check no empty lines at start
    lines = robots_content.split("\n")
    assert len(lines) > 10  # Should have substantial content


def test_robots_txt_combined_config():
    """Test robots.txt with multiple config options."""
    config = RobotsConfig(
        block_ai_training=True,
        allow_ai_search=True,
        crawl_delay=15,
        disallowed_paths=["/admin", "/settings"],
        custom_rules=["User-agent: SpecialBot", "Allow: /special"],
    )
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    # All features should be present
    assert "Crawl-delay: 15" in robots_content
    assert "Disallow: /admin" in robots_content
    assert "User-agent: SpecialBot" in robots_content
    assert "User-agent: GPTBot" in robots_content
    assert "Sitemap: https://example.com/sitemap.xml" in robots_content