"""
Verified crawler identity — the ledger's key (2.8.0).

``vendors.get_bot_vendor()`` is honest that it matches a substring: any
client can send ``ClaudeBot`` in its User-agent and be counted as
Anthropic. For a ledger whose rows are meant to be shown to the vendors
they name, "who" needs a second factor wherever one is published.

That second factor is the operator's own published IP ranges. Eleven of
the twenty-five registry vendors publish them (see ``Vendor
.ip_ranges_url``); this module answers, for a (vendor, client address)
pair, one of three strings:

    ``verified``    the vendor publishes ranges and the address is in one
    ``unverified``  the vendor publishes ranges and the address is NOT
    ``n/a``         no vendor, or the vendor publishes nothing, or we
                    have no address, or the snapshot is unusable

What this module deliberately does NOT do
-----------------------------------------
It never blocks, never returns a status, and never changes which lane a
request is served on. An impostor sending ``ClaudeBot`` receives exactly
the document the real ClaudeBot receives, plus a ledger row that says
``unverified``. That asymmetry is the whole design: the network decided
the ledger is the asset, not the wall. A verification failure is a fact
to record, not a door to close — and treating it as a door would make
the package's behaviour depend on a third-party JSON file's uptime.

Where the data comes from
-------------------------
A snapshot ships in the wheel (``_ranges/<vendor>.json``), refreshed by
``scripts/refresh_ip_ranges.py`` as part of the release. The request path
never touches the network: a runtime refresh is opt-in via
``configure_identity(refresh=True)``, runs once on first use, and falls
back to the shipped snapshot on any failure. The package gains no
network dependency and no new install requirement.

Every failure mode degrades to ``n/a`` with at most one warning. A
malformed snapshot, an unparseable address, a missing file — none of
them may raise into a request.
"""

import ipaddress
import json
import os
import warnings
from typing import Any, Dict, List, Optional, Tuple

from .vendors import get_vendor

VERIFIED = "verified"
UNVERIFIED = "unverified"
NOT_APPLICABLE = "n/a"

_RANGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ranges")

# vendor key -> (v4 networks, v6 networks). Built once per vendor, on first
# use, and cached for the process: parsing ~1400 CIDRs on every request
# would be the one place this package added measurable latency.
_CACHE: Dict[str, Tuple[List[ipaddress.IPv4Network], List[ipaddress.IPv6Network]]] = {}

_warned: set = set()

_refresh_enabled = False
_refreshed = False


def _warn_once(message: str) -> None:
    if message in _warned:
        return
    _warned.add(message)
    warnings.warn(message, RuntimeWarning, stacklevel=2)


def configure_identity(refresh: bool = False) -> None:
    """Opt in to refreshing the shipped IP-range snapshots at runtime.

    Off by default and off on the request path. When enabled the refresh
    runs once, lazily, the first time a verification needs a vendor whose
    snapshot is not yet loaded — and any failure silently keeps the
    shipped snapshot. Most hosts should leave this alone and take the
    ranges from the release; it exists for long-lived deployments that
    outlast a release cycle.
    """
    global _refresh_enabled, _refreshed
    _refresh_enabled = bool(refresh)
    _refreshed = False


def _snapshot_path(vendor_key: str) -> str:
    return os.path.join(_RANGES_DIR, f"{vendor_key}.json")


def parse_prefixes(payload: object) -> Tuple[List[str], List[str]]:
    """Split a published ranges document into (v4 strings, v6 strings).

    Every operator that publishes — Google, OpenAI, Microsoft, Apple,
    Perplexity, DuckDuckGo, Common Crawl — uses the same shape, a
    ``prefixes`` list of ``{"ipv4Prefix": ...}`` / ``{"ipv6Prefix": ...}``
    objects. That was measured across all eleven URLs in the registry, so
    there is one parser and no per-vendor hint. Anything that does not
    match the shape yields two empty lists rather than an exception.
    """
    if not isinstance(payload, dict):
        return [], []
    prefixes = payload.get("prefixes")
    if not isinstance(prefixes, list):
        return [], []
    v4: List[str] = []
    v6: List[str] = []
    for entry in prefixes:
        if not isinstance(entry, dict):
            continue
        four = entry.get("ipv4Prefix")
        six = entry.get("ipv6Prefix")
        if isinstance(four, str) and four:
            v4.append(four)
        if isinstance(six, str) and six:
            v6.append(six)
    return v4, v6


