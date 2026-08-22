"""Sliding-window rate limiter for the corpus routes — W4 of 2.7.0.

Scope, deliberately narrow: BOT traffic against the CORPUS routes
(`/llms.txt`, `/llms-small.txt`, `/llms-full.txt`, per-page docs), keyed
on the client IP from the edge headers G0 threads in. The policy routes
(`/robots.txt`, `/sitemap.xml`) are never limited — they are where the
rules themselves are announced, and RFC 9309 reads an unreadable
robots.txt as "no rules at all". Humans are never limited: the stampede
this exists for (2.4M requests for 117 accepted jobs, per the 2026-08-13
multiagent findings) is an agent failure mode, and the 429 + Retry-After
this returns is the machine-readable half of the conduct contract W3
publishes in the document body.

**FAIL OPEN, always.** A limiter bug must never black-hole the corpus —
this is the one place the package's usual fail-closed instinct is wrong:
refusing to serve documents is strictly worse than serving too many.
Every exception in `check()` is swallowed into "not limited".

Per-process state, honestly: gunicorn runs N workers, so the effective
ceiling is N × the configured value. Same caveat as every in-process
cache in this stack; the operator panel's per-worker footer note applies.
The identity exemption ("anonymous" bulk vs keyed agents) arrives with
W5's identity plumbing — key VERIFICATION is application-side, so in
2.7.0 all bot corpus traffic counts. The knob defaults to None (off),
so an un-opted host is byte-identical.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

_WINDOW_S = 60.0

# Memory guard: a crawler sweep from many addresses must not grow the
# bucket table without bound. Beyond this many distinct keys the oldest
# quiet bucket is evicted — at worst an over-ceiling client gets one
# free window after eviction, which fail-open accepts by design.
_MAX_KEYS = 10_000

_lock = threading.Lock()
_buckets: Dict[str, Deque[float]] = {}


def check(key: str, ceiling: int) -> Optional[int]:
    """Record one hit for ``key`` and return Retry-After seconds if over.

    Returns None (not limited) or the whole-second wait until the oldest
    hit in the window expires. Never raises past its own boundary — the
    caller treats any exception as "not limited" too, but this function
    does its own containment first.
    """
    try:
        now = time.monotonic()
        with _lock:
            bucket = _buckets.get(key)
            if bucket is None:
                if len(_buckets) >= _MAX_KEYS:
                    _buckets.pop(next(iter(_buckets)))
                bucket = _buckets[key] = deque()
            cutoff = now - _WINDOW_S
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= ceiling:
                retry = int(bucket[0] + _WINDOW_S - now) + 1
                return max(retry, 1)
            bucket.append(now)
            return None
    except Exception:
        return None  # fail open — see module docstring


def reset() -> None:
    """Drop all buckets. Tests only."""
    with _lock:
        _buckets.clear()
