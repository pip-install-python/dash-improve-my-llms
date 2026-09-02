"""
Generate robots.txt with configurable AI bot policies.

This module provides functionality to generate robots.txt files with
fine-grained control over different types of bots (training, search, traditional).
"""

from typing import Any, List, Optional


class RobotsConfig:
    """Configuration for robots.txt generation."""

    def __init__(
        self,
        block_ai_training: bool = True,
        allow_ai_search: bool = True,
        allow_traditional: bool = True,
        crawl_delay: Optional[int] = None,
        custom_rules: Optional[List[str]] = None,
        disallowed_paths: Optional[List[str]] = None,
        block_ai_training_docs: bool = False,
        vendor_policy: Optional[Any] = None,
        default_unknown_ai: str = "allow",
    ):
        """
        Initialize robots.txt configuration.

        Args:
            block_ai_training: Block AI training data collection bots
            allow_ai_search: Allow AI search and citation bots
            allow_traditional: Allow traditional search engine bots
            crawl_delay: Crawl delay in seconds (rate limiting)
            custom_rules: Additional custom rules to include
            disallowed_paths: Paths to disallow for all bots
            block_ai_training_docs: Extend `block_ai_training` to the corpus
                routes themselves (`/llms.txt`, `/llms-small.txt`,
                `/llms-full.txt`, and the per-page `/<page>/llms.txt`).
                Defaults to False, which is the historical behaviour: those
                documents exist to be read by machines, so blocking a
                training bot from the app's PAGES while still serving it the
                corpus is the deliberate default. Set True when the corpus
                itself is the thing you are protecting. `/robots.txt` and
                `/sitemap.xml` are never gated: robots.txt is where the
                block is announced, and a bot that receives 403 for it
                treats the site as having no rules at all (RFC 9309) — the
                opposite of what blocking is for.
            vendor_policy: Per-vendor overrides — a dict mapping a registry
                vendor key (see ``vendors.VENDORS``) to ``allow`` | ``block``
                | ``meter``, OR a zero-argument callable returning one (the
                reloadable-settings convention: a writable control board
                wires a persisted store through it and an edit takes effect
                on the next request). The SAME map drives the robots.txt
                groups and the middleware, so what the site says and what it
                does are one source. ``meter`` renders as Allow in
                robots.txt (a Disallow would kill the funnel metering
                exists for) and is enforced by the rate limiter once W4
                lands; until then it behaves as allow. Unset reproduces the
                coarse flags exactly.
            default_unknown_ai: Middleware-only posture for every crawler
                with no registry vendor identity — the unenumerated-AI
                residue of defect P2. ``allow`` (default, the historical
                behaviour) | ``block`` | ``meter``. Through 2.8.x it
                covered only the GENERIC patterns
                (``bot``/``crawler``/``spider``/``scraper``); since 2.9.0
                it also covers the UNIDENTIFIED — ``httpx``,
                ``Go-http-client``, an absent User-agent — which 2.8 moved
                onto the crawler lane. Leaving them out meant the one
                class of reader a host cannot enumerate was also the one
                it could not govern. CLI tools (curl, wget,
                python-requests) are deliberately NOT covered: they are
                the paste-into-chat lane. robots.txt cannot address
                unnamed agents, so this knob has no robots rendering.
        """
        self.block_ai_training = block_ai_training
        self.allow_ai_search = allow_ai_search
        self.allow_traditional = allow_traditional
        self.crawl_delay = crawl_delay
        self.custom_rules = custom_rules or []
        self.disallowed_paths = disallowed_paths or []
        self.block_ai_training_docs = block_ai_training_docs
        self.vendor_policy = vendor_policy
        self.default_unknown_ai = default_unknown_ai


