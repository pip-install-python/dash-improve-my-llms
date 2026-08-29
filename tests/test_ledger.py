"""
The read event and the one classification fold (2.8 items 5 and 6).

Through 2.7.x the middleware worked out which vendor was asking, whether
policy permitted it, which tier it got and how many bytes went out — and
then dropped all of it on the floor. Applications that wanted bot
accounting had to re-derive it from the User-agent with lists of their
own, and those lists drifted from this package's registry in both
directions. That drift is the direct cause of wrong bot numbers in
downstream dashboards; it is not a hypothetical.

So there are two things to defend here:

* ``classify()`` is a single fold an application can call INSTEAD of
  keeping its own lists, and
* ``on_document_read`` delivers one event per document, with a stable
  shape, and can never take a response down.

The per-adapter matrix — one event per response across three backends and
every document route — lives in ``test_adapters.py`` beside the other
tests that drive real requests.
"""

from __future__ import annotations

import warnings

import pytest

from dash_improve_my_llms import _identity, _ledger
from dash_improve_my_llms.bot_detection import classify, is_browser_ua

CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CLAUDEBOT_REAL = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
    "ClaudeBot/1.0; +claudebot@anthropic.com)"
)


@pytest.fixture(autouse=True)
def _clean():
    _ledger.reset()
    _identity.reset()
    yield
    _ledger.reset()
    _identity.reset()


@pytest.fixture
def recorded():
    """A registered callback plus the list it appends to."""
    events = []
    _ledger.on_document_read(events.append)
    return events


# ---------------------------------------------------------------------------
# Item 6 — classify()
# ---------------------------------------------------------------------------


class TestClassify:
    @pytest.mark.parametrize(
        "ua,bot_type,vendor_key,lane",
        [
            ("GPTBot/1.2", "training", "gptbot", "crawler"),
            ("ClaudeBot/1.0", "training", "claudebot", "crawler"),
            (CLAUDEBOT_REAL, "training", "claudebot", "crawler"),
            ("Mozilla/5.0 (compatible; Googlebot/2.1)", "traditional", "googlebot", "crawler"),
            ("Mozilla/5.0 compatible; ChatGPT-User/1.0", "search", "chatgpt-user", "crawler"),
            ("curl/8.4.0", "traditional", None, "crawler"),
            ("SomeRandomCrawler/1.0", "traditional", None, "crawler"),
            ("httpx/0.27.0", "unknown", None, "crawler"),
            ("", "unknown", None, "crawler"),
            (CHROME, None, None, "browser"),
        ],
    )
    def test_the_fold(self, ua, bot_type, vendor_key, lane):
        result = classify(ua)
        assert result["bot_type"] == bot_type
        assert result["vendor_key"] == vendor_key
        assert result["lane"] == lane

    def test_it_returns_every_documented_field(self):
        assert set(classify("GPTBot/1.2")) == {
            "bot_type",
            "vendor_key",
            "vendor_class",
            "verified",
            "lane",
        }

    def test_vendor_matching_beats_the_browser_test(self):
        """The ordering that keeps ClaudeBot off the browser lane.

        Its real header opens with ``Mozilla/5.0 AppleWebKit/537.36`` and
        would pass any reasonable browser sniff on its own.
        """
        assert is_browser_ua(CLAUDEBOT_REAL) is True
        assert classify(CLAUDEBOT_REAL)["lane"] == "crawler"

    def test_verification_rides_along_when_an_address_is_given(self):
        assert classify("GPTBot/1.2")["verified"] == "n/a"
        assert classify("GPTBot/1.2", "8.8.8.8")["verified"] == "unverified"

    def test_verification_never_changes_the_lane(self):
        """The ledger, not the wall — an impostor is recorded, not refused."""
        impostor = classify("GPTBot/1.2", "8.8.8.8")
        assert impostor["verified"] == "unverified"
        assert impostor["lane"] == classify("GPTBot/1.2")["lane"] == "crawler"

    @pytest.mark.parametrize(
        "ua,expected",
        [
            (CHROME, True),
            ("Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0", True),
            ("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36", True),
            ("Mozilla/5.0 (compatible; MSIE 9.0; Trident/5.0)", True),
            # Mozilla/ alone is not a browser — no real one omits the engine.
            ("Mozilla/5.0", False),
            ("httpx/0.27.0", False),
            ("", False),
        ],
    )
    def test_is_browser_ua(self, ua, expected):
        assert is_browser_ua(ua) is expected


# ---------------------------------------------------------------------------
# Item 5 — the event
# ---------------------------------------------------------------------------