def _load(vendor_key: str):
    """Networks for a vendor, or None when it has no usable snapshot."""
    if vendor_key in _CACHE:
        return _CACHE[vendor_key]

    path = _snapshot_path(vendor_key)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001 - a bad snapshot is never fatal
        _warn_once(
            f"dash-improve-my-llms: IP-range snapshot for {vendor_key!r} is "
            f"unreadable ({exc}); crawler identity for this vendor will "
            f"report 'n/a'."
        )
        _CACHE[vendor_key] = ([], [])
        return _CACHE[vendor_key]

    # The shipped snapshot is normalised (`ipv4`/`ipv6` lists of CIDR
    # strings) by scripts/refresh_ip_ranges.py. Fall back to the upstream
    # `prefixes` shape so a raw vendor document dropped in by hand also
    # works — it is the same data, and failing on it would be a trap.
    if isinstance(payload, dict) and ("ipv4" in payload or "ipv6" in payload):
        v4_raw = [x for x in (payload.get("ipv4") or []) if isinstance(x, str)]
        v6_raw = [x for x in (payload.get("ipv6") or []) if isinstance(x, str)]
    else:
        v4_raw, v6_raw = parse_prefixes(payload)
    v4: List[ipaddress.IPv4Network] = []
    v6: List[ipaddress.IPv6Network] = []
    bad = 0
    for text in v4_raw:
        try:
            v4.append(ipaddress.IPv4Network(text, strict=False))
        except ValueError:
            bad += 1
    for text in v6_raw:
        try:
            v6.append(ipaddress.IPv6Network(text, strict=False))
        except ValueError:
            bad += 1
    if bad:
        _warn_once(
            f"dash-improve-my-llms: {bad} malformed prefix(es) in the "
            f"IP-range snapshot for {vendor_key!r}; they were skipped."
        )
    _CACHE[vendor_key] = (v4, v6)
    return _CACHE[vendor_key]


def _maybe_refresh() -> None:
    global _refreshed
    if not _refresh_enabled or _refreshed:
        return
    _refreshed = True  # one attempt per process, success or not
    try:
        from scripts.refresh_ip_ranges import refresh_all

        refresh_all(quiet=True)
        _CACHE.clear()
    except Exception:  # noqa: BLE001 - the shipped snapshot is the fallback
        pass


def verify(vendor_key: Optional[str], client_ip: Optional[str]) -> str:
    """Three-state crawler identity for one request.

    Returns ``verified`` / ``unverified`` / ``n/a``. Never raises, never
    blocks, never influences which document is served.
    """
    if not vendor_key or not client_ip:
        return NOT_APPLICABLE

    vendor = get_vendor(vendor_key)
    if vendor is None or not getattr(vendor, "ip_ranges_url", None):
        # The operator publishes nothing to check against. "n/a" is the
        # honest answer; "unverified" would libel a real crawler.
        return NOT_APPLICABLE

    _maybe_refresh()
    networks = _load(vendor_key)
    if not networks:
        return NOT_APPLICABLE
    v4, v6 = networks
    if not v4 and not v6:
        return NOT_APPLICABLE

    try:
        address = ipaddress.ip_address(str(client_ip).strip())
    except ValueError:
        return NOT_APPLICABLE

    if isinstance(address, ipaddress.IPv4Address):
        pool = v4
    else:
        pool = v6
    if not pool:
        # The vendor publishes, but nothing in this address family — we
        # cannot say the address is outside a list that does not exist.
        return NOT_APPLICABLE

    for network in pool:
        if address in network:
            return VERIFIED
    return UNVERIFIED


def snapshot_status() -> Dict[str, Dict[str, object]]:
    """What ranges this install actually has — for panels and diagnostics."""
    from .vendors import VENDORS

    out: Dict[str, Dict[str, object]] = {}
    for vendor in VENDORS:
        url = getattr(vendor, "ip_ranges_url", None)
        if not url:
            continue
        fetched_at = None
        path = _snapshot_path(vendor.key)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                fetched_at = (json.load(handle) or {}).get("fetched_at")
        except Exception:  # noqa: BLE001
            fetched_at = None
        loaded: Tuple[List[Any], List[Any]] = _load(vendor.key) or ([], [])
        out[vendor.key] = {
            "url": url,
            "fetched_at": fetched_at,
            "ipv4": len(loaded[0]),
            "ipv6": len(loaded[1]),
        }
    return out


def reset() -> None:
    """Drop caches — tests only."""
    global _refresh_enabled, _refreshed
    _CACHE.clear()
    _warned.clear()
    _refresh_enabled = False
    _refreshed = False
