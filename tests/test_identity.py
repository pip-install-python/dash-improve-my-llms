"""
Verified crawler identity (2.8 item 4).

``get_bot_vendor`` matches a substring, so "who is asking" has always been
a claim the client makes about itself. For eleven registry vendors the
operator publishes the addresses its crawler fetches from, and this module
checks the claim against them.

The invariant every test here defends: **verification never changes what
is served.** It produces a string for the ledger and nothing else. An
impostor sending ``ClaudeBot`` gets the same document the real ClaudeBot
gets, plus a row that says ``unverified``. Making it a gate would turn a
third-party JSON file's uptime into this package's availability.
"""

from __future__ import annotations

import json

import pytest

from dash_improve_my_llms import _identity
from dash_improve_my_llms.vendors import VENDORS, get_vendor

V4_IN = "10.11.12.13"
V6_IN = "2600:1f18:abcd::1"


@pytest.fixture(autouse=True)
def _clean():
    _identity.reset()
    yield
    _identity.reset()


@pytest.fixture
def fixture_ranges(tmp_path, monkeypatch):
    """A snapshot directory with one v4 and one v6 range per vendor."""

    def _write(vendor_key="gptbot", ipv4=("10.11.12.0/24",), ipv6=("2600:1f18:abcd::/48",)):
        payload = {
            "vendor": vendor_key,
            "source": "https://example.invalid/ranges.json",
            "fetched_at": "2026-08-29T00:00:00+00:00",
            "ipv4": list(ipv4),
            "ipv6": list(ipv6),
        }
        (tmp_path / f"{vendor_key}.json").write_text(json.dumps(payload))
        return tmp_path

    monkeypatch.setattr(_identity, "_RANGES_DIR", str(tmp_path))
    return _write


# ---------------------------------------------------------------------------
# The three states
# ---------------------------------------------------------------------------


class TestTheThreeStates:
    def test_an_address_inside_a_published_range_is_verified(self, fixture_ranges):
        fixture_ranges()
        assert _identity.verify("gptbot", V4_IN) == "verified"

    def test_ipv6_verifies_too(self, fixture_ranges):
        fixture_ranges()
        assert _identity.verify("gptbot", V6_IN) == "verified"

    def test_an_address_outside_a_published_range_is_unverified(self, fixture_ranges):
        fixture_ranges()
        assert _identity.verify("gptbot", "8.8.8.8") == "unverified"
        assert _identity.verify("gptbot", "2001:4860:4860::8888") == "unverified"

    def test_a_vendor_that_publishes_nothing_is_never_unverified(self, fixture_ranges):
        """Anthropic publishes no crawler ranges.

        ``n/a``, not ``unverified`` — the distinction matters because these
        rows are meant to be shown to the vendors they name, and calling a
        real crawler unverified on the strength of a list that does not
        exist would be a libel the ledger cannot support.
        """
        fixture_ranges()
        assert get_vendor("claudebot").ip_ranges_url is None
        assert _identity.verify("claudebot", V4_IN) == "n/a"

    def test_no_vendor_and_no_address_are_both_n_a(self, fixture_ranges):
        fixture_ranges()
        assert _identity.verify(None, V4_IN) == "n/a"
        assert _identity.verify("gptbot", None) == "n/a"
        assert _identity.verify("gptbot", "") == "n/a"
        assert _identity.verify(None, None) == "n/a"


# ---------------------------------------------------------------------------
# Degradation — every one of these used to be a way to raise into a request
# ---------------------------------------------------------------------------


