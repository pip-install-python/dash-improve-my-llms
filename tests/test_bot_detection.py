"""
Tests for bot detection module.
  # AI Training Bots (should show bot_type: "training")
  curl -A "GPTBot/1.0" http://localhost:8959/
  curl -A "anthropic-ai" http://localhost:8959/
  curl -A "Claude-Web/1.0" http://localhost:8959/
  curl -A "CCBot/2.0" http://localhost:8959/
  curl -A "Google-Extended/2.1" http://localhost:8959/

  # AI Search Bots (should show bot_type: "search")
  curl -A "ChatGPT-User" http://localhost:8959/
  curl -A "ClaudeBot/1.0" http://localhost:8959/
  curl -A "PerplexityBot/1.0" http://localhost:8959/

  # Traditional Search Bots (should show bot_type: "traditional")
  curl -A "Googlebot/2.1" http://localhost:8959/
  curl -A "Bingbot/2.0" http://localhost:8959/
  curl -A "Yahoo! Slurp" http://localhost:8959/
  curl -A "DuckDuckBot/1.0" http://localhost:8959/
"""

import pytest
from dash_improve_my_llms.bot_detection import (
    is_ai_training_bot,
    is_ai_search_bot,
    is_traditional_bot,
    is_any_bot,
    get_bot_type,
    get_all_bot_lists,
)


def test_detects_gptbot():
    """Test detection of OpenAI GPTBot."""
    ua = "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)"
    assert is_ai_training_bot(ua) is True
    assert is_any_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_detects_claudebot():
    """ClaudeBot is Anthropic's TRAINING crawler — the 2.7.0 P1 fix.

    Through 2.6.x this classified as 'search' while robots.txt disallowed
    ClaudeBot in the training block: the site told it to go away and then
    served it 200 HTML. robots.txt was the published promise, so the
    classification moved to match it. The named-human fetchers
    (Claude-User, Claude-SearchBot) are the search class — see below.
    """
    ua = "Mozilla/5.0 (compatible; ClaudeBot/1.0)"
    assert is_ai_training_bot(ua) is True
    assert is_any_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_detects_googlebot():
    """Test detection of Google Search bot."""
    ua = "Mozilla/5.0 (compatible; Googlebot/2.1)"
    assert is_traditional_bot(ua) is True
    assert is_any_bot(ua) is True
    assert get_bot_type(ua) == "traditional"


def test_detects_anthropic_ai():
    """Test detection of Anthropic AI training bot."""
    ua = "Anthropic-AI (https://www.anthropic.com)"
    assert is_ai_training_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_detects_chatgpt_user():
    """Test detection of ChatGPT browsing."""
    ua = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0"
    assert is_ai_search_bot(ua) is True
    assert get_bot_type(ua) == "search"


def test_detects_perplexitybot():
    """Test detection of Perplexity bot."""
    ua = "PerplexityBot/1.0"
    assert is_ai_search_bot(ua) is True
    assert get_bot_type(ua) == "search"


def test_detects_regular_browser():
    """Test that regular browsers are not detected as bots."""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    assert is_any_bot(ua) is False
    assert get_bot_type(ua) == "unknown"


def test_detects_firefox():
    """Test that Firefox is not detected as a bot."""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
    assert is_any_bot(ua) is False
    assert get_bot_type(ua) == "unknown"


def test_detects_safari():
    """Test that Safari is not detected as a bot."""
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    assert is_any_bot(ua) is False
    assert get_bot_type(ua) == "unknown"


def test_case_insensitive():
    """Test that bot detection is case-insensitive."""
    ua_upper = "MOZILLA/5.0 (COMPATIBLE; GPTBOT/1.0)"
    ua_lower = "mozilla/5.0 (compatible; gptbot/1.0)"
    ua_mixed = "MoZiLLa/5.0 (CoMpAtIbLe; GpTbOt/1.0)"

    assert is_ai_training_bot(ua_upper) is True
    assert is_ai_training_bot(ua_lower) is True
    assert is_ai_training_bot(ua_mixed) is True


def test_get_all_bot_lists():
    """Test that all bot lists are returned correctly."""
    bot_lists = get_all_bot_lists()

    assert "training" in bot_lists
    assert "search" in bot_lists
    assert "traditional" in bot_lists

    assert isinstance(bot_lists["training"], list)
    assert isinstance(bot_lists["search"], list)
    assert isinstance(bot_lists["traditional"], list)

    assert "gptbot" in bot_lists["training"]
    assert "claudebot" in bot_lists["training"]  # the 2.7.0 P1 fix
    assert "claude-user" in bot_lists["search"]  # the 2.7.0 P3 fix
    assert "googlebot" in bot_lists["traditional"]