def content_signal(config: Any) -> str:
    """The `Content-Signal` value for a config, as `key=yes|no` pairs.

    Cloudflare's Content Signals Policy (CC0, 2025) lets a site state
    three postures that robots.txt itself cannot express: may this content
    be shown in search results, used as input to an AI answer, and used to
    train a model. No crawler honours it yet; stating it costs one line
    and it is the posture this fleet already holds.

    All three are DERIVED, which is the difference between a signal and a
    decoration:

    * ``search`` follows ``allow_traditional`` — a host that disallows
      Googlebot and Bingbot in the groups below must not say `search=yes`
      one line above them.
    * ``ai-input`` follows ``allow_ai_search`` — the named-human fetchers
      and citation crawlers are exactly "AI input".
    * ``ai-train`` follows ``block_ai_training``, inverted: `yes` when
      training is allowed, `no` when it is blocked.

    Cloudflare's own injected default said `ai-train=no`. A host that
    deliberately allows training crawlers so their reads can be attributed
    would have shipped the opposite of its policy by taking that default,
    which is the argument for generating the line from the config that
    also renders the groups.
    """
    allow_search = "yes" if getattr(config, "allow_traditional", True) else "no"
    allow_input = "yes" if getattr(config, "allow_ai_search", True) else "no"
    allow_train = "no" if getattr(config, "block_ai_training", True) else "yes"
    return f"search={allow_search}, ai-input={allow_input}, ai-train={allow_train}"


def _vendor_groups(vendors: list, directive: str) -> list:
    """User-agent groups for the given vendors, one group per robots token.

    Registry order is preserved by the callers — pre-2.7.0 vendors first,
    so existing hosts' robots.txt keeps its familiar shape with 2.7.0's
    additions appended, never interleaved. A vendor with no robots tokens
    (anthropic-legacy) emits nothing; that absence is a hard-won rule and
    is regression-tested.
    """
    lines = []
    for vendor in vendors:
        for token in vendor.robots_tokens:
            lines.extend([f"User-agent: {token}", f"{directive}: /", ""])
    return lines