class TestItNeverRaises:
    def test_a_malformed_address_is_n_a(self, fixture_ranges):
        fixture_ranges()
        assert _identity.verify("gptbot", "not-an-ip") == "n/a"
        assert _identity.verify("gptbot", "999.999.999.999") == "n/a"

    def test_a_missing_snapshot_is_n_a(self, fixture_ranges):
        fixture_ranges(vendor_key="gptbot")
        # bingbot publishes ranges but has no file in this fixture dir
        assert _identity.verify("bingbot", V4_IN) == "n/a"

    def test_a_malformed_snapshot_is_n_a_with_one_warning(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_identity, "_RANGES_DIR", str(tmp_path))
        (tmp_path / "gptbot.json").write_text("{not json at all")
        with pytest.warns(RuntimeWarning):
            assert _identity.verify("gptbot", V4_IN) == "n/a"
        # warn ONCE: a bad snapshot must not warn on every request
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _identity.verify("gptbot", V4_IN)
        assert caught == []

    def test_malformed_prefixes_are_skipped_not_fatal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_identity, "_RANGES_DIR", str(tmp_path))
        (tmp_path / "gptbot.json").write_text(
            json.dumps({"ipv4": ["10.11.12.0/24", "not-a-cidr", "999.0.0.0/8"], "ipv6": []})
        )
        with pytest.warns(RuntimeWarning):
            assert _identity.verify("gptbot", V4_IN) == "verified"

    def test_an_empty_snapshot_is_n_a_never_unverified(self, tmp_path, monkeypatch):
        """A vendor whose snapshot failed to populate must not turn its real
        crawler into a wall of `unverified` rows."""
        monkeypatch.setattr(_identity, "_RANGES_DIR", str(tmp_path))
        (tmp_path / "gptbot.json").write_text(json.dumps({"ipv4": [], "ipv6": []}))
        assert _identity.verify("gptbot", V4_IN) == "n/a"

    def test_an_address_family_the_vendor_does_not_publish_is_n_a(self, fixture_ranges):
        """OpenAI publishes v4 only. A v6 client is unknown, not an impostor."""
        fixture_ranges(ipv6=())
        assert _identity.verify("gptbot", V6_IN) == "n/a"
        assert _identity.verify("gptbot", V4_IN) == "verified"


# ---------------------------------------------------------------------------
# The upstream shape, and what actually ships
# ---------------------------------------------------------------------------


class TestSnapshots:
    def test_the_published_upstream_shape_parses(self):
        """Every operator that publishes uses this one shape — measured
        across all eleven URLs, which is why there is no per-vendor hint."""
        v4, v6 = _identity.parse_prefixes(
            {
                "creationTime": "2026-08-28T14:46:23.000000",
                "prefixes": [
                    {"ipv4Prefix": "192.0.2.0/24"},
                    {"ipv6Prefix": "2001:db8::/32"},
                    {"unexpectedKey": "ignored"},
                ],
            }
        )
        assert v4 == ["192.0.2.0/24"] and v6 == ["2001:db8::/32"]

    @pytest.mark.parametrize("payload", [None, [], "", {"prefixes": "not a list"}, {}])
    def test_junk_parses_to_nothing_rather_than_raising(self, payload):
        assert _identity.parse_prefixes(payload) == ([], [])

    def test_a_raw_vendor_document_dropped_in_by_hand_also_works(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_identity, "_RANGES_DIR", str(tmp_path))
        (tmp_path / "gptbot.json").write_text(
            json.dumps({"prefixes": [{"ipv4Prefix": "10.11.12.0/24"}]})
        )
        assert _identity.verify("gptbot", V4_IN) == "verified"

    def test_the_shipped_snapshots_cover_every_publishing_vendor(self):
        """Guards the release step: a wheel built without running
        scripts/refresh_ip_ranges.py silently empties the ledger's identity
        column instead of failing."""
        status = _identity.snapshot_status()
        publishing = {v.key for v in VENDORS if v.ip_ranges_url}
        assert set(status) == publishing
        for key, info in status.items():
            assert info["ipv4"] or info["ipv6"], f"{key} shipped an empty snapshot"
            assert info["fetched_at"], f"{key} has no fetched_at"

    def test_refresh_is_off_by_default(self):
        assert _identity._refresh_enabled is False
        _identity.configure_identity(refresh=True)
        assert _identity._refresh_enabled is True
        _identity.configure_identity()
        assert _identity._refresh_enabled is False
