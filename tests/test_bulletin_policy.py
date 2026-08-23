"""W6 — the bulletin's toll-gate policy keys, and the two hard rules.

Rule one: the hub may only TIGHTEN local policy, never loosen — a
compromised or misconfigured hub can refuse traffic, never open a host
that chose to block. Rule two: a bulletin carrying anything shaped like a
pay-to address is refused WHOLE — the bulletin is fetched over the
network and TTL-cached, which makes a fetched address a
payment-redirection target. Price is a business setting; the address is
a key, pinned per-repo in constants.
"""

from __future__ import annotations

import pytest

from dash_improve_my_llms import bulletin
from dash_improve_my_llms.bulletin import PayToAddressRefused, _normalize
from dash_improve_my_llms.robots_generator import RobotsConfig
from dash_improve_my_llms.vendors import effective_policies

# ---------------------------------------------------------------------------
# Schema normalization
# ---------------------------------------------------------------------------


class TestPolicyKeys:
    def test_crawler_policy_is_bounded_and_validated(self):
        payload = {
            "network": {
                "crawler_policy": [
                    {"vendor": "gptbot", "policy": "block"},
                    {"vendor": "not-a-vendor", "policy": "block"},  # dropped
                    {"vendor": "claudebot", "policy": "maybe"},  # dropped
                    "junk",  # dropped
                ]
                + [{"vendor": "ccbot", "policy": "meter"}] * 20  # capped
            }
        }
        out = _normalize(payload)["network"]["crawler_policy"]
        assert {"vendor": "gptbot", "policy": "block"} in out
        assert all(e["vendor"] != "not-a-vendor" for e in out)
        assert len(out) <= 8  # the hard element cap

    def test_prices_and_rate_limit_are_bounded(self):
        payload = {
            "network": {
                "price_default": "  $0.01  ",
                "prices": [{"path": "/llms-full.txt", "price": "$0.05"}, {"bad": 1}],
                "rate_limit": "120",
            }
        }
        net = _normalize(payload)["network"]
        assert net["price_default"] == "$0.01"
        assert net["prices"] == [{"path": "/llms-full.txt", "price": "$0.05"}]
        assert net["rate_limit"] == 120

    @pytest.mark.parametrize("raw", ["nope", -5, 0, 10_001, None])
    def test_junk_rate_limits_are_dropped(self, raw):
        assert _normalize({"network": {"rate_limit": raw}})["network"]["rate_limit"] is None


# ---------------------------------------------------------------------------
# The pay-to refusal — whole payload, never sanitized
# ---------------------------------------------------------------------------


class TestPayToRefusal:
    @pytest.mark.parametrize(
        "payload",
        [
            {"network": {"pay_to": "0xabc"}},
            {"network": {"prices": [{"path": "/x", "price": "$1", "wallet": "0xabc"}]}},
            {"network": {"payment": {"recipient_address": "0xabc"}}},
            {"tips": [], "payTo": "0xabc"},
        ],
    )
    def test_any_address_shaped_key_refuses_the_whole_bulletin(self, payload):
        with pytest.raises(PayToAddressRefused):
            _normalize(payload)

    def test_a_clean_payload_passes(self):
        out = _normalize({"network": {"name": "N", "price_default": "$0.01"}})
        assert out["network"]["name"] == "N"


# ---------------------------------------------------------------------------
# Tighten-only consumption
# ---------------------------------------------------------------------------


class TestHubTightening:
    @pytest.fixture(autouse=True)
    def _fake_bulletin(self, monkeypatch):
        self._data = {"network": {}}
        monkeypatch.setattr(bulletin, "get_bulletin", lambda: self._data)
        # effective_policies imports get_bulletin from .bulletin at call
        # time, so patching the module attribute is enough.
        yield

    def test_hub_can_tighten_allow_to_block(self):
        self._data = {"network": {"crawler_policy": [{"vendor": "claude-user", "policy": "block"}]}}
        policies = effective_policies(RobotsConfig())  # claude-user default: allow
        assert policies["claude-user"] == "block"

    def test_hub_can_never_loosen_block_to_allow(self):
        """The rule that makes a compromised hub survivable."""
        self._data = {"network": {"crawler_policy": [{"vendor": "gptbot", "policy": "allow"}]}}
        policies = effective_policies(RobotsConfig(block_ai_training=True))
        assert policies["gptbot"] == "block"

    def test_hub_meter_tightens_allow_but_not_block(self):
        self._data = {"network": {"crawler_policy": [{"vendor": "googlebot", "policy": "meter"}]}}
        policies = effective_policies(RobotsConfig())
        assert policies["googlebot"] == "meter"
        self._data = {"network": {"crawler_policy": [{"vendor": "gptbot", "policy": "meter"}]}}
        assert effective_policies(RobotsConfig())["gptbot"] == "block"

    def test_bulletin_failure_changes_nothing(self, monkeypatch):
        def boom():
            raise RuntimeError("hub down")

        monkeypatch.setattr(bulletin, "get_bulletin", boom)
        assert effective_policies(RobotsConfig())["gptbot"] == "block"
        assert effective_policies(RobotsConfig())["claude-user"] == "allow"
