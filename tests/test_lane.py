"""
Which document a client gets, and why (2.8 items 1 and 2).

Two defects motivated this file, both found on the wire rather than in a
test, and both invisible to a green suite because the responses were 200
with correct headers:

**F1 — a not-blocked vendor still got the browser shell.** Through 2.7.x
the crawler branch demanded an EXPLICIT ``vendor_policy`` entry before it
would serve a training-class crawler. A host whose posture was *allow*
therefore handed ClaudeBot and GPTBot the ~204kB JavaScript shell while
Googlebot and bare curl got the ~12kB crawler document. The hosts that
had opted IN to AI crawlers were serving them the worst document on the
site.

**F2 — the unmatched default was the browser shell.** Anything
``is_any_bot()`` rejected — httpx, aiohttp, node-fetch, Go-http-client, an
absent User-agent — got the shell too. For a package whose whole thesis
is machine readers, the fallback was backwards.

The assertions here are about SAMENESS as much as status: the point of
F1 is not that ClaudeBot gets a 200, it is that ClaudeBot gets the same
bytes Googlebot gets.
"""

from __future__ import annotations

import pytest

from dash_improve_my_llms import RobotsConfig
from dash_improve_my_llms.handlers import handle_bot_request

CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
CLAUDEBOT = "ClaudeBot/1.0"
# ClaudeBot's REAL header imitates a browser. It must still read as a
# crawler, which only holds while vendor matching runs before the browser
# test — this is the assertion that pins that ordering.
CLAUDEBOT_REAL = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
    "ClaudeBot/1.0; +claudebot@anthropic.com)"
)
GPTBOT = "GPTBot/1.2"

MACHINES_WITHOUT_A_VENDOR = [
    "httpx/0.27.0",
    "aiohttp/3.9.5",
    "node-fetch/1.0",
    "Go-http-client/2.0",
]


def _fetch(app, metadata, ua, path="/", config=None, headers=None):
    app._robots_config = config
    return handle_bot_request(
        path=path,
        user_agent=ua,
        app=app,
        page_metadata=metadata,
        hidden_paths=set(),
        headers=headers if headers is not None else {"user-agent": ua},
    )


# ---------------------------------------------------------------------------
# Item 1 — the lane follows the registry
# ---------------------------------------------------------------------------


class TestLaneFollowsTheRegistry:
    @pytest.mark.parametrize("ua", [CLAUDEBOT, CLAUDEBOT_REAL, GPTBOT])
    def test_a_not_blocked_training_vendor_gets_the_crawler_document(
        self, fake_app, fake_page_registry, page_metadata_sample, ua
    ):
        """F1, stated directly: no vendor_policy entry, training not blocked."""
        result = _fetch(
            fake_app, page_metadata_sample, ua, config=RobotsConfig(block_ai_training=False)
        )
        assert result is not None, "fell through to the app shell — this is F1"
        assert result["status"] == 200
        assert result["content_type"] == "text/html"

    @pytest.mark.parametrize("ua", [CLAUDEBOT, CLAUDEBOT_REAL, GPTBOT])
    def test_it_is_the_same_document_googlebot_gets(
        self, fake_app, fake_page_registry, page_metadata_sample, ua
    ):
        """The heart of F1 — not "a 200", but the SAME BYTES.

        The old behaviour returned 200 for both clients too; it just
        returned a different document to each, which is why nothing
        reported it for two minor versions.
        """
        config = RobotsConfig(block_ai_training=False)
        reference = _fetch(fake_app, page_metadata_sample, GOOGLEBOT, config=config)
        subject = _fetch(fake_app, page_metadata_sample, ua, config=config)
        assert subject is not None and reference is not None
        assert subject["body"] == reference["body"]
        assert subject["content_type"] == reference["content_type"]

    @pytest.mark.parametrize("ua", [CLAUDEBOT, CLAUDEBOT_REAL, GPTBOT])
    def test_blocking_still_403s_exactly_as_before(
        self, fake_app, fake_page_registry, page_metadata_sample, ua
    ):
        """Item 1 widened who gets the crawler doc; it did not touch block."""
        result = _fetch(
            fake_app, page_metadata_sample, ua, config=RobotsConfig(block_ai_training=True)
        )
        assert result is not None and result["status"] == 403

    def test_an_explicit_allow_still_works(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        """The pre-2.8 path — an explicit vendor_policy — is unchanged."""
        result = _fetch(
            fake_app,
            page_metadata_sample,
            CLAUDEBOT,
            config=RobotsConfig(vendor_policy={"claudebot": "allow"}),
        )
        assert result is not None and result["status"] == 200

    def test_no_robots_config_at_all_still_serves_the_crawler_document(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        """A host that never configured RobotsConfig has an allow posture."""
        result = _fetch(fake_app, page_metadata_sample, CLAUDEBOT, config=None)
        assert result is not None and result["status"] == 200


# ---------------------------------------------------------------------------
# Item 2 — the unidentified read as machines, not people
# ---------------------------------------------------------------------------


class TestUnidentifiedClientsGetTheCrawlerDocument:
    @pytest.mark.parametrize("ua", MACHINES_WITHOUT_A_VENDOR + [""])
    def test_a_client_that_is_not_positively_a_browser_gets_the_crawler_document(
        self, fake_app, fake_page_registry, page_metadata_sample, ua
    ):
        result = _fetch(fake_app, page_metadata_sample, ua)
        assert result is not None, "fell through to the app shell — this is F2"
        assert result["status"] == 200
        assert result["content_type"] == "text/html"

    def test_a_real_browser_still_falls_through_to_the_app(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        assert _fetch(fake_app, page_metadata_sample, CHROME) is None

    @pytest.mark.parametrize(
        "ua",
        [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/121.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/120.0 Safari/537.36 Edg/120.0",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
            " (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        ],
    )
    def test_real_browsers_across_engines_fall_through(
        self, fake_app, fake_page_registry, page_metadata_sample, ua
    ):
        assert _fetch(fake_app, page_metadata_sample, ua) is None

    @pytest.mark.parametrize(
        "path",
        [
            "/_dash-update-component",
            "/_dash-layout",
            "/_dash-dependencies",
            "/_dash-component-suites/dash/x.js",
            "/_reload-hash",
            "/_favicon.ico",
            "/assets/data.json",
        ],
    )
    def test_dash_endpoints_are_never_short_circuited_even_with_no_user_agent(
        self, fake_app, fake_page_registry, page_metadata_sample, path
    ):
        """The one thing item 2 could plausibly break.

        A client-side callback POST answered with crawler HTML breaks the
        APPLICATION, not merely its SEO — and an XHR does not always carry
        a browser User-agent of its own.
        """
        assert _fetch(fake_app, page_metadata_sample, "", path=path) is None

    def test_a_blocked_vendor_is_still_blocked_and_the_unknown_are_not(
        self, fake_app, fake_page_registry, page_metadata_sample
    ):
        """Item 2 gave the unidentified a document, not an exemption from
        policy — and not a vendor's policy either."""
        config = RobotsConfig(block_ai_training=True)
        assert _fetch(fake_app, page_metadata_sample, GPTBOT, config=config)["status"] == 403
        unknown = _fetch(fake_app, page_metadata_sample, "httpx/0.27.0", config=config)
        assert unknown is not None and unknown["status"] == 200
