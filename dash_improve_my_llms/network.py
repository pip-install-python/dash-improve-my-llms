"""
Cross-host discovery: turning scattered deployments into one legible network.

The problem this solves
-----------------------
Search engines follow links, and links between *hosts* are weak signals at
best. An agent that lands on ``maps.example.com`` has no path to discover
``email.example.com``: separate hosts, no shared crawl graph, no relationship
expressed anywhere in the markup. A model reasoning about an ecosystem of
eighteen packages sees one package, eighteen times over, with no way to know
the others exist.

Per-host ``sitemap.xml`` cannot fix this — a sitemap is scoped to its own
origin by design. So the package emits an explicit, machine-readable
directory instead, in three tiers that mean different things:

``peer``
    Same network, same operator. ``hub.example.com``, ``maps.example.com``,
    ``email.example.com``. These are the crawl graph you actually own.
``affiliated``
    Yours, on its own unrelated domain — a separate product built on the
    same stack, deliberately not presented as part of the primary network.
``external``
    Third-party documentation worth following but not yours — an upstream
    component library, a framework's docs. Listed as references so an agent
    can chase a dependency without guessing URLs.

Keeping the tiers distinct matters. Collapsing them would either overclaim
ownership of third-party sites or bury your own network in a flat list of
links, and both make the directory less trustworthy to whatever is reading
it.
"""

from __future__ import annotations

import html as _stdlib_html
from typing import Any, Dict, List, Optional

__all__ = [
    "NetworkSite",
    "build_directory_markdown",
    "build_directory_section",
    "build_peer_link_tags",
]

TIERS = ("peer", "affiliated", "external")

_TIER_HEADINGS = {
    "peer": "Network",
    "affiliated": "Related projects",
    "external": "External references",
}

_TIER_BLURBS = {
    "peer": (
        "Other applications in this network. Same operator; each one serves "
        "its own `/llms.txt` in this format."
    ),
    "affiliated": (
        "Projects by the same author on their own domains. Built on the same "
        "stack, but not part of the primary network."
    ),
    "external": (
        "Third-party documentation this project depends on or references. "
        "Not affiliated — listed so an agent can follow a dependency "
        "directly instead of searching for it."
    ),
}


class NetworkSite:
    """One entry in the cross-host directory."""

    __slots__ = ("name", "url", "description", "llms_txt", "tier")

    def __init__(
        self,
        name: str,
        url: str,
        description: str = "",
        llms_txt: Optional[str] = None,
        tier: str = "peer",
    ) -> None:
        if tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS!r}, got {tier!r}")

        self.name = name
        self.url = url.rstrip("/")
        self.description = description
        self.tier = tier
        # Default to the conventional location rather than leaving it unset —
        # the whole point of the directory is that a reader never has to guess.
        self.llms_txt = llms_txt or f"{self.url}/llms.txt"

    def as_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "llms_txt": self.llms_txt,
            "tier": self.tier,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"NetworkSite({self.name!r}, {self.url!r}, tier={self.tier!r})"


class NetworkConfig:
    """The registry of sites, plus the network's own identity."""

    def __init__(self) -> None:
        self.name: Optional[str] = None
        self.description: Optional[str] = None
        self.hub_url: Optional[str] = None
        self.wordmark: Any = None
        self.sites: List[NetworkSite] = []

    def add(self, site: NetworkSite) -> None:
        # Re-registering a URL updates it rather than listing it twice; app
        # modules get imported more than once in some deployment layouts.
        for index, existing in enumerate(self.sites):
            if existing.url == site.url and existing.tier == site.tier:
                self.sites[index] = site
                return
        self.sites.append(site)

    def by_tier(self, tier: str) -> List[NetworkSite]:
        return [site for site in self.sites if site.tier == tier]

    @property
    def is_empty(self) -> bool:
        return not self.sites and not self.name


def _get_config(state: Any) -> Optional[NetworkConfig]:
    config = getattr(state, "network", None)
    if config is None or config.is_empty:
        return None
    return config


# ---------------------------------------------------------------------------
# Markdown — for /llms.txt
# ---------------------------------------------------------------------------


def build_directory_markdown(state: Any) -> str:
    """Render the network directory as llms.txt-style Markdown sections."""
    config = _get_config(state)
    if config is None:
        return ""

    lines: List[str] = []

    if config.name:
        lines.append(f"## About {config.name}")
        lines.append("")
        if config.description:
            lines.append(config.description)
            lines.append("")
        if config.hub_url:
            lines.append(
                f"Network index: [{config.hub_url}]({config.hub_url.rstrip('/')}/llms.txt)"
            )
            lines.append("")

    for tier in TIERS:
        sites = config.by_tier(tier)
        if not sites:
            continue

        lines.append(f"## {_TIER_HEADINGS[tier]}")
        lines.append("")
        lines.append(_TIER_BLURBS[tier])
        lines.append("")
        for site in sites:
            suffix = f": {site.description}" if site.description else ""
            lines.append(f"- [{site.name}]({site.url}){suffix}")
            lines.append(f"  - Machine-readable: {site.llms_txt}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# HTML — for the prerendered page body and <head>
# ---------------------------------------------------------------------------


def _esc(value: Any) -> str:
    return _stdlib_html.escape(str(value or ""), quote=True)


def build_directory_section(state: Any) -> List[str]:
    """Render the directory as HTML sections for the prerendered body."""
    config = _get_config(state)
    if config is None:
        return []

    sections: List[str] = []

    for tier in TIERS:
        sites = config.by_tier(tier)
        if not sites:
            continue

        # Third-party links are not endorsements and should not pass ranking
        # signal; own-network links deliberately should.
        rel = ' rel="nofollow noopener"' if tier == "external" else ""

        item_parts = []
        for site in sites:
            blurb = f" — {_esc(site.description)}" if site.description else ""
            item_parts.append(
                f'<li><a href="{_esc(site.url)}"{rel}>{_esc(site.name)}</a>'
                f"{blurb}"
                f' (<a href="{_esc(site.llms_txt)}"{rel}>llms.txt</a>)</li>'
            )
        items = "".join(item_parts)
        sections.append(
            f'<section class="dimll-network" data-tier="{tier}">'
            f"<h2>{_esc(_TIER_HEADINGS[tier])}</h2>"
            f"<p>{_esc(_TIER_BLURBS[tier])}</p>"
            f"<ul>{items}</ul></section>"
        )

    return sections


def build_peer_link_tags(state: Any) -> str:
    """
    Emit <link rel="related"> hints for same-network hosts.

    Only peers get these. `rel="related"` on a third-party reference would
    assert a relationship that doesn't exist.
    """
    config = _get_config(state)
    if config is None:
        return ""

    tags = [
        f'<link data-dimll-prerender="1" rel="related" '
        f'href="{_esc(site.url)}" title="{_esc(site.name)}">'
        for site in config.by_tier("peer")
    ]
    return "\n    ".join(tags)


def build_network_jsonld(state: Any, base_url: str) -> Optional[Dict[str, Any]]:
    """Describe the network as a schema.org Collection of WebSites."""
    config = _get_config(state)
    if config is None:
        return None

    peers = config.by_tier("peer") + config.by_tier("affiliated")
    if not peers:
        return None

    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": config.name or "Related sites",
        "description": config.description or "",
        "url": base_url or "/",
        "hasPart": [
            {
                "@type": "WebSite",
                "name": site.name,
                "url": site.url,
                "description": site.description,
            }
            for site in peers
        ],
    }
