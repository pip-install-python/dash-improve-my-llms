"""Country guardrail — opt-in denial of whole geographies, at one seam.

The contract (owner decision, 2026-08-20): a denied country receives
**HTTP 451 on EVERYTHING** — app pages, client-side navigation, assets,
the llms.txt family, sitemap, robots, root-icon redirects — humans and
bots alike. The application does not exist for that geography. This is a
deliberate, owner-decided exception to the network's discovery-floor
guardrail (robots/sitemap/root llms.txt otherwise stay public forever):
compliance, not monetization. Do not "fix" it in either direction.

What this is, honestly (docs/GEO.md carries the full trust model): a
**compliance guardrail and uniform-response layer, not a security
boundary**. Country comes from edge headers, and edge headers are exactly
as trustworthy as the edge in front of the origin — a client that reaches
the origin directly can spoof or omit them. Pair with an edge WAF rule
where the block matters adversarially.

Deployment precondition (verified on the fleet 2026-08-22): the host must
be edge-proxied for a country header to exist at all. llms.2plot.dev sits
behind Cloudflare, so ``CF-IPCountry`` reaches the origin; a DNS-only
host resolves every request "unknown" and — under the default
``unknown="allow"`` — ships this feature INERT. Verify per host BEFORE
enabling: the operator panel's "this request resolved to X via <header>"
line is the live check.

Hard rule: **no network lookups in the request path, ever.** The fleet's
analytics tracker has an ip-api fallback that is asynchronous BY DESIGN
(a cache miss returns None and resolves in the background) — useless and
forbidden as a gate. Apps with their own geo-IP database plug it in via
``resolver=``.

Config-surface pattern copied from ``access.py``: module-level config,
keyword-only configure with loud validation, one fold function the seam
calls, warn-once logging, ``reset()`` for tests, and the fail posture
visible in code.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Postures for a request whose country cannot be resolved. "allow" is the
# default and deliberately fail-open: it is what keeps platform health
# checks (no country header), internal monitoring sweeps, and
# direct-to-origin fetches alive on a host that enables geo. The
# fail-closed variant exists for operators whose edge guarantees the
# header on every real request.
UNKNOWN_ALLOW = "allow"
UNKNOWN_DENY = "deny"

_UNKNOWN_POSTURES = (UNKNOWN_ALLOW, UNKNOWN_DENY)

# Edge headers that carry a country code, in resolution order. Cloudflare
# first — the fleet's own edge, verified live. The Fastly pair is
# conventional rather than built-in (operators set it from
# client.geo.country_code); documented as such in docs/GEO.md.
_COUNTRY_HEADERS = (
    "cf-ipcountry",  # Cloudflare
    "cloudfront-viewer-country",  # AWS CloudFront (when forwarded)
    "x-vercel-ip-country",  # Vercel
    "fastly-geo-country",  # Fastly (operator-set)
    "x-country-code",  # generic operator convention
)

# Header values that mean "no usable country": Cloudflare's XX (unknown)
# and T1 (Tor).
_SENTINELS = ("", "XX", "T1")

#: Paths that skip geo entirely, exact-match only. A 451'd health
#: endpoint takes the service down for EVERY country — strictly worse
#: than the guardrail's goal, and a health probe carries no content
#: subject to legal restriction. Overridable, including to ().
DEFAULT_EXEMPT_PATHS = ("/healthz", "/health", "/livez", "/readyz")

_DEFAULT_BODY = (
    "451 Unavailable For Legal Reasons - This service is not available in your region.\n"
)

DenyCountries = Union[Sequence[str], Callable[[], Sequence[str]]]


def _normalize_codes(raw: Sequence[str], *, strict: bool) -> Tuple[str, ...]:
    """Country codes → validated uppercase tuple.

    ``strict`` raises on a malformed entry (config time, static input);
    non-strict skips it with a warn-once (request time, callable input —
    a malformed store entry must not take down the request path).
    """
    out = []
    for entry in raw:
        code = str(entry).strip().upper()
        if len(code) == 2 and code.isalpha():
            out.append(code)
        elif strict:
            raise ValueError(f"configure_geo: {entry!r} is not an ISO 3166-1 alpha-2 country code")
        else:
            _warn_once(f"deny_countries callable produced {entry!r}; entry ignored")
    return tuple(out)


class _GeoConfig:
    __slots__ = (
        "deny_static",
        "deny_callable",
        "unknown",
        "resolver",
        "exempt_paths",
        "body",
        "policy_url",
    )

    def __init__(self) -> None:
        self.deny_static: Tuple[str, ...] = ()
        self.deny_callable: Optional[Callable[[], Sequence[str]]] = None
        self.unknown: str = UNKNOWN_ALLOW
        self.resolver: Optional[Callable[[Mapping[str, str]], Optional[str]]] = None
        self.exempt_paths: Tuple[str, ...] = DEFAULT_EXEMPT_PATHS
        self.body: str = _DEFAULT_BODY
        self.policy_url: str = ""


_config = _GeoConfig()

# Warn-once registry (the access.py idiom): a broken resolver or store
# must log once per message, not once per crawler per request.
_warned: Set[str] = set()

# Memoized normalization for the callable path: (raw tuple) -> validated
# tuple. The callable is evaluated per request (that is the point — a
# writable control board's store edit takes effect on the NEXT request,
# no restart), but re-validating an unchanged denylist is wasted work on
# a hot path.
_callable_cache: Dict[Tuple, Tuple[str, ...]] = {}


def _warn_once(message: str) -> None:
    if message not in _warned:
        _warned.add(message)
        logger.warning("dash-improve-my-llms geo: %s", message)


def configure_geo(
    *,
    deny_countries: DenyCountries,
    unknown: str = UNKNOWN_ALLOW,
    resolver: Optional[Callable[[Mapping[str, str]], Optional[str]]] = None,
    exempt_paths: Optional[Sequence[str]] = None,
    body: Optional[str] = None,
    policy_url: str = "",
) -> None:
    """Deny listed countries on every surface the package touches.

    Args:
        deny_countries: ISO 3166-1 alpha-2 codes (case-insensitive), OR a
            zero-argument callable returning them. A static sequence is
            validated NOW and raises ``ValueError`` on a malformed entry.
            A callable is evaluated on every request — the reloadable
            seam a writable control board wires a persisted store through
            (``configure_geo(deny_countries=policy_store.geo_deny)``);
            its failures degrade warn-once + fail-open, never an error in
            the request path. An empty denylist leaves geo UNCONFIGURED:
            output stays byte-identical to a build without this feature.
        unknown: Posture when no country resolves — ``"allow"`` (default,
            fail-open: health checks, monitoring sweeps and
            direct-to-origin fetches keep working) or ``"deny"`` (only
            for edges that guarantee the header on every real request).
        resolver: Optional ``(lowercase_headers) -> "US" | None``
            override for apps with their own geo-IP database. Takes
            precedence over header scanning. Exceptions degrade to
            unknown, warn-once. Must never do network I/O.
        exempt_paths: Exact-match paths that skip geo entirely. Defaults
            to the conventional health endpoints; pass ``()`` to exempt
            nothing.
        body: Override the one-line 451 body.
        policy_url: If set, emitted as ``Link: <url>; rel="blocked-by"``
            (RFC 7725) so the refusal can cite its policy.
    """
    if callable(deny_countries):
        deny_static: Tuple[str, ...] = ()
        deny_callable: Optional[Callable[[], Sequence[str]]] = deny_countries
    else:
        deny_static = _normalize_codes(deny_countries, strict=True)
        deny_callable = None

    if unknown not in _UNKNOWN_POSTURES:
        raise ValueError(
            f"configure_geo: unknown= must be one of {_UNKNOWN_POSTURES}, got {unknown!r}"
        )
    if resolver is not None and not callable(resolver):
        raise TypeError("configure_geo: resolver must be callable")

    _config.deny_static = deny_static
    _config.deny_callable = deny_callable
    _config.unknown = unknown
    _config.resolver = resolver
    _config.exempt_paths = tuple(exempt_paths) if exempt_paths is not None else DEFAULT_EXEMPT_PATHS
    _config.body = body if body is not None else _DEFAULT_BODY
    _config.policy_url = str(policy_url or "").strip()
    _warned.clear()
    _callable_cache.clear()


def is_configured() -> bool:
    """True when a denylist source exists (static entries or a callable)."""
    return bool(_config.deny_static) or _config.deny_callable is not None


def _deny_set() -> Tuple[str, ...]:
    """The effective denylist for THIS request."""
    if _config.deny_callable is None:
        return _config.deny_static
    try:
        raw = tuple(_config.deny_callable())
    except Exception:
        _warn_once("deny_countries callable raised; treating denylist as empty (fail-open)")
        logger.debug("geo denylist callable failure", exc_info=True)
        return ()
    cached = _callable_cache.get(raw)
    if cached is None:
        cached = _normalize_codes(raw, strict=False)
        _callable_cache.clear()  # one live denylist at a time; no unbounded growth
        _callable_cache[raw] = cached
    return cached


def resolve_country(headers: Optional[Mapping[str, str]]) -> Optional[str]:
    """The request's country code, or None when it cannot be known.

    Resolution order: the custom ``resolver`` (if configured), then the
    edge headers in ``_COUNTRY_HEADERS`` order. Sentinels (``XX``, ``T1``,
    empty, anything not two ASCII letters) mean unknown.
    """
    if headers is None:
        return None

    if _config.resolver is not None:
        try:
            code = _config.resolver(headers)
        except Exception:
            _warn_once("resolver raised; falling back to header resolution")
            logger.debug("geo resolver failure", exc_info=True)
            code = None
        if code is not None:
            code = str(code).strip().upper()
            if len(code) == 2 and code.isalpha() and code not in _SENTINELS:
                return code
            return None

    for name in _COUNTRY_HEADERS:
        raw = (headers.get(name) or "").strip().upper()
        if raw in _SENTINELS:
            continue
        if len(raw) == 2 and raw.isalpha():
            return raw
    return None


def gate(path: str, headers: Optional[Mapping[str, str]]) -> Optional[Dict[str, Any]]:
    """The geo verdict for one request.

    Returns None (proceed) or the full 451 response dict in
    ``handle_bot_request``'s shape. Called as the FIRST statement of the
    enforcement seam — before the asset short-circuit and the bot gate —
    which is what makes "451 on everything" one point with nothing to
    drift.
    """
    if not is_configured():
        return None
    if path in _config.exempt_paths:  # exact match only; /healthz-evil stays blocked
        return None

    deny = _deny_set()
    if not deny:
        return None

    country = resolve_country(headers)
    if country is None:
        if _config.unknown == UNKNOWN_ALLOW:
            return None
    elif country not in deny:
        return None

    # `no-store` is load-bearing: this response varies by country and no
    # Vary token exists for edge geo headers — a shared cache storing one
    # country's 451 would serve it to the world.
    response_headers: Dict[str, str] = {"Cache-Control": "no-store"}
    if _config.policy_url:
        response_headers["Link"] = f'<{_config.policy_url}>; rel="blocked-by"'
    return {
        "status": 451,
        "body": _config.body,
        "content_type": "text/plain",
        "headers": response_headers,
    }


def effective_policy() -> Dict[str, Any]:
    """A read-only snapshot for the operator panel."""
    source = "static"
    if _config.deny_callable is not None:
        source = getattr(_config.deny_callable, "__qualname__", repr(_config.deny_callable))
    return {
        "configured": is_configured(),
        "deny_countries": list(_deny_set()),
        "denylist_source": source,
        "unknown": _config.unknown,
        "resolver": (
            getattr(_config.resolver, "__qualname__", repr(_config.resolver))
            if _config.resolver
            else "headers"
        ),
        "exempt_paths": list(_config.exempt_paths),
        "policy_url": _config.policy_url,
    }


def reset() -> None:
    """Drop all configuration. Tests only."""
    global _config
    _config = _GeoConfig()
    _warned.clear()
    _callable_cache.clear()