class TestTheEvent:
    def test_every_field_is_always_present(self, recorded):
        _ledger.emit_read(path="/llms.txt", tier="index", user_agent="GPTBot/1.2")
        assert len(recorded) == 1
        assert set(recorded[0]) == set(_ledger.EVENT_FIELDS)

    def test_the_fields_carry_what_they_say(self, recorded):
        _ledger.emit_read(
            path="/llms-full.txt",
            method="GET",
            tier="full",
            status=200,
            body="x" * 40,
            verdict="served",
            user_agent="GPTBot/1.2",
            headers={"host": "example.com", "x-forwarded-for": "8.8.8.8"},
            policy="allow",
        )
        event = recorded[0]
        assert event["path"] == "/llms-full.txt"
        assert event["tier"] == "full"
        assert event["lane"] == "crawler"
        assert event["bot_type"] == "training"
        assert event["vendor_key"] == "gptbot"
        assert event["verified"] == "unverified"  # 8.8.8.8 is not OpenAI's
        assert event["policy"] == "allow"
        assert event["verdict"] == "served"
        assert event["status"] == 200
        assert event["bytes"] == 40
        assert event["host"] == "example.com"
        assert event["client_ip"] == "8.8.8.8"
        assert isinstance(event["ts"], float)

    def test_bytes_counts_utf8_not_characters(self, recorded):
        _ledger.emit_read(path="/llms.txt", body="café")  # 5 bytes, 4 chars
        assert recorded[0]["bytes"] == 5

    def test_the_user_agent_is_truncated(self, recorded):
        _ledger.emit_read(path="/llms.txt", user_agent="A" * 500)
        assert len(recorded[0]["ua"]) == 160

    def test_a_browser_has_no_bot_type(self, recorded):
        _ledger.emit_read(path="/llms.txt", user_agent=CHROME)
        assert recorded[0]["bot_type"] is None
        assert recorded[0]["lane"] == "browser"

    @pytest.mark.parametrize(
        "status,verdict",
        [
            (200, "served"),
            (402, "priced"),
            (403, "blocked"),
            (404, "denied"),
            (429, "rate_limited"),
        ],
    )
    def test_the_status_to_verdict_map(self, status, verdict):
        assert _ledger.verdict_for_status(status) == verdict

    def test_every_verdict_and_tier_is_one_of_the_declared_names(self):
        assert set(_ledger._VERDICT_BY_STATUS.values()) <= set(_ledger.VERDICTS)
        assert "html" in _ledger.TIERS and "index" in _ledger.TIERS


class TestItIsFailOpen:
    def test_a_raising_callback_does_not_propagate(self, recorded):
        def _boom(event):
            raise RuntimeError("the writer is broken")

        _ledger.on_document_read(_boom)
        with pytest.warns(RuntimeWarning):
            _ledger.emit_read(path="/llms.txt", user_agent="GPTBot/1.2")
        # the healthy callback still ran
        assert len(recorded) == 1

    def test_a_raising_callback_warns_only_once(self):
        _ledger.on_document_read(lambda event: (_ for _ in ()).throw(RuntimeError("x")))
        with pytest.warns(RuntimeWarning):
            _ledger.emit_read(path="/llms.txt")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for _ in range(5):
                _ledger.emit_read(path="/llms.txt")
        assert caught == []

    def test_with_no_listener_nothing_is_built(self):
        """The default for every host that has not opted in."""
        assert _ledger.has_listeners() is False
        _ledger.emit_read(path="/llms.txt")  # must not raise

    def test_registering_the_same_callback_twice_yields_one_event(self):
        events = []
        _ledger.on_document_read(events.append)
        _ledger.on_document_read(events.append)
        _ledger.emit_read(path="/llms.txt")
        assert len(events) == 1

    def test_it_works_as_a_decorator_and_returns_the_function(self):
        seen = []

        @_ledger.on_document_read
        def _writer(event):
            seen.append(event)

        assert callable(_writer)
        _ledger.emit_read(path="/llms.txt")
        assert len(seen) == 1

    def test_a_non_callable_is_rejected_at_registration(self):
        with pytest.raises(TypeError):
            _ledger.on_document_read("not callable")

    def test_bad_header_objects_degrade_rather_than_raise(self, recorded):
        class Hostile:
            def get(self, *a, **k):
                raise RuntimeError("nope")

        _ledger.emit_read(path="/llms.txt", headers=Hostile())
        assert recorded[0]["client_ip"] is None
        assert recorded[0]["host"] is None
