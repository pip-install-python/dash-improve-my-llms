"""The operator control panel — P1 of 2.7.0. Read-only, by decision.

One token-gated GET route (default ``/llms-policy``, registered only when
``LLMSConfig(panel=True)``) rendering the live effective policy of every
surface this package governs: vendor policy (from the SAME
``effective_policies`` fold robots.txt renders from, so the panel cannot
drift from robots.txt), bot-policy flags, tier documents, access-control
state, the geo guardrail, rate/metering posture, and the bulletin.

Why read-only (decided 2026-08-20, affirmed on owner review): package
config is per-process module state; under gunicorn's N workers a mutating
panel is a nondeterministically lying control plane, and a write-capable
endpoint behind one token is a remote policy override. Every section
therefore ends with the copy-paste call that WOULD change it, and the
pid/boot-time footer turns worker divergence into a diagnostic instead of
a mystery. The WRITABLE layer above this floor is the new site's
inherited template control board (boilerplate ≥1.6.0's
``lib/page_visibility.py`` + ``pages/control_board.py``, extended per the
llms satellite migration plan) — wired through the same callable seams
(``configure_geo(deny_countries=...)``, ``RobotsConfig(vendor_policy=...)``)
this panel merely displays.

Gate rules (the /admin lessons, applied):

- Token from ``LLMSConfig(panel_token=...)`` or the ``DIMLL_PANEL_TOKEN``
  env var, read PER REQUEST so rotation needs no redeploy. Unset or empty
  ⇒ **404, unconditionally** — production fails closed.
- Wrong token ⇒ 404 with an unrevealing body: the panel never advertises
  its own existence. It is likewise absent from robots.txt (a Disallow
  line publishes the path), the sitemap, and the llms index — it is not a
  registered page, so the generators never see it.
- Comparison via ``hmac.compare_digest``. Transport: the
  ``X-LLMS-Panel-Token`` header (preferred) or ``?token=`` (browser
  convenience; it lands in access logs — documented).
- Success responses carry ``X-Robots-Tag: noindex, nofollow`` and
  ``Cache-Control: private, no-store``.
- The geo guardrail runs before every route, this one included: a denied
  country's operator gets the 451. Intended — "451 on everything".

Zero dependencies beyond the standard library: pure-string HTML in the
``llms_viewer`` tradition, no Dash Pages, no component library — it works
in any consumer app on any of the three backends.
"""

from __future__ import annotations

import hmac
import html as _stdlib_html
import os
import time
from typing import Any, Dict, List, Mapping, Optional

_BOOT_TIME = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

_STYLE = """
:root { color-scheme: light dark; }
body { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
       max-width: 960px; margin: 0 auto; padding: 24px; line-height: 1.55;
       background: #101014; color: #e6e6ea; }
h1 { font-size: 1.3rem; border-bottom: 1px solid #333; padding-bottom: 8px; }
h2 { font-size: 1.02rem; margin-top: 28px; color: #b3a1f7; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { text-align: left; padding: 4px 10px 4px 0; border-bottom: 1px solid #26262c; }
code, pre { background: #1a1a21; border-radius: 4px; padding: 2px 5px; font-size: 0.85rem; }
pre { padding: 10px; overflow-x: auto; }
.muted { color: #8a8a93; }
.policy-allow { color: #62c073; }
.policy-block { color: #e46a6a; }
.policy-meter { color: #d9a441; }
footer { margin-top: 36px; border-top: 1px solid #333; padding-top: 10px;
         font-size: 0.78rem; color: #8a8a93; }
"""


def _esc(value: Any) -> str:
    return _stdlib_html.escape(str(value), quote=True)


def _expected_token(config: Any) -> str:
    """The configured secret, re-read per request (rotation without redeploy)."""
    explicit = getattr(config, "panel_token", None)
    if explicit:
        return str(explicit)
    return (os.environ.get("DIMLL_PANEL_TOKEN") or "").strip()


def authorized(config: Any, headers: Optional[Mapping[str, str]], query_token: str = "") -> bool:
    """Whether this request may see the panel. Fails closed on everything."""
    expected = _expected_token(config)
    if not expected:
        return False
    presented = ""
    if headers:
        presented = headers.get("x-llms-panel-token") or ""
    if not presented and query_token:
        presented = query_token
    if not isinstance(presented, str) or not presented:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def panel_response_headers() -> Dict[str, str]:
    return {
        "X-Robots-Tag": "noindex, nofollow",
        "Cache-Control": "private, no-store",
    }


