"""The `/.well-known/` namespace — and the refusal that makes it worth having.

Measured on three live hosts and reproduced in-process on all three
adapters (2026-09-02): **every** path under `/.well-known/` answered 200
with the Dash app shell. So did `/auth.md`, and `/openapi.json` on the
backends that have no schema. An agent asking for an API catalog, an
agent card or OAuth metadata received a 200 and a web page — the soft-404
class, on the one namespace whose entire purpose is machine discovery.

That is why the guard comes first in this module and first in the
release. A document published here is only trustworthy if its neighbours
refuse: an agent that gets 200 for `/.well-known/anything` learns nothing
from getting 200 for `/.well-known/api-catalog`. Refusing the unknown is
what makes the known worth reading.

What this module does NOT do
----------------------------
No I/O beyond reading a host's `SKILL.md` once at registration, and no
framework types. Every function here returns text and a content type; the
adapters own the routes and the responses, exactly as ``handlers.py``
does. The one deliberate exception is the digest, which must be computed
from bytes that exist on disk — see ``build_agent_skills_index``.

Nothing here invents facts about a host:

* ``service-desc`` appears in the API catalog only where the adapter
  really serves an OpenAPI document (FastAPI). Flask and Quart omit the
  relation rather than point at a 404.
* The MCP server card is served only when the bridge actually registered
  resources; otherwise the path 404s like any other unknown one.
* The skills index is *empty*, never absent, on a host with no
  ``SKILL.md``: an empty list is an answer ("this host publishes no
  skills"), while a 404 would be indistinguishable from a host that has
  never heard of the spec.

Specs, all draft or recent, all named at their version because they will
move: RFC 9727 (api-catalog, `application/linkset+json`), SEP-2127 draft
(MCP server card), agent-skills-discovery v0.2.0.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: Everything below this prefix is ours to answer — with a document if we
#: publish one there, with a 404 if we do not.
WELL_KNOWN_PREFIX = "/.well-known/"

API_CATALOG_PATH = "/.well-known/api-catalog"
MCP_CARD_PATH = "/.well-known/mcp/server-card.json"
AGENT_SKILLS_PATH = "/.well-known/agent-skills/index.json"

#: The health endpoint this fleet's hosts serve. Detected, never assumed —
#: see ``build_api_catalog``.
HEALTH_PATHS: Tuple[str, ...] = ("/healthz", "/health")

#: Two discovery paths that live at the root rather than under
#: `/.well-known/`. Claimed ONLY when nothing else already answers them —
#: FastAPI serves a real `/openapi.json`, and a host may serve its own
#: `/auth.md` once the identity ladder is published.
ROOT_DISCOVERY_PATHS: Tuple[str, ...] = ("/auth.md", "/openapi.json")

#: The documents this package itself publishes under the namespace. A
#: request for one of these reaches its own handler; everything else under
#: the prefix reaches the guard.
PUBLISHED_PATHS: Tuple[str, ...] = (API_CATALOG_PATH, MCP_CARD_PATH, AGENT_SKILLS_PATH)

JSON_TYPE = "application/json"
LINKSET_TYPE = "application/linkset+json"

#: The tier these documents record as. New in 2.10.0 — a consumer that has
#: never heard of it sees an unfamiliar string, which is why `TIERS` is a
#: vocabulary and not an enum.
WELLKNOWN_TIER = "wellknown"

_SKILL_FILENAME = "SKILL.md"


def not_found_body() -> str:
    """The refusal, as bytes.

    Small on purpose, and JSON on purpose: the reader is a program, the
    answer is "no", and the one useful thing to say next is where the
    documents actually are.
    """
    return json.dumps({"error": "not found", "see": "/llms.txt"}, separators=(",", ":")) + "\n"


def not_found_response() -> Dict[str, Any]:
    """A complete 404 for a discovery path, adapter-shaped."""
    return {
        "status": 404,
        "body": not_found_body(),
        "content_type": JSON_TYPE,
        "headers": {"Cache-Control": "no-store"},
    }


def is_well_known_path(path: str) -> bool:
    return (path or "").startswith(WELL_KNOWN_PREFIX)


# ---------------------------------------------------------------------------
# RFC 9727 — /.well-known/api-catalog
# ---------------------------------------------------------------------------


def build_api_catalog(
    app: Any,
    *,
    openapi_path: Optional[str] = None,
    status_path: Optional[str] = None,
) -> str:
    """One linkset naming this host's machine surfaces (RFC 9727).

    The anchor is the host itself, and the relations are the three a
    catalog can honestly assert for a documentation backend:

    * ``service-doc`` → `/llms.txt`, the prose an agent should read;
    * ``service-desc`` → the OpenAPI document, **only where one exists**.
      Flask and Quart hosts omit the relation entirely: pointing
      ``service-desc`` at a path that 404s is worse than having no
      catalog, because it converts "this host has no schema" into "this
      host is broken";
    * ``status`` → the host's health endpoint, and **only when the host
      really registered one**. `/healthz` is a convention of the fleet
      this package grew up in, not a route the package serves, so the
      adapters detect it rather than the builder asserting it. A catalog
      whose ``status`` link 404s is the same lie as a ``service-desc``
      that 404s, and this release exists because that class of lie was
      everywhere in this namespace.

    RFC 9727 §4 wants `application/linkset+json` with a top-level
    ``linkset`` array of anchored objects; each relation is an array of
    ``{"href": ...}`` even when it holds one entry, which is what makes a
    later second entry a non-breaking change for the reader.
    """
    base_url = str(getattr(app, "_base_url", "") or "").rstrip("/")

    def _url(path: str) -> str:
        return f"{base_url}{path}" if base_url else path

    entry: Dict[str, Any] = {
        "anchor": base_url or "/",
        "service-doc": [{"href": _url("/llms.txt"), "type": "text/markdown"}],
    }
    if openapi_path:
        entry["service-desc"] = [{"href": _url(openapi_path), "type": JSON_TYPE}]
    if status_path:
        entry["status"] = [{"href": _url(status_path)}]

    return json.dumps({"linkset": [entry]}, indent=1, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# SEP-2127 draft — /.well-known/mcp/server-card.json
# ---------------------------------------------------------------------------

#: Everything the draft names, in one place, so ratification is one edit.
#: The schema URL and both version strings are expected to move; a rename
#: after ratification should not send anyone hunting through adapters.
MCP_CARD_SCHEMA = "https://modelcontextprotocol.io/schemas/draft/server-card.json"
MCP_CARD_VERSION = "0.1.0"
MCP_PROTOCOL_VERSION = "2025-06-18"


def build_mcp_server_card(app: Any, config: Any = None) -> Optional[str]:
    """The MCP server card, or None when there is no server to describe.

    Generated from what the bridge actually registered — ``add_llms_routes``
    records that on the app — so the card cannot claim a surface the host
    does not run. None means the caller should 404 the path exactly like
    any other unknown discovery path, which is the honest answer and the
    one the guard already gives.

    ``serverInfo`` is the HOST's identity, never the package's: the same
    ``openapi_title`` / ``openapi_version`` knobs that name the OpenAPI
    document name the card, falling back to the Dash app's own title. A
    card that said "dash-improve-my-llms" would name the library instead
    of the site, which is the mistake the OpenAPI identity fix existed to
    stop.
    """
    if not getattr(app, "_dimll_mcp_resources", False):
        return None

    name = (
        getattr(config, "openapi_title", None) or getattr(app, "title", None) or "Dash application"
    )
    version = getattr(config, "openapi_version", None)

    server_info: Dict[str, Any] = {"name": str(name)}
    if version:
        server_info["version"] = str(version)

    base_url = str(getattr(app, "_base_url", "") or "").rstrip("/")
    documentation_url = f"{base_url}/llms.txt" if base_url else "/llms.txt"

    card = {
        "$schema": MCP_CARD_SCHEMA,
        "version": MCP_CARD_VERSION,
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "serverInfo": server_info,
        # The bridge registers each page's prose as a resource and nothing
        # else — no tools, no prompts. Declaring only what is there is the
        # whole point of generating the card rather than writing it.
        "capabilities": {"resources": {}},
        "transport": {"type": "streamable-http"},
        "documentationUrl": documentation_url,
    }
    return json.dumps(card, indent=1, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# agent-skills-discovery v0.2.0 — /.well-known/agent-skills/index.json
# ---------------------------------------------------------------------------

AGENT_SKILLS_SCHEMA = "https://schemas.agentskills.io/discovery/0.2.0/schema.json"


def parse_skill_frontmatter(text: str) -> Dict[str, str]:
    """``name`` and ``description`` from a SKILL.md's YAML frontmatter.

    A deliberately small parser: the package has no YAML dependency and
    this file's frontmatter is two scalar fields by the spec. Anything it
    cannot read yields ``{}`` and the caller falls back — a malformed
    header must not cost a host its whole index.
    """
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("\n")
    block, sep, _ = rest.partition("\n---")
    if not sep:
        return {}

    fields: Dict[str, str] = {}
    for line in block.splitlines():
        key, sep_colon, value = line.partition(":")
        if not sep_colon:
            continue
        key = key.strip().lower()
        if key not in ("name", "description"):
            continue
        value = value.strip().strip("'\"")
        if value:
            fields[key] = value
    return fields


def _assets_folder(app: Any) -> Optional[str]:
    for owner in (getattr(app, "config", None), app):
        folder = getattr(owner, "assets_folder", None)
        if isinstance(folder, str) and folder:
            return folder
    return None


def find_skill_file(app: Any) -> Optional[str]:
    """The host's ``SKILL.md``, if it ships one, or None.

    The assets folder, because that is where Dash already serves static
    files from and therefore where the served bytes live. The package does
    not generate this file: its content is the host's — the template
    writes one per host from that host's own corpus.
    """
    folder = _assets_folder(app)
    if not folder:
        return None
    path = os.path.join(folder, _SKILL_FILENAME)
    return path if os.path.isfile(path) else None


def build_agent_skills_index(app: Any, *, skill_path: Optional[str] = None) -> str:
    """The skills index, with digests computed from the bytes on disk.

    The digest is the point of the spec: it lets an agent cache a skill
    and know when it changed. So it is computed from the file the host
    actually serves, at registration time — not from a build artifact, not
    from the corpus the file was generated from, and never omitted with
    the entry kept.

    A host with no ``SKILL.md`` gets ``"skills": []``. Empty is an answer;
    absent is a mystery.
    """
    skills: List[Dict[str, Any]] = []
    path = skill_path if skill_path is not None else find_skill_file(app)

    if path:
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            digest = hashlib.sha256(raw).hexdigest()
            front = parse_skill_frontmatter(raw.decode("utf-8", "replace"))
            base_url = str(getattr(app, "_base_url", "") or "").rstrip("/")
            url = (
                f"{base_url}/assets/{_SKILL_FILENAME}" if base_url else f"/assets/{_SKILL_FILENAME}"
            )
            entry: Dict[str, Any] = {
                "name": front.get("name") or str(getattr(app, "title", "") or "skill"),
                "type": "skill-md",
                "url": url,
                "digest": f"sha256:{digest}",
            }
            description = front.get("description")
            if description:
                entry["description"] = description
            skills.append(entry)
        except Exception:  # noqa: BLE001
            # Truth or silence, the same rule the size annotations follow:
            # an unreadable SKILL.md yields an empty index rather than an
            # entry whose digest we could not compute.
            logger.debug("SKILL.md could not be read; serving an empty index", exc_info=True)
            skills = []

    return json.dumps({"$schema": AGENT_SKILLS_SCHEMA, "skills": skills}, indent=1) + "\n"


def detect_status_path(claimed_paths: Any) -> Optional[str]:
    """The host's health endpoint, if it registered one this package knows.

    Given the set of route paths the application had before
    ``add_llms_routes`` ran. Returns None when the host serves none, and
    the catalog then omits the ``status`` relation rather than pointing at
    a 404.
    """
    try:
        claimed = set(claimed_paths or ())
    except TypeError:
        return None
    for candidate in HEALTH_PATHS:
        if candidate in claimed:
            return candidate
    return None
