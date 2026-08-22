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
    assert "User-agent: ClaudeBot" in robots_content
    assert "User-agent: CCBot" in robots_content
    assert "User-agent: Google-Extended" in robots_content

    # Check each blocked bot has Disallow
    assert robots_content.count("User-agent: GPTBot\nDisallow: /") > 0


def test_generate_robots_txt_allow_all():
    """Test robots.txt when allowing all bots."""
    config = RobotsConfig(block_ai_training=False, allow_ai_search=True, allow_traditional=True)
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
    assert "User-agent: ClaudeBot\nDisallow: /" not in robots_content


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


def _policy_by_agent(robots_content):
    """Parse robots.txt into {user-agent: [directives]}."""
    policies = {}
    agent = None
    for line in robots_content.splitlines():
        line = line.strip()
        if line.startswith("User-agent:"):
            agent = line.split(":", 1)[1].strip()
            policies.setdefault(agent, [])
        elif agent and (line.startswith("Allow:") or line.startswith("Disallow:")):
            policies[agent].append(line)
        elif not line:
            agent = None
    return policies


def test_robots_txt_ai_search_bots_are_allowed():
    """Every bot in the allow_ai_search branch must get Allow, not Disallow.

    Regression test: through 2.3.0, OAI-SearchBot was given `Disallow: /`
    inside the allow branch — every site configured to allow AI search was
    asking ChatGPT's search index to exclude it. The old version of this
    test only checked the agents were *mentioned*, so it never caught the
    directive being wrong.
    """
    config = RobotsConfig(allow_ai_search=True)
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    policies = _policy_by_agent(robots_content)
    for bot in (
        "ChatGPT-User",
        "Claude-User",
        "Claude-SearchBot",
        "PerplexityBot",
        "OAI-SearchBot",
    ):
        assert policies.get(bot) == [
            "Allow: /"
        ], f"{bot} should be allowed, got {policies.get(bot)}"


def test_robots_txt_training_bots_are_disallowed():
    """The block_ai_training branch must actually disallow each agent.

    ClaudeBot is in this list, not the search list: it is Anthropic's
    training crawler. Through 2.3.2 it sat in the allow branch while the
    deprecated aliases were blocked — backwards on both counts.
    """
    config = RobotsConfig(block_ai_training=True)
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    policies = _policy_by_agent(robots_content)
    for bot in ("GPTBot", "ClaudeBot", "CCBot", "Google-Extended", "ByteSpider"):
        assert policies.get(bot) == [
            "Disallow: /"
        ], f"{bot} should be blocked, got {policies.get(bot)}"


def test_robots_txt_never_names_legacy_anthropic_aliases():
    """`anthropic-ai` and `Claude-Web` must not appear in any branch.

    Regression test: through 2.3.2 the training branch disallowed these
    deprecated aliases. claude.ai's user-initiated fetcher honours a
    disallow on them, so the block refused the paste-into-Claude audience
    — the one llms.txt exists for — while blocking no actual training
    (ClaudeBot, the real training crawler, was allowed).
    """
    for config in (RobotsConfig(), RobotsConfig(block_ai_training=True, allow_ai_search=False)):
        robots_content = generate_robots_txt(
            config=config,
            sitemap_url="https://example.com/sitemap.xml",
            base_url="https://example.com",
        )
        assert "anthropic-ai" not in robots_content
        assert "Claude-Web" not in robots_content


def test_robots_txt_has_documentation_links():
    """Test that robots.txt includes AI-friendly documentation links.

    Updated in 2.0: only /llms.txt is advertised in the comments now.
    /page.json, /architecture.txt, and the .toon endpoints were removed.
    """
    config = RobotsConfig()
    robots_content = generate_robots_txt(
        config=config,
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )

    assert "https://example.com/llms.txt" in robots_content
    assert "https://example.com/sitemap.xml" in robots_content
    # 2.0: these should NOT appear — they were dropped
    assert "/architecture.txt" not in robots_content
    assert "/page.json" not in robots_content
    assert "/llms.toon" not in robots_content


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
        "ClaudeBot",
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