def test_detects_ccbot():
    """Test detection of Common Crawl bot."""
    ua = "CCBot/2.0 (https://commoncrawl.org/faq/)"
    assert is_ai_training_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_detects_google_extended():
    """Test detection of Google Extended (Gemini training)."""
    ua = "Google-Extended"
    assert is_ai_training_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_empty_user_agent():
    """Test handling of empty user agent."""
    ua = ""
    assert is_any_bot(ua) is False
    assert get_bot_type(ua) == "unknown"


# ---------------------------------------------------------------------------
# 2.7.0 — the vendor registry (W1)
# ---------------------------------------------------------------------------

from dash_improve_my_llms.vendors import (  # noqa: E402
    VENDORS,
    get_bot_vendor,
    get_vendor,
    vendors_of_class,
)


def test_registry_agreement_kills_p1_permanently():
    """For every vendor, robots.txt's directive and get_bot_type()'s
    classification must agree — the construction W1 exists for. This test
    is what makes the ClaudeBot disagreement (P1) unrepresentable."""
    from dash_improve_my_llms.robots_generator import RobotsConfig, generate_robots_txt

    robots = generate_robots_txt(
        config=RobotsConfig(block_ai_training=True, allow_ai_search=True),
        sitemap_url="https://example.com/sitemap.xml",
        base_url="https://example.com",
    )
    for vendor in VENDORS:
        if not vendor.robots_tokens:
            continue  # anthropic-legacy: deliberately never named
        expected = {"training": "Disallow", "search": "Allow"}.get(vendor.cls)
        if expected is None:
            continue  # traditional rides `User-agent: *` when allowed
        for token in vendor.robots_tokens:
            block = f"User-agent: {token}\n{expected}: /"
            assert block in robots, f"{vendor.key}: robots.txt disagrees with class {vendor.cls}"
        ua = f"Mozilla/5.0 (compatible; {vendor.robots_tokens[0]}/1.0)"
        assert get_bot_type(ua) == vendor.cls, f"{vendor.key}: classification disagrees"


def test_new_ai_vendors_no_longer_fall_through_to_traditional():
    """The P2 fix: these all used to match the generic `bot` token and
    land in `traditional` — the branch that gets full static HTML."""
    for ua, expected in [
        ("Mozilla/5.0 (compatible; Amazonbot/0.1)", "training"),
        ("Applebot-Extended/1.0", "training"),
        ("meta-externalagent/1.1", "training"),
        ("AI2Bot/1.0 (+https://allenai.org)", "training"),
        ("Diffbot/4.0", "training"),
        ("Timpibot/1.0", "training"),
        ("ImagesiftBot/1.0", "training"),
    ]:
        assert get_bot_type(ua) == expected, ua


def test_named_human_fetchers_classify_search():
    """The P3 fix: these had NO tokens at all while robots.txt allowed
    them — the two layers disagreed in both directions."""
    for ua in ("Claude-User/1.0", "Claude-SearchBot/1.0", "Perplexity-User/1.0"):
        assert is_ai_search_bot(ua) is True, ua
        assert get_bot_type(ua) == "search", ua


def test_get_bot_vendor_is_the_identity_primitive():
    assert get_bot_vendor("Mozilla/5.0 (compatible; ClaudeBot/1.0)") == "claudebot"
    assert get_bot_vendor("Claude-User/1.0") == "claude-user"
    assert get_bot_vendor("Mozilla/5.0 (compatible; Googlebot/2.1)") == "googlebot"
    assert get_bot_vendor("some-random-crawler/1.0") is None  # generic, no identity
    assert get_bot_vendor("") is None
    assert get_vendor("claudebot").cls == "training"


def test_plain_applebot_is_not_the_extended_vendor():
    """Applebot (search) must not match the Applebot-Extended (training)
    record; it rides the generic fallback as before."""
    assert get_bot_vendor("Mozilla/5.0 (compatible; Applebot/0.1)") is None
    assert get_bot_type("Mozilla/5.0 (compatible; Applebot/0.1)") == "traditional"


def test_legacy_anthropic_aliases_classify_but_never_reach_robots():
    """UA classification only — their registry record has no robots
    tokens, preserving the hard-won paste-into-Claude rule."""
    assert get_bot_type("Anthropic-AI (https://www.anthropic.com)") == "training"
    assert get_bot_type("Claude-Web/1.0") == "training"
    legacy = get_vendor("anthropic-legacy")
    assert legacy.robots_tokens == ()


