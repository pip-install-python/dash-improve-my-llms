"""
The read event — one structured row per document this package serves (2.8.0).

Through 2.7.x the middleware decided everything worth recording — which
vendor asked, whether it was verified, what policy applied, which tier it
got, how many bytes went out — and then discarded all of it. Applications
that wanted bot accounting had no choice but to re-classify the
User-agent themselves, against hand-written lists that drifted from this
package's registry. Every such list is a fourth classifier and a source
of wrong numbers.

So the package now says what it did. One event per document response,
handed to callbacks the application registers:

    from dash_improve_my_llms import on_document_read

    @on_document_read
    def _write(event: dict) -> None:
        db.insert(event)

What this module does NOT do
----------------------------
No I/O. It does not write a file, open a socket, or POST to a hub. It
hands a dict to whatever the application registered and returns. Where
the row is durably written, and whether it is forwarded anywhere, is the
application's decision — the package's job is to stop throwing the
information away.

Fail-open, always
-----------------
A callback that raises is caught, warned about once, and otherwise
ignored. A broken analytics writer must never take the corpus down; this
is the same rule ``_rate_limit`` follows, and for the same reason — the
documents exist to be read, and a bookkeeping failure is not a reason to
stop serving them.
"""

import time
import warnings
from typing import Any, Callable, Dict, List, Optional

# Every field the event carries, in a fixed order. Declared once so that
# emit_read() can guarantee the shape: a consumer that sees a key on one
# host and not another cannot build a table, so ALL keys are always
# present and None means "not known here", never "not applicable".
EVENT_FIELDS = (
    "ts",
    "host",
    "path",
    "method",
    "tier",
    "lane",
    "bot_type",
    "vendor_key",
    # 2.9.2: `classify()` has always computed the vendor's class and
    # `build_event` has always had it in hand — it simply never made it
    # into the event. A consumer storing `{k: event[k] for k in
    # EVENT_FIELDS}` therefore dropped it at the app boundary on every
    # host, and every rollup's per-vendor class was null. None when no
    # vendor matched, which is a real answer: a generic `bot` token gives
    # a bot_type without saying whose.
    "vendor_class",
    "verified",
    "policy",
    "verdict",
    "status",
    "bytes",
    "ua",
    "client_ip",
)

# What `tier` may say. Named rather than free-form so a rollup can group
# on it without a per-host mapping.
# `wellknown` is new in 2.10.0 — the /.well-known/ documents (API
# catalog, MCP server card, agent-skills index) are corpus reads too: an
# agent discovering the host is a reader, and a ledger that only counted
# the prose would show the discovery as nothing at all. A consumer that
# has never heard of the name sees an unfamiliar string, which is why
# this is a vocabulary and not an enum.
TIERS = ("small", "index", "full", "page", "html", "policy", "sitemap", "wellknown")

# What `verdict` may say — the outcome, not the status code, because the
# same 200 covers "served the corpus" and "served a payment offer".
VERDICTS = ("served", "priced", "gated", "denied", "blocked", "rate_limited")

# How a status code reads as a verdict, for the document routes where the
# handler does not already know one. `gated` and `priced` are NOT derivable
# here — a gate document and a payment offer both go out at 200 — so the
# sites that produce them name their verdict explicitly.
_VERDICT_BY_STATUS = {
    200: "served",
    402: "priced",
    403: "blocked",
    404: "denied",
    429: "rate_limited",
}


def verdict_for_status(status: int) -> str:
    """Default verdict for a status code. `served` for anything unlisted."""
    return _VERDICT_BY_STATUS.get(int(status), "served")


_callbacks: List[Callable[[Dict[str, Any]], None]] = []

_warned: set = set()

# The UA is truncated before it leaves the package: the field exists to
# identify a client, not to be a log-injection vector or an unbounded
# column.
_UA_MAX = 160


def on_document_read(callback: Callable[[Dict[str, Any]], None]):
    """Register a callback that receives one event per document served.

    Usable as a decorator or called directly. Returns the callback, so
    the decorated name stays bound to the original function.

    The callback receives a plain dict (see ``EVENT_FIELDS``) and its
    return value is ignored. It is called synchronously on the request
    path, so it should be cheap — append to a queue, not fsync a file.
    Exceptions are swallowed.
    """
    if not callable(callback):
        raise TypeError("on_document_read expects a callable")
    if callback not in _callbacks:
        _callbacks.append(callback)
    return callback


def has_listeners() -> bool:
    """True when at least one callback is registered.

    Emission sites check this before assembling an event: with no
    listener — the default for every host that has not opted in — the
    whole path costs one list truth-test.
    """
    return bool(_callbacks)


def _warn_once(message: str) -> None:
    if message in _warned:
        return
    _warned.add(message)
    warnings.warn(message, RuntimeWarning, stacklevel=2)


def build_event(
    *,
    path: str = "",
    method: str = "GET",
    tier: Optional[str] = None,
    lane: Optional[str] = None,
    status: int = 200,
    body: Any = None,
    verdict: str = "served",
    user_agent: str = "",
    headers: Optional[Any] = None,
    classification: Optional[Dict[str, Any]] = None,
    policy: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble one event. Pure — no callbacks, no I/O. Never raises."""
    from ._headers import client_ip as _client_ip

    ip = None
    resolved_host = host
    if headers is not None:
        try:
            ip = _client_ip(headers)
        except Exception:  # noqa: BLE001
            ip = None
        if resolved_host is None:
            try:
                resolved_host = headers.get("host") or headers.get("Host")
            except Exception:  # noqa: BLE001
                resolved_host = None

    if classification is None:
        from .bot_detection import classify

        try:
            classification = classify(user_agent, ip)
        except Exception:  # noqa: BLE001
            classification = {}

    size = 0
    if body is not None:
        try:
            size = len(body.encode("utf-8")) if isinstance(body, str) else len(body)
        except Exception:  # noqa: BLE001
            size = 0

    return {
        "ts": time.time(),
        "host": resolved_host,
        "path": path,
        "method": method,
        "tier": tier,
        "lane": lane or classification.get("lane"),
        "bot_type": classification.get("bot_type"),
        "vendor_key": classification.get("vendor_key"),
        "vendor_class": classification.get("vendor_class"),
        "verified": classification.get("verified", "n/a"),
        "policy": policy,
        "verdict": verdict,
        "status": status,
        "bytes": size,
        "ua": (user_agent or "")[:_UA_MAX],
        "client_ip": ip,
    }


def emit_read(**fields: Any) -> None:
    """Build an event and hand it to every registered callback.

    The single emission point. Adapters and the middleware call this and
    never construct event dicts themselves, so the shape cannot drift
    between the three backends the way the route declarations once did.
    """
    if not _callbacks:
        return
    try:
        event = build_event(**fields)
    except Exception as exc:  # noqa: BLE001
        _warn_once(f"dash-improve-my-llms: could not build a read event ({exc}); skipping.")
        return
    for callback in list(_callbacks):
        try:
            callback(event)
        except Exception as exc:  # noqa: BLE001
            _warn_once(
                f"dash-improve-my-llms: an on_document_read callback raised "
                f"({type(exc).__name__}: {exc}); the response was unaffected "
                f"and further failures from this callback are silent."
            )


def reset() -> None:
    """Drop every registered callback — tests only."""
    _callbacks.clear()
    _warned.clear()
