"""The /.well-known/ namespace — the documents, and the refusal (2.10.0).

The refusal is the load-bearing half. Measured on three live hosts and
reproduced in-process on all three adapters before any of this shipped:
every path under `/.well-known/` answered 200 with the Dash app shell, and
so did `/auth.md`. An agent asking for an API catalog or OAuth metadata
got a web page — so a document published here could not be trusted, no
matter how correct it was, because its neighbours lied.

These are the pure-function tests. The wire behaviour across the three
adapters lives in test_adapters.py.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from dash_improve_my_llms import wellknown


class FakeApp:
    """The three attributes these builders read."""

    def __init__(self, base_url="https://example.com", title="Test App", mcp=False):
        self._base_url = base_url
        self.title = title
        self._dimll_mcp_resources = mcp


class FakeConfig:
    def __init__(self, title=None, version=None):
        self.openapi_title = title
        self.openapi_version = version


# ---------------------------------------------------------------------------
# Item 0 — the refusal
# ---------------------------------------------------------------------------


class TestTheRefusal:
    def test_the_body_is_small_json_that_points_somewhere(self):
        """The reader is a program, the answer is no, and the one useful
        thing left to say is where the documents actually are."""
        payload = json.loads(wellknown.not_found_body())
        assert payload == {"error": "not found", "see": "/llms.txt"}
        assert len(wellknown.not_found_body()) < 120

    def test_the_response_is_404_json_and_uncacheable(self):
        response = wellknown.not_found_response()
        assert response["status"] == 404
        assert response["content_type"] == "application/json"
        assert response["headers"]["Cache-Control"] == "no-store"

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/.well-known/nope", True),
            ("/.well-known/oauth-authorization-server", True),
            ("/.well-known/mcp/server-card.json", True),
            ("/well-known/nope", False),
            ("/llms.txt", False),
            ("/", False),
            ("", False),
        ],
    )
    def test_the_prefix_test_is_exact(self, path, expected):
        assert wellknown.is_well_known_path(path) is expected


# ---------------------------------------------------------------------------
# Item 3 — RFC 9727 api-catalog
# ---------------------------------------------------------------------------


class TestApiCatalog:
    def test_the_shape_is_a_linkset_of_anchored_entries(self):
        catalog = json.loads(wellknown.build_api_catalog(FakeApp()))
        assert list(catalog) == ["linkset"]
        assert isinstance(catalog["linkset"], list) and len(catalog["linkset"]) == 1
        entry = catalog["linkset"][0]
        assert entry["anchor"] == "https://example.com"
        # RFC 9727: every relation is an ARRAY of link objects, even at one
        # entry — which is what makes adding a second one later a
        # non-breaking change for a reader.
        for relation in ("service-doc",):
            assert isinstance(entry[relation], list)
            assert entry[relation][0]["href"].startswith("https://example.com")

    def test_service_doc_points_at_the_prose_and_says_it_is_markdown(self):
        entry = json.loads(wellknown.build_api_catalog(FakeApp()))["linkset"][0]
        assert entry["service-doc"][0]["href"] == "https://example.com/llms.txt"
        assert entry["service-doc"][0]["type"] == "text/markdown"

    def test_service_desc_is_omitted_when_the_host_has_no_openapi(self):
        """Flask and Quart serve no schema. Pointing `service-desc` at a
        path that 404s would turn "this host has no OpenAPI document" into
        "this host is broken", which is worse than saying nothing."""
        entry = json.loads(wellknown.build_api_catalog(FakeApp()))["linkset"][0]
        assert "service-desc" not in entry

    def test_service_desc_appears_when_one_really_exists(self):
        entry = json.loads(wellknown.build_api_catalog(FakeApp(), openapi_path="/openapi.json"))[
            "linkset"
        ][0]
        assert entry["service-desc"][0]["href"] == "https://example.com/openapi.json"
        assert entry["service-desc"][0]["type"] == "application/json"

    def test_status_is_omitted_unless_the_host_really_serves_one(self):
        """`/healthz` is a convention of the fleet, not a route this
        package serves. A `status` link that 404s is the same lie as a
        `service-desc` that 404s."""
        entry = json.loads(wellknown.build_api_catalog(FakeApp()))["linkset"][0]
        assert "status" not in entry

        entry = json.loads(wellknown.build_api_catalog(FakeApp(), status_path="/healthz"))[
            "linkset"
        ][0]
        assert entry["status"][0]["href"] == "https://example.com/healthz"

    def test_the_health_endpoint_is_detected_from_the_hosts_routes(self):
        assert wellknown.detect_status_path({"/", "/healthz", "/llms.txt"}) == "/healthz"
        assert wellknown.detect_status_path({"/", "/health"}) == "/health"
        assert wellknown.detect_status_path({"/", "/llms.txt"}) is None
        assert wellknown.detect_status_path(None) is None

    def test_it_degrades_to_relative_urls_with_no_base_url(self):
        entry = json.loads(wellknown.build_api_catalog(FakeApp(base_url="")))["linkset"][0]
        assert entry["service-doc"][0]["href"] == "/llms.txt"


# ---------------------------------------------------------------------------
# Item 4 — the MCP server card
# ---------------------------------------------------------------------------


class TestMcpServerCard:
    def test_no_card_when_the_bridge_registered_nothing(self):
        """404, exactly like any other unknown discovery path. A card for
        a server that is not running is the failure mode this release
        exists to remove."""
        assert wellknown.build_mcp_server_card(FakeApp(mcp=False)) is None

    def test_the_card_names_the_draft_it_implements(self):
        card = json.loads(wellknown.build_mcp_server_card(FakeApp(mcp=True)))
        assert card["$schema"] == wellknown.MCP_CARD_SCHEMA
        assert card["version"] == wellknown.MCP_CARD_VERSION
        assert card["protocolVersion"] == wellknown.MCP_PROTOCOL_VERSION

    def test_server_info_is_the_hosts_identity_not_the_packages(self):
        """A card that said "dash-improve-my-llms" would name the library
        instead of the site — the same misreading the OpenAPI identity fix
        exists to stop."""
        card = json.loads(wellknown.build_mcp_server_card(FakeApp(mcp=True)))
        assert card["serverInfo"]["name"] == "Test App"

        injected = json.loads(
            wellknown.build_mcp_server_card(
                FakeApp(mcp=True), FakeConfig(title="pannellum.2plot.dev", version="1.6.45")
            )
        )
        assert injected["serverInfo"] == {"name": "pannellum.2plot.dev", "version": "1.6.45"}

    def test_version_is_absent_rather_than_invented(self):
        card = json.loads(wellknown.build_mcp_server_card(FakeApp(mcp=True)))
        assert "version" not in card["serverInfo"]

    def test_it_declares_only_the_capability_the_bridge_provides(self):
        """The bridge registers page prose as resources and nothing else —
        no tools, no prompts. Declaring only what is there is the whole
        reason the card is generated rather than written."""
        card = json.loads(wellknown.build_mcp_server_card(FakeApp(mcp=True)))
        assert card["capabilities"] == {"resources": {}}
        assert card["documentationUrl"] == "https://example.com/llms.txt"


# ---------------------------------------------------------------------------
# Item 5 — the agent-skills index
# ---------------------------------------------------------------------------


SKILL_MD = (
    "---\n"
    "name: dash-leaflet2\n"
    "description: Leaflet 2 maps for Dash.\n"
    "---\n"
    "\n"
    "# Use dash-leaflet2\n"
)


class TestAgentSkillsIndex:
    @pytest.fixture
    def skill_file(self, tmp_path):
        path = tmp_path / "SKILL.md"
        path.write_text(SKILL_MD)
        return str(path)

    def test_an_empty_index_is_an_answer_a_missing_one_is_a_mystery(self):
        index = json.loads(wellknown.build_agent_skills_index(FakeApp(), skill_path=None))
        assert index["$schema"] == wellknown.AGENT_SKILLS_SCHEMA
        assert index["skills"] == []

    def test_the_digest_is_computed_from_the_bytes_on_disk(self, skill_file):
        """The digest is the point of the spec — it is how an agent knows a
        cached skill went stale. Computed from the file the host serves,
        not from the corpus it was generated out of."""
        index = json.loads(wellknown.build_agent_skills_index(FakeApp(), skill_path=skill_file))
        expected = hashlib.sha256(SKILL_MD.encode("utf-8")).hexdigest()
        assert index["skills"][0]["digest"] == f"sha256:{expected}"

    def test_the_entry_carries_the_frontmatter_and_the_served_url(self, skill_file):
        entry = json.loads(wellknown.build_agent_skills_index(FakeApp(), skill_path=skill_file))[
            "skills"
        ][0]
        assert entry["name"] == "dash-leaflet2"
        assert entry["description"] == "Leaflet 2 maps for Dash."
        assert entry["type"] == "skill-md"
        assert entry["url"] == "https://example.com/assets/SKILL.md"

    def test_a_changed_skill_changes_the_digest(self, tmp_path):
        path = tmp_path / "SKILL.md"
        path.write_text(SKILL_MD)
        first = json.loads(wellknown.build_agent_skills_index(FakeApp(), skill_path=str(path)))[
            "skills"
        ][0]["digest"]
        path.write_text(SKILL_MD + "\nOne more line.\n")
        second = json.loads(wellknown.build_agent_skills_index(FakeApp(), skill_path=str(path)))[
            "skills"
        ][0]["digest"]
        assert first != second

    def test_an_unreadable_skill_yields_an_empty_index_not_a_broken_entry(self, tmp_path):
        """Truth or silence, the same rule the size annotations follow: an
        entry whose digest could not be computed is worse than no entry."""
        missing = str(tmp_path / "does-not-exist" / "SKILL.md")
        index = json.loads(wellknown.build_agent_skills_index(FakeApp(), skill_path=missing))
        assert index["skills"] == []

    def test_frontmatter_parsing_is_small_and_forgiving(self):
        assert wellknown.parse_skill_frontmatter(SKILL_MD) == {
            "name": "dash-leaflet2",
            "description": "Leaflet 2 maps for Dash.",
        }
        # No frontmatter, unterminated frontmatter, and junk all yield {}
        assert wellknown.parse_skill_frontmatter("# Just a heading\n") == {}
        assert wellknown.parse_skill_frontmatter("---\nname: x\n") == {}
        assert wellknown.parse_skill_frontmatter("") == {}
        # Quotes are stripped; unknown keys ignored
        assert wellknown.parse_skill_frontmatter('---\nname: "quoted"\nlicense: MIT\n---\n') == {
            "name": "quoted"
        }

    def test_the_name_falls_back_to_the_app_title(self, tmp_path):
        path = tmp_path / "SKILL.md"
        path.write_text("# No frontmatter here\n")
        entry = json.loads(wellknown.build_agent_skills_index(FakeApp(), skill_path=str(path)))[
            "skills"
        ][0]
        assert entry["name"] == "Test App"
        assert "description" not in entry

    def test_find_skill_file_looks_in_the_assets_folder(self, tmp_path):
        class AppWithAssets:
            _base_url = ""
            title = "x"

            class config:
                assets_folder = str(tmp_path)

        assert wellknown.find_skill_file(AppWithAssets()) is None
        (tmp_path / "SKILL.md").write_text(SKILL_MD)
        assert wellknown.find_skill_file(AppWithAssets()) == os.path.join(str(tmp_path), "SKILL.md")