def test_registry_order_keeps_pre27_vendors_first():
    """robots.txt byte-stability: existing hosts' groups keep their
    familiar order, with 2.7.0 additions appended after."""
    training = [v.key for v in vendors_of_class("training")]
    assert training[:8] == [
        "gptbot",
        "claudebot",
        "ccbot",
        "google-extended",
        "facebookbot",
        "omgili",
        "bytespider",
        "anthropic-legacy",
    ]


# ---------------------------------------------------------------------------
# 2.9.0 — the monitor class
# ---------------------------------------------------------------------------

PINGDOM = "Pingdom.com_bot_version_1.4_(http://www.pingdom.com/)"
BETTER_UPTIME = "Better Uptime Bot Mozilla/5.0 (compatible; https://betterstack.com)"
HEADLESS = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "HeadlessChrome/128.0.0.0 Safari/537.36"
)


@pytest.mark.parametrize(
    "ua,vendor_key",
    [
        (PINGDOM, "pingdom"),
        (BETTER_UPTIME, "betteruptime"),
        (HEADLESS, "headless"),
        ("Mozilla/5.0 (compatible; UptimeRobot/2.0; http://uptimerobot.com/)", "uptimerobot"),
        ("Mozilla/5.0 (compatible; StatusCake)", "statuscake"),
        ("Site24x7", "site24x7"),
    ],
)
def test_monitors_are_named_not_unknown(ua, vendor_key):
    """The 2.9.0 fourth class. Before it, `uptimerobot` landed in
    `traditional` via the generic `bot` token and everything else landed in
    `unknown` with no vendor — so the null-key row in a host's ledger was
    part monitoring traffic and part everything else, and unreadable."""
    from dash_improve_my_llms.bot_detection import classify

    identity = classify(ua)
    assert identity["bot_type"] == "monitor", ua
    assert identity["vendor_key"] == vendor_key, ua
    assert identity["vendor_class"] == "monitor", ua
    assert identity["lane"] == "crawler", ua
    assert get_bot_type(ua) == "monitor", ua


def test_a_headless_browser_takes_the_crawler_lane():
    """Contract change: through 2.8.x HeadlessChrome claimed a browser UA,
    took the BROWSER lane and was handed the JavaScript shell. It is
    automation, not a reader — vendor matching runs before the browser
    check, so it now gets the crawler document."""
    from dash_improve_my_llms.bot_detection import classify, is_browser_ua

    assert is_browser_ua(HEADLESS) is True  # it really does look like one
    assert classify(HEADLESS)["lane"] == "crawler"


def test_an_unnamed_monitor_is_still_a_monitor():
    """Uptime Kuma, Uptime.com and a dozen self-hosted probes carry
    `uptime` without naming a vendor. `monitor` with no vendor_key beats
    attributing them all to UptimeRobot."""
    from dash_improve_my_llms.bot_detection import classify

    for ua in ("Uptime-Kuma/1.23.0", "MyCorp-Monitoring/2", "healthcheck/1.0"):
        identity = classify(ua)
        assert identity["bot_type"] == "monitor", ua
        assert identity["vendor_key"] is None, ua


def test_monitor_tokens_do_not_capture_real_crawlers():
    """The generic monitor tokens are matched before the generic bot
    tokens, so they must not be able to swallow a named vendor."""
    assert get_bot_type("Mozilla/5.0 (compatible; Googlebot/2.1)") == "traditional"
    assert get_bot_type("Mozilla/5.0 (compatible; GPTBot/1.0)") == "training"
    assert get_bot_type("Claude-User/1.0") == "search"
    assert get_bot_type("curl/8.4.0") == "traditional"


def test_monitors_are_never_named_in_robots_txt():
    """A health check is not a crawler and robots.txt is a crawling
    policy — every monitor record carries empty robots_tokens, the same
    hard rule anthropic-legacy carries for a different reason."""
    for vendor in vendors_of_class("monitor"):
        assert vendor.robots_tokens == (), vendor.key
        assert vendor.ip_ranges_url is None, vendor.key


def test_get_all_bot_lists_names_the_monitor_class():
    lists = get_all_bot_lists()
    assert "pingdom" in lists["monitor"]
    assert "headlesschrome" in lists["monitor"]
    # and it did not leak into the three that existed before
    assert "pingdom" not in lists["traditional"]