def generate_robots_txt(
    config: RobotsConfig,
    sitemap_url: str,
    base_url: str,
    mcp_enabled: bool = False,
) -> str:
    """
    Generate robots.txt content based on configuration.

    Args:
        config: Robots.txt configuration
        sitemap_url: Full URL to sitemap.xml
        base_url: Base URL of the application

    Returns:
        Complete robots.txt content
    """

    lines = [
        "# Robots.txt for Dash Application",
        "# Generated by dash-improve-my-llms",
        "# https://pypi.org/project/dash-improve-my-llms/",
        "",
        "# Default policy - allow all standard crawlers",
        "User-agent: *",
        "Allow: /",
    ]

    # Disallowed paths and crawl delay belong INSIDE the `User-agent: *`
    # group — through 2.6.x they were emitted after the blank line that
    # closes it, leaving them orphaned from any group in strict RFC 9309
    # parsers (defect P5). The group now closes after its last directive.
    if config.disallowed_paths:
        for path in config.disallowed_paths:
            lines.append(f"Disallow: {path}")

    if config.crawl_delay:
        lines.append(f"Crawl-delay: {config.crawl_delay}")

    # Content Signals (2.10.0), inside the `*` group and derived from this
    # same config — never hand-typed by a host, because a signal that
    # disagrees with the directives below it is worse than no signal.
    lines.append(f"Content-Signal: {content_signal(config)}")

    lines.append("")

    # Block AI training bots if configured. Groups render from the vendor
    # registry (vendors.py) — the SAME source get_bot_type() classifies
    # from, so what this file says and what the middleware does cannot
    # drift (the construction that killed defects P1/P2/P3). The legacy
    # aliases (anthropic-ai, Claude-Web) are deliberately NOT emitted:
    # claude.ai's user-initiated fetcher honours a disallow on them, so
    # blocking the deprecated names blocks the paste-into-Claude audience
    # while blocking no training — their registry record has no robots
    # tokens.
    # Placement follows the EFFECTIVE directive (W2): a vendor overridden
    # by vendor_policy sits in the section whose directive matches it —
    # the directives are the contract, the section headers are for
    # humans. With vendor_policy unset, membership equals class
    # membership and the output reproduces 2.6.x exactly.
    from .vendors import VENDORS, effective_policies

    policies = effective_policies(config)
    blocked = [v for v in VENDORS if policies[v.key] == "block" and v.cls != "traditional"]
    allowed_ai = [
        v for v in VENDORS if v.cls == "search" and policies[v.key] in ("allow", "meter")
    ] + [
        v
        for v in VENDORS
        if v.cls == "training" and policies[v.key] in ("allow", "meter") and config.vendor_policy
    ]

    if blocked:
        lines.extend(
            [
                "# ==========================================",
                "# Block AI Training Data Collection",
                "# ==========================================",
                "# These bots collect data to train AI models.",
                "# Blocking them prevents your content from being",
                "# used in training datasets without permission.",
                "",
            ]
        )
        lines.extend(_vendor_groups(blocked, "Disallow"))

    # Allow AI search/citation bots. Claude-User fetches when a person
    # asks Claude to read a URL; Claude-SearchBot indexes for citation.
    # The named-human fetchers are the audience llms.txt exists for —
    # never in the training block. A training vendor overridden to
    # allow/meter joins this section (its effective directive is Allow).
    if allowed_ai:
        lines.extend(
            [
                "# ==========================================",
                "# Allow AI Search and Citation Bots",
                "# ==========================================",
                "# These bots help users find your content through",
                "# AI-powered search engines and assistants.",
                "",
            ]
        )
        lines.extend(_vendor_groups(allowed_ai, "Allow"))

    # Traditional search bots. With the default True the block stays
    # comments-only — the engines ride `User-agent: *` exactly as they
    # always have. With False the registry's traditional vendors get real
    # Disallow groups: through 2.6.x the knob only deleted a comment and
    # did nothing (defect P4).
    if config.allow_traditional:
        lines.extend(
            [
                "# ==========================================",
                "# Traditional Search Engines",
                "# ==========================================",
                "# Standard search engine bots are allowed",
                "# by default with the User-agent: * rule above.",
                "",
                "# Googlebot, Bingbot, etc. - covered by *",
                "",
            ]
        )
        # Soak finding #2 (2026-08-22): a per-vendor override on a
        # traditional crawler was ENFORCED by the middleware but never
        # published here — the host 403'd Googlebot while its own
        # robots.txt said Allow via `*`, filling Search Console with
        # errors and pointing the operator at the wrong layer. A vendor
        # with no group of its own is not unregulated, it is governed by
        # `*` — so a blocked one must get a group. This branch now
        # consults the same fold the else-branch always did.
        blocked_traditional = [
            v for v in VENDORS if v.cls == "traditional" and policies[v.key] == "block"
        ]
        if blocked_traditional:
            lines.extend(_vendor_groups(blocked_traditional, "Disallow"))
    else:
        lines.extend(
            [
                "# ==========================================",
                "# Traditional Search Engines — blocked",
                "# ==========================================",
                "",
            ]
        )
        lines.extend(
            _vendor_groups(
                [v for v in VENDORS if v.cls == "traditional" and policies[v.key] == "block"],
                "Disallow",
            )
        )

    # Add custom rules
    if config.custom_rules:
        lines.extend(
            [
                "# ==========================================",
                "# Custom Rules",
                "# ==========================================",
                "",
                *config.custom_rules,
                "",
            ]
        )

    # Always include sitemap reference
    lines.extend(
        [
            "# ==========================================",
            "# Sitemaps and Discovery",
            "# ==========================================",
            f"Sitemap: {sitemap_url}",
            "",
        ]
    )

    # Add helpful links for AI agents
    lines.extend(
        [
            "# ==========================================",
            "# AI-Friendly Documentation",
            "# ==========================================",
            "# For AI agents and LLMs, we provide structured",
            "# documentation in multiple formats:",
            "#",
            f"# {base_url}/llms.txt - LLM-friendly prose documentation",
            f"# {base_url}/sitemap.xml - Complete sitemap",
        ]
    )
    # Only claimed when the resources actually registered. Through 2.9.2
    # these two lines were unconditional, so every host advertised MCP
    # resource endpoints — and no host ran one (measured across the fleet,
    # 2026-08-31). Truth-or-silence applies to the comments as much as to
    # the directives: an agent reads both, and a comment it cannot act on
    # costs it a fetch to find out.
    if mcp_enabled:
        lines.extend(
            [
                "#",
                "# MCP-aware clients can also fetch per-page docs as",
                "# resources via this app's Dash MCP server.",
            ]
        )
    lines.append("")

    return "\n".join(lines)
