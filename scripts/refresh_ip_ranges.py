#!/usr/bin/env python3
"""
Refresh the shipped crawler IP-range snapshots.

Run this before cutting a release. It fetches each publishing vendor's
own ranges document and writes a normalised snapshot to
``dash_improve_my_llms/_ranges/<vendor>.json``, which the wheel ships and
``_identity.verify()`` reads. The package itself never fetches on the
request path.

    python scripts/refresh_ip_ranges.py            # refresh all
    python scripts/refresh_ip_ranges.py gptbot     # refresh some

A vendor that fails to fetch keeps its existing snapshot: a stale list is
strictly better than a missing one, because a missing one turns every
request from that vendor into ``n/a`` and quietly empties a column of the
ledger.

Only the vendors with a ``ip_ranges_url`` are touched. The rest —
Anthropic's crawlers most notably — publish no ranges at all, so there is
nothing to snapshot and their identity is ``n/a`` by construction, not by
omission.

One file per SNAPSHOT, not per vendor: Google publishes a single document
for its whole common-crawler family and another for its special-case
crawlers, so vendors sharing a ``ranges_key`` are fetched and written
once between them.
"""

import datetime
import gzip
import json
import os
import sys
import urllib.error
import urllib.request
from typing import List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dash_improve_my_llms._identity import parse_prefixes  # noqa: E402
from dash_improve_my_llms.vendors import VENDORS  # noqa: E402

RANGES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dash_improve_my_llms",
    "_ranges",
)

# Some of these endpoints sit behind a CDN that 403s an unset agent, and
# Common Crawl's serves gzip regardless of Accept-Encoding.
_UA = "dash-improve-my-llms/refresh_ip_ranges (+https://pypi.org/project/dash-improve-my-llms/)"


def _fetch(url: str, timeout: int = 30) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def refresh_all(only: Optional[Sequence[str]] = None, quiet: bool = False) -> int:
    """Refresh snapshots. Returns the number of vendors written."""
    os.makedirs(RANGES_DIR, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

    written = 0
    failures: List[str] = []
    seen: set = set()
    for vendor in VENDORS:
        url = getattr(vendor, "ip_ranges_url", None)
        if not url:
            continue
        if only and vendor.key not in only:
            continue
        name = getattr(vendor, "ranges_key", None) or vendor.key
        if name in seen:
            # A later member of a shared family — the first one already
            # fetched and wrote the file they both read.
            continue
        seen.add(name)
        try:
            payload = _fetch(url)
            v4, v6 = parse_prefixes(payload)
            if not v4 and not v6:
                raise ValueError("document parsed but declared no prefixes")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{vendor.key}: {type(exc).__name__}: {exc}")
            continue

        sharers = [
            v.key
            for v in VENDORS
            if (getattr(v, "ranges_key", None) or v.key) == name
            and getattr(v, "ip_ranges_url", None)
        ]
        snapshot = {
            # `vendor` stays the SNAPSHOT's name (a string, as it always
            # was); `vendors` lists everyone who reads it. Additive, so a
            # reader of the old shape is unaffected.
            "vendor": name,
            "vendors": sorted(sharers),
            "source": url,
            "fetched_at": stamp,
            # The upstream document's own timestamp, kept so a reader can
            # tell a stale REFRESH from a stale PUBLICATION — Bingbot's
            # list has not moved since 2024 and that is the vendor's doing.
            "source_created": (
                (payload or {}).get("creationTime") if isinstance(payload, dict) else None
            ),
            "ipv4": sorted(v4),
            "ipv6": sorted(v6),
        }
        path = os.path.join(RANGES_DIR, f"{name}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=1, sort_keys=True)
            handle.write("\n")
        written += 1
        if not quiet:
            label = name if len(sharers) == 1 else f"{name} ({len(sharers)} vendors)"
            print(f"  {label:<28} v4={len(v4):<5} v6={len(v6):<5} {url}")

    if failures and not quiet:
        print("\nkept existing snapshots for:")
        for line in failures:
            print(f"  ! {line}")
    return written


def main(argv: Sequence[str]) -> int:
    only = list(argv[1:]) or None
    if only is not None:
        known = {v.key for v in VENDORS if getattr(v, "ip_ranges_url", None)}
        unknown = [k for k in only if k not in known]
        if unknown:
            print(f"not vendors that publish ranges: {', '.join(unknown)}", file=sys.stderr)
            print(f"choose from: {', '.join(sorted(known))}", file=sys.stderr)
            return 2
    print("refreshing crawler IP-range snapshots")
    written = refresh_all(only=only)
    print(f"\n{written} snapshot(s) written to {RANGES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