# ---------------------------------------------------------------------------
# 2.7.0/W2 — per-vendor policy drives the robots.txt groups
# ---------------------------------------------------------------------------


class TestVendorPolicy:
    def _render(self, config):
        return generate_robots_txt(
            config=config,
            sitemap_url="https://example.com/sitemap.xml",
            base_url="https://example.com",
        )

    def test_unset_reproduces_the_coarse_flags_byte_for_byte(self):
        """The byte-identical rule: a config that never heard of W2 (an
        old object without the attributes) renders the same bytes as the
        2.7.0 defaults."""
        from types import SimpleNamespace

        old_shape = SimpleNamespace(
            block_ai_training=True,
            allow_ai_search=True,
            allow_traditional=True,
            crawl_delay=None,
            custom_rules=[],
            disallowed_paths=[],
        )
        assert self._render(old_shape) == self._render(RobotsConfig())

    def test_override_moves_a_vendor_to_the_section_its_directive_matches(self):
        """claudebot -> allow: its group leaves the Disallow block and
        renders Allow — placement follows the effective directive."""
        robots = self._render(RobotsConfig(vendor_policy={"claudebot": "allow"}))
        assert "User-agent: ClaudeBot\nAllow: /" in robots
        assert "User-agent: ClaudeBot\nDisallow: /" not in robots
        # the rest of the training block is untouched
        assert "User-agent: GPTBot\nDisallow: /" in robots

    def test_a_blocked_search_vendor_renders_disallow(self):
        robots = self._render(RobotsConfig(vendor_policy={"chatgpt-user": "block"}))
        assert "User-agent: ChatGPT-User\nDisallow: /" in robots
        assert "User-agent: ChatGPT-User\nAllow: /" not in robots
        assert "User-agent: Claude-User\nAllow: /" in robots

    def test_meter_renders_allow(self):
        """A Disallow would kill the funnel metering exists for."""
        robots = self._render(RobotsConfig(vendor_policy={"gptbot": "meter"}))
        assert "User-agent: GPTBot\nAllow: /" in robots
        assert "User-agent: GPTBot\nDisallow: /" not in robots

    def test_callable_vendor_policy_is_read_at_render_time(self):
        store = {"policy": {}}
        config = RobotsConfig(vendor_policy=lambda: store["policy"])
        assert "User-agent: GPTBot\nDisallow: /" in self._render(config)
        store["policy"] = {"gptbot": "allow"}
        assert "User-agent: GPTBot\nAllow: /" in self._render(config)

    def test_raising_or_invalid_vendor_policy_falls_back_to_class_defaults(self):
        def broken():
            raise OSError("store gone")

        robots = self._render(RobotsConfig(vendor_policy=broken))
        assert robots == self._render(RobotsConfig())

        robots = self._render(
            RobotsConfig(vendor_policy={"gptbot": "maybe", "not-a-vendor": "block"})
        )
        assert robots == self._render(RobotsConfig())

    def test_allow_ai_search_false_now_blocks_in_robots(self):
        """Says==does (the W2 construction): the flag used to only delete
        the Allow section, leaving search bots covered by `User-agent: *`
        — the knob claimed to disallow and did nothing. Deliberate 2.7.0
        contract change, same class as the P4 fix."""
        robots = self._render(RobotsConfig(allow_ai_search=False))
        assert "User-agent: ChatGPT-User\nDisallow: /" in robots
        assert "User-agent: Claude-User\nDisallow: /" in robots

    def test_default_unknown_ai_has_no_robots_rendering(self):
        """robots.txt cannot address unnamed agents; the knob is
        middleware-only."""
        assert self._render(RobotsConfig(default_unknown_ai="block")) == self._render(
            RobotsConfig()
        )