def _section(title: str, rows: List[str], change_hint: str = "") -> List[str]:
    out = [f"<h2>{_esc(title)}</h2>"] + rows
    if change_hint:
        out.append(f"<p class='muted'>To change this:</p><pre>{_esc(change_hint)}</pre>")
    return out


def build_panel_html(
    *,
    app: Any,
    config: Any,
    state: Any = None,
    request_headers: Optional[Mapping[str, str]] = None,
) -> str:
    """Render the live effective policy. Pure string, reads config/state only."""
    from . import __version__, access, geo
    from .vendors import VENDORS, effective_policies

    parts: List[str] = [
        f"<style>{_STYLE}</style>",
        "<h1>dash-improve-my-llms — policy panel</h1>",
        "<p class='muted'>Read-only. The writable layer is your site's "
        "control board, wired through the callable seams shown below.</p>",
    ]

    # --- identity ---------------------------------------------------------
    registry_pages = 0
    try:  # dash.page_registry is optional at panel time
        import dash

        registry_pages = len(getattr(dash, "page_registry", {}) or {})
    except Exception:
        pass
    parts += _section(
        "Identity",
        [
            "<table>",
            f"<tr><th>package</th><td>dash-improve-my-llms {_esc(__version__)}</td></tr>",
            "<tr><th>base_url</th>"
            f"<td>{_esc(getattr(app, '_base_url', '') or '(unset)')}</td></tr>",
            f"<tr><th>app title</th><td>{_esc(getattr(app, 'title', '') or '')}</td></tr>",
            f"<tr><th>registered pages</th><td>{registry_pages}</td></tr>",
            "</table>",
        ],
    )

    # --- vendor policy (the anti-drift table) -----------------------------
    # Mirror build_robots_txt exactly: an app with no RobotsConfig attached
    # still serves robots.txt from the DEFAULTS, so the panel must show the
    # defaults too — "no config" here while robots.txt publishes a policy
    # would be the very drift this table exists to make impossible.
    from .robots_generator import RobotsConfig as _RobotsConfig

    attached = getattr(app, "_robots_config", None)
    robots_config = attached or _RobotsConfig()
    if robots_config is not None:
        policies = effective_policies(robots_config)
        rows = [
            "<table><tr><th>vendor</th><th>operator</th><th>class</th>"
            "<th>effective policy</th></tr>"
        ]
        for vendor in VENDORS:
            if not vendor.robots_tokens:
                continue  # never display what robots.txt never names
            policy = policies[vendor.key]
            rows.append(
                f"<tr><td>{_esc(vendor.display)}</td>"
                f"<td>{_esc(vendor.operator)}</td>"
                f"<td>{_esc(vendor.cls)}</td>"
                f"<td class='policy-{_esc(policy)}'>{_esc(policy)}</td></tr>"
            )
        rows.append("</table>")
        rows.append(
            "<p class='muted'>Rendered from the same fold robots.txt renders "
            "from — this table cannot drift from what /robots.txt says.</p>"
        )
        parts += _section(
            "Vendor policy",
            rows,
            'RobotsConfig(vendor_policy={"claudebot": "allow", ...})  '
            "# dict or zero-arg callable",
        )

        flags = {
            "block_ai_training": getattr(robots_config, "block_ai_training", True),
            "block_ai_training_docs": getattr(robots_config, "block_ai_training_docs", False),
            "allow_ai_search": getattr(robots_config, "allow_ai_search", True),
            "allow_traditional": getattr(robots_config, "allow_traditional", True),
            "crawl_delay": getattr(robots_config, "crawl_delay", None),
            "default_unknown_ai": getattr(robots_config, "default_unknown_ai", "allow"),
            "disallowed_paths": getattr(robots_config, "disallowed_paths", []),
        }
        parts += _section(
            "Bot policy flags",
            ["<table>"]
            + [f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in flags.items()]
            + ["</table>"],
        )
    if attached is None:
        parts.append(
            "<p class='muted'>No RobotsConfig is attached to the app — "
            "robots.txt serves the defaults shown above.</p>"
        )

    # --- tiers ------------------------------------------------------------
    parts += _section(
        "Tier documents",
        [
            "<table>",
            f"<tr><th>llms_tiers</th><td>{_esc(getattr(config, 'llms_tiers', True))}</td></tr>",
            "<tr><th>llms_full_max_bytes</th>"
            f"<td>{_esc(getattr(config, 'llms_full_max_bytes', 4_000_000))}</td></tr>",
            "</table>",
        ],
    )

    # --- access state (qualnames only — NEVER invoke request-scoped checks)
    def _qualname(fn: Any) -> str:
        return getattr(fn, "__qualname__", repr(fn)) if fn else "(not set)"

    access_config = access._config  # read-only peek at the module state
    parts += _section(
        "Access control",
        [
            "<table>",
            f"<tr><th>configured</th><td>{_esc(access.is_configured())}</td></tr>",
            f"<tr><th>check</th><td>{_esc(_qualname(access_config.check))}</td></tr>",
            f"<tr><th>gate_doc</th><td>{_esc(_qualname(access_config.gate_doc))}</td></tr>",
            f"<tr><th>offer_doc</th><td>{_esc(_qualname(access_config.offer_doc))}</td></tr>",
            "<tr><th>metering</th>"
            f"<td>{_esc('ON' if access.metering_enabled() else 'off (402 lane dark)')}</td></tr>",
            "</table>",
            "<p class='muted'>Callbacks are shown by name and never invoked "
            "here — access checks are request-scoped.</p>",
        ],
    )

    # --- geo --------------------------------------------------------------
    geo_policy = geo.effective_policy()
    geo_rows = [
        "<table>",
        f"<tr><th>configured</th><td>{_esc(geo_policy['configured'])}</td></tr>",
        "<tr><th>deny_countries</th>"
        f"<td>{_esc(', '.join(geo_policy['deny_countries']) or '(none)')}</td></tr>",
        f"<tr><th>denylist source</th><td>{_esc(geo_policy['denylist_source'])}</td></tr>",
        f"<tr><th>unknown posture</th><td>{_esc(geo_policy['unknown'])}</td></tr>",
        f"<tr><th>resolver</th><td>{_esc(geo_policy['resolver'])}</td></tr>",
        f"<tr><th>exempt paths</th><td>{_esc(', '.join(geo_policy['exempt_paths']))}</td></tr>",
        "</table>",
        # The per-host deployment check GEO.md mandates: an edge-proxied
        # request must show a real country here before the denylist is
        # trusted; "unknown" means the edge is not forwarding the header
        # and the feature is inert.
        "<p>This request resolved to: "
        f"<code>{_esc(geo.explain_resolution(request_headers))}</code></p>",
    ]
    parts += _section(
        "Geo guardrail",
        geo_rows,
        'configure_geo(deny_countries=["RU", "CN"])  # or a zero-arg callable '
        "(your policy store)",
    )

    # --- rate / metering --------------------------------------------------
    ceiling = getattr(config, "rate_limit_per_minute", None)
    parts += _section(
        "Rate limiting",
        [
            "<table>",
            "<tr><th>rate_limit_per_minute</th>"
            f"<td>{_esc(ceiling if ceiling else 'not enabled in this build')}</td></tr>",
            "</table>",
        ],
        "LLMSConfig(rate_limit_per_minute=120)",
    )

    # --- bulletin / network ----------------------------------------------
    network = getattr(state, "network", None) if state is not None else None
    bulletin_state = "(not configured)"
    hub_policy = ""
    try:
        from . import bulletin as _bulletin

        if getattr(_bulletin._config, "enabled", False):
            data = _bulletin.get_bulletin()
            bulletin_state = (
                "configured, cached copy present" if data else "configured, no copy yet"
            )
            if data:
                tightenings = (data.get("network") or {}).get("crawler_policy") or []
                if tightenings:
                    hub_policy = ", ".join(f"{e['vendor']}→{e['policy']}" for e in tightenings)
    except Exception:
        pass
    net_rows = [
        "<table>",
        f"<tr><th>network</th><td>{_esc(getattr(network, 'name', '') or '(none)')}</td></tr>",
        f"<tr><th>hub</th><td>{_esc(getattr(network, 'hub_url', '') or '(none)')}</td></tr>",
        f"<tr><th>bulletin</th><td>{_esc(bulletin_state)}</td></tr>",
    ]
    if hub_policy:
        net_rows.append(f"<tr><th>hub tightenings</th><td>{_esc(hub_policy)}</td></tr>")
    net_rows.append("</table>")
    parts += _section("Network", net_rows)

    # --- footer -----------------------------------------------------------
    parts.append(
        "<footer>worker pid "
        f"{os.getpid()} · booted {_esc(_BOOT_TIME)} · values that flip "
        "between refreshes mean different workers booted with different "
        "code or env — that is a deployment diagnostic, not a panel bug."
        "</footer>"
    )

    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='robots' content='noindex, nofollow'>"
        "<title>dimll policy panel</title></head><body>" + "".join(parts) + "</body></html>"
    )
