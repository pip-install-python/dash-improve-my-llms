"""The country guardrail (dash_improve_my_llms/geo.py) — G1 of 2.7.0.

The contract under test: opt-in, 451-on-everything for denied countries
(humans and bots, every surface), byte-identical no-op when unconfigured,
no network lookups in the request path, fail-open on unknown by default,
and the callable seam a writable control board wires a persisted store
through.
"""

from __future__ import annotations

import logging

import pytest

from dash_improve_my_llms import geo


@pytest.fixture(autouse=True)
def _clean_geo():
    """Geo config is process-global; no test may inherit another's."""
    geo.reset()
    yield
    geo.reset()


# ---------------------------------------------------------------------------
# configure_geo — validation
# ---------------------------------------------------------------------------


class TestConfigureGeo:
    def test_static_codes_are_validated_eagerly(self):
        with pytest.raises(ValueError):
            geo.configure_geo(deny_countries=["Russia"])  # names are not codes
        with pytest.raises(ValueError):
            geo.configure_geo(deny_countries=["R"])
        with pytest.raises(ValueError):
            geo.configure_geo(deny_countries=["RUS"])
        with pytest.raises(ValueError):
            geo.configure_geo(deny_countries=["R1"])

    def test_codes_are_case_and_whitespace_normalized(self):
        geo.configure_geo(deny_countries=[" ru ", "cN", "IR"])
        assert geo.effective_policy()["deny_countries"] == ["RU", "CN", "IR"]

    def test_bad_unknown_posture_raises(self):
        with pytest.raises(ValueError):
            geo.configure_geo(deny_countries=["RU"], unknown="maybe")

    def test_non_callable_resolver_raises(self):
        with pytest.raises(TypeError):
            geo.configure_geo(deny_countries=["RU"], resolver="not-callable")

    def test_empty_denylist_means_unconfigured(self):
        """The byte-identical rule's hinge: an empty list is a no-op."""
        geo.configure_geo(deny_countries=[])
        assert geo.is_configured() is False
        assert geo.gate("/", {"cf-ipcountry": "RU"}) is None

    def test_reset_restores_unconfigured(self):
        geo.configure_geo(deny_countries=["RU"])
        assert geo.is_configured() is True
        geo.reset()
        assert geo.is_configured() is False


# ---------------------------------------------------------------------------
# resolve_country
# ---------------------------------------------------------------------------


class TestResolveCountry:
    @pytest.mark.parametrize(
        "header",
        [
            "cf-ipcountry",
            "cloudfront-viewer-country",
            "x-vercel-ip-country",
            "fastly-geo-country",
            "x-country-code",
        ],
    )
    def test_each_supported_header_resolves(self, header):
        geo.configure_geo(deny_countries=["RU"])
        assert geo.resolve_country({header: "de"}) == "DE"

    def test_precedence_is_cloudflare_first(self):
        geo.configure_geo(deny_countries=["RU"])
        headers = {"x-vercel-ip-country": "US", "cf-ipcountry": "DE"}
        assert geo.resolve_country(headers) == "DE"

    @pytest.mark.parametrize("value", ["XX", "T1", "", "  ", "USA", "1A", "??"])
    def test_sentinels_and_garbage_mean_unknown(self, value):
        geo.configure_geo(deny_countries=["RU"])
        assert geo.resolve_country({"cf-ipcountry": value}) is None

    def test_no_headers_means_unknown(self):
        geo.configure_geo(deny_countries=["RU"])
        assert geo.resolve_country(None) is None
        assert geo.resolve_country({}) is None

    def test_custom_resolver_overrides_headers(self):
        geo.configure_geo(deny_countries=["RU"], resolver=lambda h: "jp")
        assert geo.resolve_country({"cf-ipcountry": "DE"}) == "JP"

    def test_resolver_none_falls_back_to_headers(self):
        geo.configure_geo(deny_countries=["RU"], resolver=lambda h: None)
        assert geo.resolve_country({"cf-ipcountry": "DE"}) == "DE"

    def test_raising_resolver_degrades_to_headers_and_warns_once(self, caplog):
        def broken(headers):
            raise RuntimeError("db offline")

        geo.configure_geo(deny_countries=["RU"], resolver=broken)
        with caplog.at_level(logging.WARNING):
            assert geo.resolve_country({"cf-ipcountry": "DE"}) == "DE"
            geo.resolve_country({"cf-ipcountry": "DE"})
            geo.resolve_country({"cf-ipcountry": "DE"})
        warnings = [r for r in caplog.records if "resolver raised" in r.message]
        assert len(warnings) == 1, "must warn once, not once per request"


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


