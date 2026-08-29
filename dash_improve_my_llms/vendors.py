"""The one vendor registry — every bot identity, defined exactly once.

Why this module exists (W1 of the 2.7.0 toll-gate design,
handoff/KICKOFF-dimll-2.5-agent-exchange.md §5):

Through 2.6.x the package carried TWO independent renderings of "who is
this bot and how do we treat it": token lists in ``bot_detection.py`` and
hand-written User-agent groups in ``robots_generator.py``. They drifted,
in both directions, on live hosts:

- **P1** — robots.txt disallowed ``ClaudeBot`` in the training block while
  ``bot_detection`` classified ``claudebot`` as AI *search*: the site told
  ClaudeBot to go away and then served it 200 HTML.
- **P2** — the generic ``bot|crawler|spider`` fallback swallowed every
  unenumerated AI vendor (Amazonbot, Applebot-Extended, meta-externalagent,
  AI2Bot, Diffbot, …), so new vendors defaulted to *allowed* with full
  static HTML.
- **P3** — Claude-User, Claude-SearchBot and Perplexity-User had no
  detection tokens at all while being exactly the named-human fetchers the
  documents exist for.

Both consumers now read THIS list — ``bot_detection.get_bot_type()`` for
classification and ``robots_generator.generate_robots_txt()`` for the
published policy — so agreement holds by construction and the
registry-agreement test pins it forever. Where the two renderings used to
disagree, the resolution is always the same: **robots.txt is the published
promise, and behaviour moves to match it** (ClaudeBot therefore classifies
``training`` as of 2.7.0 — the P1 fix, a deliberate contract change).

Vendor matching runs BEFORE the generic ``bot|crawler|spider`` fallback
(see ``bot_detection``), which is what makes per-vendor policy possible at
all: a vendor the fallback used to swallow now carries its own identity.

``VENDOR ORDER IS LOAD-BEARING`` for robots.txt byte-stability: within a
class, vendors render in list order, and the pre-2.7.0 vendors come first
so existing hosts' robots.txt keeps its familiar shape with new vendors
appended, never interleaved.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

#: Classification vocabulary. ``get_bot_type()`` has answered with these
#: strings since 1.x; the registry keeps that contract.
TRAINING = "training"
SEARCH = "search"
TRADITIONAL = "traditional"

_CLASSES = (TRAINING, SEARCH, TRADITIONAL)


class Vendor:
    """One canonical bot identity.

    Plain class, all attributes assigned in ``__init__`` — the same
    forward-compatible shape as ``RobotsConfig`` (readers use ``getattr``
    with defaults, so adding fields never breaks an old consumer).

    Attributes:
        key: Stable lowercase identifier — the name ``vendor_policy`` maps
            key on, and what ``get_bot_vendor()`` returns.
        display: Human-readable name for panels and documents.
        operator: Who runs it.
        purpose: One line on what the bot does.
        robots_tokens: EXACT-case User-agent tokens emitted in robots.txt,
            in emission order. Empty means "deliberately never named in
            robots.txt" — see ``anthropic-legacy``, whose absence is a
            hard-won rule, not an omission.
        ua_tokens: Lowercase substrings matched against the User-agent
            header. Matching is substring-based, same as 1.x.
        cls: ``training`` | ``search`` | ``traditional``.
        ip_ranges_url: Where this operator PUBLISHES the IP ranges its
            crawler fetches from, or None when it publishes none. Feeds
            ``_identity.verify()`` and ``scripts/refresh_ip_ranges.py``.
            ``None`` is a real answer, not a gap to fill: Anthropic
            publishes no crawler ranges, so ClaudeBot is unverifiable and
            the ledger records ``n/a`` rather than guessing.
        default_policy: What class membership implies before any
            ``vendor_policy`` override: training → governed by
            ``block_ai_training``; search → by ``allow_ai_search``;
            traditional → by ``allow_traditional``.
    """

    __slots__ = (
        "key",
        "display",
        "operator",
        "purpose",
        "robots_tokens",
        "ua_tokens",
        "cls",
        "ip_ranges_url",
    )

    def __init__(
        self,
        key: str,
        display: str,
        operator: str,
        purpose: str,
        robots_tokens: Sequence[str],
        ua_tokens: Sequence[str],
        cls: str,
        ip_ranges_url: Optional[str] = None,
    ) -> None:
        assert cls in _CLASSES, cls
        self.key = key
        self.display = display
        self.operator = operator
        self.purpose = purpose
        self.robots_tokens = tuple(robots_tokens)
        self.ua_tokens = tuple(t.lower() for t in ua_tokens)
        self.cls = cls
        self.ip_ranges_url = ip_ranges_url


# ---------------------------------------------------------------------------
# The registry. Order within a class is robots.txt emission order:
# pre-2.7.0 vendors first (byte-stable for existing hosts), 2.7.0 additions
# after.
# ---------------------------------------------------------------------------

VENDORS: Tuple[Vendor, ...] = (
    # ------------------------------------------------------ training ------
    Vendor(
        "gptbot",
        "GPTBot",
        "OpenAI",
        "Bulk crawler collecting training data.",
        ["GPTBot"],
        ["gptbot"],
        TRAINING,
        ip_ranges_url="https://openai.com/gptbot.json",
    ),
    Vendor(
        "claudebot",
        "ClaudeBot",
        "Anthropic",
        "Bulk crawler. NOT the paste-into-Claude fetcher (that is "
        "Claude-User) — through 2.6.x this classified as 'search' while "
        "robots.txt disallowed it (defect P1); robots.txt was the "
        "published promise, so classification moved to match it in 2.7.0.",
        ["ClaudeBot"],
        ["claudebot"],
        TRAINING,
    ),
    Vendor(
        "ccbot",
        "CCBot",
        "Common Crawl",
        "Web-scale corpus crawler; training datasets are built from it.",
        ["CCBot"],
        ["ccbot"],
        TRAINING,
        ip_ranges_url="https://index.commoncrawl.org/ccbot.json",
    ),
    Vendor(
        "google-extended",
        "Google-Extended",
        "Google",
        "Robots token governing Gemini training use of Googlebot's crawl.",
        ["Google-Extended"],
        ["google-extended"],
        TRAINING,
        ip_ranges_url="https://developers.google.com/static/search/apis/ipranges/googlebot.json",
    ),
    Vendor(
        "facebookbot",
        "FacebookBot",
        "Meta",
        "Meta AI training crawler (legacy token).",
        ["FacebookBot"],
        ["facebookbot"],
        TRAINING,
    ),
    Vendor(
        "omgili",
        "Omgili",
        "Webz.io",
        "Data-feed crawler resold for training.",
        # Two robots tokens, one vendor: both User-agent groups have been
        # emitted since 1.x and stay, in this order. The single UA token
        # "omgili" substring-matches "omgilibot" too.
        ["Omgilibot", "Omgili"],
        ["omgili"],
        TRAINING,
    ),
    Vendor(
        "bytespider",
        "ByteSpider",
        "ByteDance",
        "TikTok/ByteDance training crawler.",
        ["ByteSpider"],
        ["bytespider"],
        TRAINING,
    ),
    Vendor(
        "anthropic-legacy",
        "anthropic-ai / Claude-Web (deprecated)",
        "Anthropic",
        "Deprecated aliases. DELIBERATELY absent from robots.txt: "
        "claude.ai's user-initiated fetcher honours a disallow on these "
        "names, so naming them blocks the paste-into-Claude audience "
        "while blocking no actual training. UA classification only.",
        [],  # never emitted — regression-tested
        ["anthropic-ai", "claude-web"],
        TRAINING,
    ),
    # -------------------------------------------- training, 2.7.0 adds ----
    # The P2 fix: every vendor below used to fall through to the generic
    # `bot` token and land in `traditional` — the branch that gets full
    # static HTML. Enumerated, they carry their own identity and the
    # training-class default.
    Vendor(
        "amazonbot",
        "Amazonbot",
        "Amazon",
        "Amazon's crawler; feeds Alexa answers and model training.",
        ["Amazonbot"],
        ["amazonbot"],
        TRAINING,
    ),
    Vendor(
        "applebot-extended",
        "Applebot-Extended",
        "Apple",
        "Robots token governing Apple Intelligence training use of "
        "Applebot's crawl. Plain Applebot (search) is NOT this vendor and "
        "still rides the generic fallback.",
        ["Applebot-Extended"],
        ["applebot-extended"],
        TRAINING,
        ip_ranges_url="https://search.developer.apple.com/applebot.json",
    ),
    Vendor(
        "meta-externalagent",
        "meta-externalagent",
        "Meta",
        "Meta's current training crawler token.",
        ["meta-externalagent"],
        ["meta-externalagent"],
        TRAINING,
    ),
    Vendor(
        "ai2bot",
        "AI2Bot",
        "Allen Institute for AI",
        "Crawler for open model training corpora.",
        ["AI2Bot"],
        ["ai2bot"],
        TRAINING,
    ),
    Vendor(
        "diffbot",
        "Diffbot",
        "Diffbot",
        "Structured-extraction crawler resold as datasets.",
        ["Diffbot"],
        ["diffbot"],
        TRAINING,
    ),
    Vendor(
        "timpibot",
        "Timpibot",
        "Timpi",
        "Decentralized index crawler.",
        ["Timpibot"],
        ["timpibot"],
        TRAINING,
    ),
    Vendor(
        "imagesiftbot",
        "ImagesiftBot",
        "The Hive",
        "Image-harvesting crawler.",
        ["ImagesiftBot"],
        ["imagesiftbot"],
        TRAINING,
    ),
    # -------------------------------------------------------- search ------
    Vendor(
        "chatgpt-user",
        "ChatGPT-User",
        "OpenAI",
        "Fetches a URL because a person asked ChatGPT to read it.",
        ["ChatGPT-User"],
        ["chatgpt-user"],
        SEARCH,
        ip_ranges_url="https://openai.com/chatgpt-user.json",
    ),
    Vendor(
        "claude-user",
        "Claude-User",
        "Anthropic",
        "Fetches when a person asks Claude to read a URL — the audience "
        "llms.txt exists for. No detection token existed before 2.7.0 "
        "(defect P3).",
        ["Claude-User"],
        ["claude-user"],
        SEARCH,
    ),
    Vendor(
        "claude-searchbot",
        "Claude-SearchBot",
        "Anthropic",
        "Indexes for citation in Claude's search answers.",
        ["Claude-SearchBot"],
        ["claude-searchbot"],
        SEARCH,
    ),
    Vendor(
        "perplexitybot",
        "PerplexityBot",
        "Perplexity",
        "Search index crawler; answers cite the source.",
        ["PerplexityBot"],
        ["perplexitybot"],
        SEARCH,
        ip_ranges_url="https://www.perplexity.com/perplexitybot.json",
    ),
    Vendor(
        "oai-searchbot",
        "OAI-SearchBot",
        "OpenAI",
        "SearchGPT index crawler.",
        ["OAI-SearchBot"],
        ["oai-searchbot"],
        SEARCH,
        ip_ranges_url="https://openai.com/searchbot.json",
    ),
    # ----------------------------------------------- search, 2.7.0 add ----
    Vendor(
        "perplexity-user",
        "Perplexity-User",
        "Perplexity",
        "Fetches a URL because a person asked Perplexity to read it "
        "(named-human fetcher; part of the P3 fix).",
        ["Perplexity-User"],
        ["perplexity-user"],
        SEARCH,
        ip_ranges_url="https://www.perplexity.com/perplexity-user.json",
    ),
    # --------------------------------------------------- traditional ------
    # robots.txt names these ONLY when allow_traditional=False (the P4
    # fix): with the default True they ride `User-agent: *` exactly as
    # they always have, and the block stays comments-only.
    Vendor(
        "googlebot",
        "Googlebot",
        "Google",
        "Google Search crawler.",
        ["Googlebot"],
        ["googlebot"],
        TRADITIONAL,
        ip_ranges_url="https://developers.google.com/static/search/apis/ipranges/googlebot.json",
    ),
    Vendor(
        "bingbot",
        "Bingbot",
        "Microsoft",
        "Bing crawler; also feeds DuckDuckGo and ChatGPT search.",
        ["Bingbot"],
        ["bingbot"],
        TRADITIONAL,
        ip_ranges_url="https://www.bing.com/toolbox/bingbot.json",
    ),
    Vendor(
        "slurp",
        "Slurp",
        "Yahoo",
        "Yahoo Search crawler.",
        ["Slurp"],
        ["slurp"],
        TRADITIONAL,
    ),
    Vendor(
        "duckduckbot",
        "DuckDuckBot",
        "DuckDuckGo",
        "DuckDuckGo crawler.",
        ["DuckDuckBot"],
        ["duckduckbot"],
        TRADITIONAL,
        ip_ranges_url="https://duckduckgo.com/duckduckbot.json",
    ),
)

_BY_KEY: Dict[str, Vendor] = {v.key: v for v in VENDORS}


def get_vendor(key: str) -> Optional[Vendor]:
    """The registry record for ``key``, or None."""
    return _BY_KEY.get(key)


def vendors_of_class(cls: str) -> List[Vendor]:
    """All vendors of one class, in robots.txt emission order."""
    return [v for v in VENDORS if v.cls == cls]


def get_bot_vendor(user_agent: str) -> Optional[str]:
    """The vendor key for a User-agent, or None.

    The vendor-identity primitive the package never had (W1) and every
    later toll-gate item keys on. Substring matching, case-insensitive,
    consistent with 1.x behaviour — and it runs BEFORE the generic
    ``bot|crawler|spider`` fallback in ``bot_detection``, which is the
    property that killed defect P2.
    """
    if not user_agent:
        return None
    ua = user_agent.lower()
    for vendor in VENDORS:
        for token in vendor.ua_tokens:
            if token in ua:
                return vendor.key
    return None


# ---------------------------------------------------------------------------
# W2 — effective per-vendor policy. ONE fold both consumers call:
# robots_generator renders groups from it, handle_bot_request enforces
# from it, so what the site says and what it does are one source.
# ---------------------------------------------------------------------------

POLICY_ALLOW = "allow"
POLICY_BLOCK = "block"
POLICY_METER = "meter"

_POLICIES = (POLICY_ALLOW, POLICY_BLOCK, POLICY_METER)

# Warn-once registry for policy-map failures: a broken callable or a bad
# entry logs once per process, never once per crawler per request.
_policy_warned: set = set()


def _warn_once(message: str) -> None:
    if message not in _policy_warned:
        _policy_warned.add(message)
        import logging

        logging.getLogger(__name__).warning("dash-improve-my-llms vendors: %s", message)


def _overrides(robots_config) -> Dict[str, str]:
    """The vendor_policy map, resolved and validated.

    Accepts a dict OR a zero-arg callable returning one (the same
    reloadable-settings convention as configure_geo's deny_countries — a
    writable control board wires a persisted store through it, and an
    edit takes effect on the next request). Failures degrade the safe
    way: a raising callable or an invalid entry is logged once and
    ignored, falling back to the class defaults.
    """
    raw = getattr(robots_config, "vendor_policy", None)
    if raw is None:
        return {}
    if callable(raw):
        try:
            raw = raw()
        except Exception:
            _warn_once("vendor_policy callable raised; using class defaults (fail-open)")
            return {}
    if not isinstance(raw, dict):
        _warn_once(f"vendor_policy must be a dict, got {type(raw).__name__}; ignored")
        return {}
    out: Dict[str, str] = {}
    for key, value in raw.items():
        policy = str(value).strip().lower()
        if key not in _BY_KEY:
            _warn_once(f"vendor_policy names unknown vendor {key!r}; entry ignored")
        elif policy not in _POLICIES:
            _warn_once(f"vendor_policy[{key!r}] = {value!r} is not one of {_POLICIES}; ignored")
        else:
            out[key] = policy
    return out


def vendor_overrides(robots_config) -> Dict[str, str]:
    """The explicit vendor_policy entries, resolved and validated.

    Public because the middleware needs to know which vendors were
    EXPLICITLY configured: an override to allow/meter serves the crawler
    branch, while a vendor that is merely not-blocked by the coarse flags
    keeps its historical fall-through to the app (the byte-identical
    rule protects flag-only configs)."""
    return _overrides(robots_config)


def effective_policies(robots_config) -> Dict[str, str]:
    """vendor key → ``allow`` | ``block`` | ``meter`` for every vendor.

    Class defaults come from the coarse flags (all read via getattr, so a
    pre-2.7.0 config object is safe): training → ``block_ai_training``,
    search → ``allow_ai_search``, traditional → ``allow_traditional``.
    ``vendor_policy`` entries override per vendor. With no overrides the
    result reproduces the coarse flags exactly — the byte-identical rule.

    ``meter`` means "fetchable under the rate contract": robots.txt
    renders it as Allow (a Disallow would kill the funnel the meter
    exists for), and the middleware treats it as allow until W4's
    limiter slots into the seam.
    """
    block_training = getattr(robots_config, "block_ai_training", True)
    allow_search = getattr(robots_config, "allow_ai_search", True)
    allow_traditional = getattr(robots_config, "allow_traditional", True)
    defaults = {
        TRAINING: POLICY_BLOCK if block_training else POLICY_ALLOW,
        SEARCH: POLICY_ALLOW if allow_search else POLICY_BLOCK,
        TRADITIONAL: POLICY_ALLOW if allow_traditional else POLICY_BLOCK,
    }
    overrides = _overrides(robots_config)
    result = {v.key: overrides.get(v.key, defaults[v.cls]) for v in VENDORS}

    # W6: hub tightenings from the network bulletin. The hub may only make
    # a vendor MORE restrictive (allow < meter < block) — a compromised or
    # misconfigured hub can refuse traffic, never open a host that chose
    # to block. Bulletin failures change nothing (it is optional plumbing).
    try:
        from .bulletin import get_bulletin

        hub_policy = ((get_bulletin() or {}).get("network") or {}).get("crawler_policy") or []
        restrict = {POLICY_ALLOW: 0, POLICY_METER: 1, POLICY_BLOCK: 2}
        for entry in hub_policy:
            key = entry.get("vendor")
            policy = entry.get("policy")
            if key in result and restrict.get(policy, -1) > restrict[result[key]]:
                result[key] = policy
    except Exception:  # noqa: BLE001
        pass
    return result


def ua_tokens_of_class(cls: str) -> List[str]:
    """All UA tokens of one class — the back-compat list material."""
    out: List[str] = []
    for vendor in VENDORS:
        if vendor.cls == cls:
            out.extend(vendor.ua_tokens)
    return out