class TestGate:
    def test_unconfigured_is_none_for_every_input(self):
        assert geo.gate("/", {"cf-ipcountry": "RU"}) is None
        assert geo.gate("/llms.txt", None) is None
        assert geo.gate("/assets/app.css", {}) is None

    def test_denied_country_gets_the_451_shape(self):
        geo.configure_geo(deny_countries=["RU", "CN", "IR"])
        result = geo.gate("/", {"cf-ipcountry": "RU"})
        assert result["status"] == 451
        assert result["content_type"] == "text/plain"
        assert result["body"].endswith("\n")
        assert result["body"].count("\n") == 1, "one line, per the owner decision"
        assert result["headers"]["Cache-Control"] == "no-store"
        assert "Link" not in result["headers"]

    def test_policy_url_emits_the_rfc7725_link(self):
        geo.configure_geo(deny_countries=["RU"], policy_url="https://example.com/policy")
        result = geo.gate("/", {"cf-ipcountry": "RU"})
        assert result["headers"]["Link"] == '<https://example.com/policy>; rel="blocked-by"'

    def test_allowed_country_proceeds(self):
        geo.configure_geo(deny_countries=["RU"])
        assert geo.gate("/", {"cf-ipcountry": "US"}) is None

    def test_unknown_default_posture_is_fail_open(self):
        """What keeps health probes, monitoring sweeps and direct-origin
        fetches alive: no resolvable country ⇒ allow, by default."""
        geo.configure_geo(deny_countries=["RU"])
        assert geo.gate("/", None) is None
        assert geo.gate("/", {}) is None
        assert geo.gate("/", {"cf-ipcountry": "XX"}) is None

    def test_unknown_deny_posture_fails_closed(self):
        geo.configure_geo(deny_countries=["RU"], unknown="deny")
        assert geo.gate("/", {})["status"] == 451
        assert geo.gate("/", None)["status"] == 451
        # a resolvable, allowed country still proceeds
        assert geo.gate("/", {"cf-ipcountry": "US"}) is None

    def test_exempt_paths_skip_geo_even_for_denied_countries(self):
        geo.configure_geo(deny_countries=["RU"])
        assert geo.gate("/healthz", {"cf-ipcountry": "RU"}) is None

    def test_exempt_is_exact_match_only(self):
        """/healthz-evil must not ride the exemption."""
        geo.configure_geo(deny_countries=["RU"])
        assert geo.gate("/healthz-evil", {"cf-ipcountry": "RU"})["status"] == 451
        assert geo.gate("/healthz/", {"cf-ipcountry": "RU"})["status"] == 451

    def test_exempt_paths_are_overridable_to_nothing(self):
        geo.configure_geo(deny_countries=["RU"], exempt_paths=())
        assert geo.gate("/healthz", {"cf-ipcountry": "RU"})["status"] == 451

    def test_custom_body_is_honoured(self):
        geo.configure_geo(deny_countries=["RU"], body="Not here.\n")
        assert geo.gate("/", {"cf-ipcountry": "RU"})["body"] == "Not here.\n"


# ---------------------------------------------------------------------------
# The callable seam — what a writable control board wires through
# ---------------------------------------------------------------------------


class TestCallableSeam:
    def test_callable_is_read_per_request(self):
        """The whole point: a store edit takes effect on the NEXT request,
        no restart, no reconfigure."""
        store = {"deny": ["RU"]}
        geo.configure_geo(deny_countries=lambda: store["deny"])

        assert geo.gate("/", {"cf-ipcountry": "CN"}) is None
        store["deny"] = ["RU", "CN"]
        assert geo.gate("/", {"cf-ipcountry": "CN"})["status"] == 451
        store["deny"] = []
        assert geo.gate("/", {"cf-ipcountry": "CN"}) is None

    def test_callable_result_is_normalized(self):
        geo.configure_geo(deny_countries=lambda: [" ru ", "cN"])
        assert geo.gate("/", {"cf-ipcountry": "RU"})["status"] == 451
        assert geo.gate("/", {"cf-ipcountry": "CN"})["status"] == 451

    def test_raising_callable_fails_open_and_warns_once(self, caplog):
        def broken():
            raise OSError("store unreadable")

        geo.configure_geo(deny_countries=broken)
        with caplog.at_level(logging.WARNING):
            assert geo.gate("/", {"cf-ipcountry": "RU"}) is None
            geo.gate("/", {"cf-ipcountry": "RU"})
        warnings = [r for r in caplog.records if "callable raised" in r.message]
        assert len(warnings) == 1

    @pytest.mark.parametrize(
        "returned",
        [
            [{"code": "RU"}],
            [["RU"]],
            [{"RU"}],
            ["RU", {"x": 1}],  # one VALID entry plus a nested object
        ],
    )
    def test_an_unhashable_entry_fails_open_never_500s(self, returned, caplog):
        """Soak finding #1 (2026-08-22): tuple() wraps a nested object
        happily and the HASH into the memo cache raised, escaping the
        seam and 500ing every request on every surface. The suite's
        earlier malformed-entry tests only ever fed bad STRINGS — this
        pins the unhashable shapes, including valid-entry-plus-junk
        (which was still a total outage)."""
        geo.configure_geo(deny_countries=lambda: returned)
        with caplog.at_level(logging.WARNING):
            # must behave exactly as an empty denylist: nobody blocked
            assert geo.gate("/", {"cf-ipcountry": "RU"}) is None
            assert geo.gate("/llms.txt", {"cf-ipcountry": "RU"}) is None
            assert geo.gate("/assets/x.css", None) is None
        assert any("callable raised" in r.message for r in caplog.records)

    def test_malformed_callable_entries_are_skipped_not_fatal(self, caplog):
        geo.configure_geo(deny_countries=lambda: ["RU", "Russia", 42])
        with caplog.at_level(logging.WARNING):
            assert geo.gate("/", {"cf-ipcountry": "RU"})["status"] == 451
            assert geo.gate("/", {"cf-ipcountry": "US"}) is None

    def test_effective_policy_names_the_source(self):
        geo.configure_geo(deny_countries=["RU"])
        assert geo.effective_policy()["denylist_source"] == "static"

        def my_store():
            return ["RU"]

        geo.configure_geo(deny_countries=my_store)
        assert "my_store" in geo.effective_policy()["denylist_source"]
