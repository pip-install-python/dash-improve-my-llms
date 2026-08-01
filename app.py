"""
Example app for dash-improve-my-llms 2.0.

Run:
    python app.py

Then visit:
    /                              — Home (overview of the 2.0 package)
    /audiences/mcp-clients         — What MCP clients see (resource directory)
    /audiences/web-crawlers        — What crawlers see + how to configure for them
    /audiences/llm-context         — Copy any page's LLMS_DOC to your clipboard
    /analytics                     — Plotly analytics dashboard (regular Dash page)
    /admin                         — Hidden from sitemap/robots (mark_hidden demo)
    /v200-features                 — Walks through what changed from 1.x

Surfaces the package generates:
    /llms.txt         — site-wide prose, also exposed via dash.mcp on 4.3+
    /<page>/llms.txt  — per-page prose from each page's LLMS_DOC
    /robots.txt       — bot-class access policies
    /sitemap.xml      — generated from dash.page_registry minus hidden pages

The visitor-tracking middleware below is example-only infrastructure
for the /admin dashboard. It's deliberately Flask-specific because
THIS demo runs on Flask — the package itself is backend-agnostic and
dispatches to Flask / FastAPI / Quart adapters at add_llms_routes().
"""

import json
import os
from datetime import datetime
from pathlib import Path

import dash_mantine_components as dmc
from dash import Dash, dcc, html, page_container

from dash_improve_my_llms import (
    RobotsConfig,
    __version__ as DIMLL_VERSION,
    add_llms_routes,
    configure_bulletin,
    mark_hidden,
    register_network,
)
from dash_improve_my_llms.bot_detection import get_bot_type, is_any_bot
from lib.constants import (
    BASE_URL,
    INTERNAL_UA_TOKEN,
    OG_IMAGE_ALT,
    OG_IMAGE_HEIGHT,
    OG_IMAGE_TYPE,
    OG_IMAGE_URL,
    OG_IMAGE_WIDTH,
    SITE_BRAND,
)

# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    # The brand, unversioned. This string is resolve_site_title()'s fallback
    # and the <title> of any page that registers no title of its own. The
    # version lives in the header chip (read live from the package), never in
    # the brand — "dash-improve-my-llms 2.0" sat here well into 2.3.x.
    title=SITE_BRAND,
)
server = app.server


# The document head. TWO RULES, both learned the hard way on this network:
#
# 1. Declare ONLY what Dash does not emit itself. dash.register_page() makes
#    Dash generate `description`, `og:type/title/description/image` and the
#    full `twitter:*` set per page (dash/_pages.py `_page_meta_tags`). A
#    static copy here makes two of each, describes the SITE where Dash's
#    describes the PAGE, and — because scrapers take the LAST tag — an empty
#    Dash tag wins over a careful static one. This host shipped exactly that:
#    empty og:image/twitter:image beat the template until every register_page
#    call passed image_url= and description=. What stays static is the set
#    Dash omits: og:url, og:site_name, the og:image:* auxiliaries and
#    twitter:image:alt.
#
# 2. Never name a Dash placeholder inside a comment. Dash resolves the
#    percent-brace tokens by plain string replacement over the whole
#    index_string, comments included — a commented mention emits the block
#    twice (bit dash-email; tests/test_social_card.py guards it here).
#
# Only /llms.txt is advertised as the machine-readable surface — /page.json
# and /architecture.* are gone in 2.0.
_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}

        <link rel="alternate" type="text/markdown" href="/llms.txt" title="LLM-friendly documentation">
        <link rel="sitemap" type="application/xml" href="/sitemap.xml">
        <meta name="author" content="Pip Install Python LLC">

        <meta property="og:url" content="__BASE_URL__/">
        <meta property="og:site_name" content="__BRAND__">
        <meta property="og:image:secure_url" content="__OG_IMAGE_URL__">
        <meta property="og:image:type" content="__OG_IMAGE_TYPE__">
        <meta property="og:image:width" content="__OG_IMAGE_WIDTH__">
        <meta property="og:image:height" content="__OG_IMAGE_HEIGHT__">
        <meta property="og:image:alt" content="__OG_IMAGE_ALT__">
        <meta name="twitter:image:alt" content="__OG_IMAGE_ALT__">

        <link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon/favicon-32x32.png">
        <link rel="icon" type="image/png" sizes="16x16" href="/assets/favicon/favicon-16x16.png">
        <link rel="apple-touch-icon" sizes="180x180" href="/assets/favicon/apple-touch-icon.png">
        <link rel="manifest" href="/assets/favicon/site.webmanifest">
        <meta name="theme-color" content="#12B886">

        <script>
        // og:url above is static, so after any client-side route change it
        // advertises the entry page; twitter:url is built by Dash from the
        // landing request and frozen there; the canonical link is injected
        // per page server-side and goes stale the same way. Dash routes via
        // history.pushState, which fires no event — so correct all three on
        // navigation. The origin is read from the og:url tag rather than
        // location.origin: the Render hostname keeps resolving after the
        // custom domain is attached, and hits on it must consolidate.
        (function () {
            var declared = document.querySelector('meta[property="og:url"]');
            var ORIGIN;
            try {
                ORIGIN = new URL(declared.content).origin;
            } catch (e) {
                return;
            }

            function sync() {
                var path = location.pathname.replace(/\\/+$/, '') || '/';
                var href = ORIGIN + (path === '/' ? '/' : path);
                document.querySelectorAll(
                    'meta[property="og:url"], meta[property="twitter:url"], ' +
                    'link[rel="canonical"]'
                ).forEach(function (el) {
                    if (el.tagName === 'LINK') { el.href = href; }
                    else { el.setAttribute('content', href); }
                });
            }

            sync();

            ['pushState', 'replaceState'].forEach(function (method) {
                var original = history[method];
                history[method] = function () {
                    var result = original.apply(this, arguments);
                    sync();
                    return result;
                };
            });
            window.addEventListener('popstate', sync);
        })();
        </script>

        <noscript>
            <div style="padding: 24px; font-family: sans-serif; max-width: 720px; margin: 0 auto;">
                <h1>__BRAND__</h1>
                <p>This demo is an interactive Dash application. For programmatic access:</p>
                <ul>
                    <li><a href="/llms.txt">LLM-friendly documentation</a></li>
                    <li><a href="/sitemap.xml">Sitemap</a></li>
                    <li><a href="/robots.txt">Robots policy</a></li>
                </ul>
            </div>
        </noscript>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""

app.index_string = (
    _INDEX_TEMPLATE.replace("__BASE_URL__", BASE_URL)
    .replace("__BRAND__", SITE_BRAND)
    .replace("__OG_IMAGE_URL__", OG_IMAGE_URL)
    .replace("__OG_IMAGE_TYPE__", OG_IMAGE_TYPE)
    .replace("__OG_IMAGE_WIDTH__", str(OG_IMAGE_WIDTH))
    .replace("__OG_IMAGE_HEIGHT__", str(OG_IMAGE_HEIGHT))
    .replace("__OG_IMAGE_ALT__", OG_IMAGE_ALT)
)


# Public origin. Drives sitemap.xml, robots.txt, absolute URLs in llms.txt,
# and — most consequentially — the <link rel="canonical"> on every page. A
# stale value here points every canonical at the wrong host and asks search
# engines to deindex this deployment, so lib/constants.py reads it from the
# environment (APP_BASE_URL) with the real production host as the default
# rather than a placeholder.
app._base_url = BASE_URL

# Configure bot-class access policies. RobotsConfig is the package's only
# imperative API for crawler control; everything else flows from this and
# from mark_hidden() calls below.
app._robots_config = RobotsConfig(
    block_ai_training=True,  # GPTBot, CCBot, anthropic-ai, etc.
    allow_ai_search=True,  # ChatGPT-User, ClaudeBot, PerplexityBot
    allow_traditional=True,  # Googlebot, Bingbot, DuckDuckBot
    crawl_delay=10,
    disallowed_paths=["/admin"],
)

# Exclude /admin from sitemap and robots, and 404 it for crawlers. This runs
# BEFORE add_llms_routes so the missing-prose startup warning doesn't name a
# page that is deliberately hidden.
mark_hidden("/admin")

# Declare the cross-host directory. Sitemaps are scoped to one origin, so a
# network spread across hosts has no crawl graph between them; this is what
# supplies one. The three tiers stay separate on purpose — see
# docs/NETWORKS.md and the /networks page.
register_network(
    name="The 2plot network",
    description=(
        "Open-source Dash component libraries and the applications built on "
        "them. Every site serves its own /llms.txt in this format."
    ),
    # The hub chain is deliberately one hop, not a jump to the root.
    #
    #   llms.2plot.dev  ->  2plot.dev  ->  2plot.ai
    #
    # This app is a *.2plot.dev subdomain, so its network index is 2plot.dev
    # (the package/subdomain index). 2plot.dev in turn names 2plot.ai as its
    # own hub_url, which is the network root. Each llms.txt therefore has
    # exactly one unambiguous "up" link, and an agent walks the chain instead
    # of having to guess which of two indexes is authoritative.
    hub_url="https://2plot.dev",
    # Drawn in the llms.txt viewer banner: "2" + morse("plot") + ".ai", which
    # renders 2.--. .-.. --- -.ai as a graphic. Supplied as data because the
    # package itself ships no branding.
    wordmark={
        "morse": "plot",
        "prefix": "2",
        # No period glyph: the morse block already separates the two halves,
        # and a floating dot between them reads as a fifth morse symbol. The
        # accessible label below keeps the real domain for screen readers and
        # for the SVG <title>.
        "suffix": "ai",
        "label": "2plot.ai",
    },
    peers=[
        {
            "name": "2plot.ai",
            "url": "https://2plot.ai",
            "description": "Network root: account origin and the heartbeat.",
        },
        {
            "name": "2plot.dev",
            "url": "https://2plot.dev",
            "description": "Index of every open-source component in the network.",
        },
        {
            "name": "Documentation boilerplate",
            "url": "https://boilerplate.2plot.dev",
            "description": "The markdown-driven docs template these sites use.",
        },
    ],
    affiliated=[
        {
            "name": "Pip Install Python",
            "url": "https://pip-install-python.com",
            "description": "Open-source Dash components, on its own domain.",
        },
    ],
    external=[
        {
            "name": "Dash Mantine Components",
            "url": "https://www.dash-mantine-components.com",
            "description": "The UI component layer this demo app is built with.",
        },
        {
            "name": "Plotly Dash documentation",
            "url": "https://dash.plotly.com",
            "description": "Upstream framework documentation.",
        },
    ],
)

# Opt in to the network bulletin: the tips and announcements panel in the
# llms.txt viewer header, published once by the hub and rendered by every
# satellite. Unset the env var and the banner simply renders without it.
if os.environ.get("NETWORK_BULLETIN_URL"):
    configure_bulletin(
        url=os.environ["NETWORK_BULLETIN_URL"],
        # Sent as ?app=llms. This is what lets the hub target an announcement at
        # this site specifically and — more usefully — see that this site is
        # actually rendering the bulletin rather than merely being deployed.
        # Without it every fetch is attributed to "unknown" in the hub's
        # satellite table. The id is registered in 2plot.dev's
        # lib/network_directory.py as a verified id; keep the two in step.
        app_id="llms",
    )

# Wire up /llms.txt, /robots.txt, /sitemap.xml, the prerender hook, the bot
# middleware, and the MCP bridge. add_llms_routes detects the backend
# (Flask here) and dispatches.
add_llms_routes(app)


# /healthz is the 2plot network convention: the hub's hourly sweep probes it,
# and Render uses it as the service health check. Registered after
# add_llms_routes so it sits behind the bot middleware like every other route,
# but it is excluded from the crawler path because it is not a Dash page.
@server.route("/healthz")
def healthz():
    from flask import jsonify

    import dash

    return jsonify(
        ok=True,
        backend="flask",
        dash_version=dash.__version__,
        base_url=app._base_url,
    )


# -----------------------------------------------------------------------------
# Visitor tracking (example-only — powers the /admin dashboard)
# -----------------------------------------------------------------------------

# Env-overridable so the test suite (and any ephemeral runner) can point the
# ledger at a temp dir instead of appending its own hits to the checked-out
# file, which otherwise shows up in `git status` after every local run.
ANALYTICS_FILE = Path(
    os.environ.get("VISITOR_ANALYTICS_FILE") or Path(__file__).parent / "visitor_analytics.json"
)
_ASSET_MARKERS = (".css", ".js", ".png", ".jpg", ".ico", "_dash", "_reload-hash")

# Paths that are machinery, not visits. /healthz is probed by Render's health
# check and the hub's hourly sweep — counting it would swamp the demo data.
_NON_VISIT_PATHS = ("/healthz",)


def load_analytics():
    if not ANALYTICS_FILE.exists():
        return {
            "visits": [],
            "stats": {k: 0 for k in ("desktop", "mobile", "tablet", "bot", "total")},
        }

    with open(ANALYTICS_FILE, "r") as f:
        data = json.load(f)

    clean_visits = [
        v for v in data.get("visits", []) if not any(m in v.get("path", "") for m in _ASSET_MARKERS)
    ]
    stats = {k: 0 for k in ("desktop", "mobile", "tablet", "bot", "total")}
    for v in clean_visits:
        device = v.get("device_type", "desktop")
        stats[device] = stats.get(device, 0) + 1
        stats["total"] += 1

    return {"visits": clean_visits, "stats": stats}


def save_analytics(data):
    with open(ANALYTICS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def detect_device_type(user_agent: str) -> str:
    ua = user_agent.lower()
    if is_any_bot(user_agent):
        return "bot"
    if any(m in ua for m in ("mobile", "android", "iphone", "ipod")):
        return "mobile"
    if any(m in ua for m in ("tablet", "ipad")):
        return "tablet"
    return "desktop"


def track_visit():
    """Append one visit record to visitor_analytics.json. Flask-specific."""
    from flask import request

    try:
        path = request.path
        if any(m in path for m in _ASSET_MARKERS) or path in _NON_VISIT_PATHS:
            return

        user_agent = request.headers.get("User-Agent", "Unknown")

        # The network's internal-traffic contract: hub sweeps, smoke batteries
        # and sibling satellites identify themselves with this token, and the
        # drop happens AT WRITE TIME — before bot classification — so internal
        # probes never reach the ledger under any category.
        if INTERNAL_UA_TOKEN in user_agent:
            return

        device_type = detect_device_type(user_agent)

        analytics = load_analytics()
        analytics["visits"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "path": path,
                "device_type": device_type,
                "bot_type": get_bot_type(user_agent) if device_type == "bot" else None,
                "user_agent": user_agent[:200],
            }
        )
        analytics["stats"][device_type] += 1
        analytics["stats"]["total"] += 1

        if len(analytics["visits"]) > 1000:
            analytics["visits"] = analytics["visits"][-1000:]

        save_analytics(analytics)
    except Exception as exc:
        print(f"visitor tracking error: {exc}")


@app.server.before_request
def _before_request():
    track_visit()


# -----------------------------------------------------------------------------
# App shell — header, nav, page_container, footer
# -----------------------------------------------------------------------------

_BRAND = "#667eea"

_NAV_LINK_STYLE = {
    "textDecoration": "none",
    "fontWeight": "500",
    "fontSize": "14px",
    "color": "#222",
    "padding": "6px 10px",
    "borderRadius": "6px",
}

_NAV_DOC_LINK_STYLE = {
    "textDecoration": "none",
    "fontSize": "13px",
    "color": "#555",
    "padding": "4px 8px",
    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
}


def _page_link(label: str, href: str, accent: str = "#222") -> dcc.Link:
    return dcc.Link(
        label,
        href=href,
        style={**_NAV_LINK_STYLE, "color": accent},
    )


def _doc_link(label: str, href: str, title: str) -> html.A:
    return html.A(label, href=href, target="_blank", title=title, style=_NAV_DOC_LINK_STYLE)


_HEADER = html.Div(
    [
        html.Div(
            [
                html.Span(
                    # Read live from the package so the chip can never lag a
                    # release the way a hard-coded "v2.0" did.
                    f"v{DIMLL_VERSION}",
                    style={
                        "background": "rgba(255,255,255,0.18)",
                        "padding": "2px 10px",
                        "borderRadius": "10px",
                        "fontSize": "11px",
                        "fontWeight": "600",
                        "letterSpacing": "0.5px",
                        "marginRight": "12px",
                        "verticalAlign": "middle",
                    },
                ),
                html.Span(
                    "dash-improve-my-llms",
                    style={"fontSize": "20px", "fontWeight": "600", "verticalAlign": "middle"},
                ),
            ],
            style={"color": "white"},
        ),
        html.P(
            "Crawler / SEO companion for Dash apps, with a thin MCP bridge for Dash 4.3+.",
            style={
                "margin": "6px 0 0",
                "fontSize": "13px",
                "color": "rgba(255,255,255,0.85)",
            },
        ),
    ],
    style={
        "padding": "18px 28px",
        "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    },
)


_NAV = html.Nav(
    [
        # Left cluster — pages, with the three-audience group prominent
        html.Div(
            [
                _page_link("Home", "/"),
                html.Span(
                    "Audiences:",
                    style={"color": "#999", "fontSize": "12px", "margin": "0 4px 0 12px"},
                ),
                _page_link("MCP", "/audiences/mcp-clients", accent=_BRAND),
                _page_link("Crawlers", "/audiences/web-crawlers", accent=_BRAND),
                _page_link("Paste-to-Chat", "/audiences/llm-context", accent=_BRAND),
                html.Span("·", style={"color": "#ccc", "margin": "0 4px"}),
                _page_link("Analytics", "/analytics"),
                _page_link("Admin", "/admin", accent="#c92a2a"),
                _page_link("v2.0", "/v200-features"),
            ],
            style={"display": "flex", "gap": "4px", "alignItems": "center", "flexWrap": "wrap"},
        ),
        # Right cluster — the three doc surfaces 2.0 actually serves
        html.Div(
            [
                html.Span(
                    "Docs:", style={"color": "#999", "fontSize": "12px", "marginRight": "4px"}
                ),
                _doc_link("/llms.txt", "/llms.txt", "Site-wide prose (LLMS_DOC of home)"),
                _doc_link("/robots.txt", "/robots.txt", "Bot-class access policies"),
                _doc_link("/sitemap.xml", "/sitemap.xml", "Generated from page_registry"),
            ],
            style={"display": "flex", "gap": "2px", "alignItems": "center"},
        ),
    ],
    style={
        "display": "flex",
        "justifyContent": "space-between",
        "alignItems": "center",
        "padding": "10px 28px",
        "background": "#fafafa",
        "borderBottom": "1px solid #e5e5e5",
        "flexWrap": "wrap",
        "gap": "12px",
    },
)


_FOOTER = html.Footer(
    html.Div(
        [
            html.Span(
                [
                    "Built with ",
                    html.A(
                        "Dash",
                        href="https://dash.plotly.com",
                        target="_blank",
                        style={"color": _BRAND},
                    ),
                    " · ",
                    html.A(
                        "dash-improve-my-llms",
                        href="https://github.com/pip-install-python/dash-improve-my-llms",
                        target="_blank",
                        style={"color": _BRAND},
                    ),
                    " · ",
                    html.A(
                        "pip-install-python.com",
                        href="https://pip-install-python.com",
                        target="_blank",
                        style={"color": _BRAND},
                    ),
                ],
                style={"color": "#888", "fontSize": "13px"},
            ),
        ],
        style={"textAlign": "center"},
    ),
    style={
        "padding": "20px",
        "borderTop": "1px solid #eee",
        "marginTop": "40px",
        "background": "#fafafa",
    },
)


app.layout = dmc.MantineProvider(
    html.Div(
        [
            _HEADER,
            _NAV,
            html.Main(
                page_container,
                style={"padding": "0", "maxWidth": "1100px", "margin": "0 auto"},
            ),
            _FOOTER,
        ],
        style={"fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"},
    )
)


if __name__ == "__main__":
    print()
    print(f"dash-improve-my-llms {DIMLL_VERSION} — example app")
    print("--------------------------------------")
    print("Pages:")
    print("  http://localhost:8959/")
    print("  http://localhost:8959/audiences/mcp-clients")
    print("  http://localhost:8959/audiences/web-crawlers")
    print("  http://localhost:8959/audiences/llm-context")
    print("  http://localhost:8959/analytics")
    print("  http://localhost:8959/admin                  (hidden from sitemap/robots)")
    print("  http://localhost:8959/v200-features")
    print()
    print("Generated surfaces:")
    print("  http://localhost:8959/llms.txt")
    print("  http://localhost:8959/<page>/llms.txt")
    print("  http://localhost:8959/robots.txt")
    print("  http://localhost:8959/sitemap.xml")
    print()

    port = int(os.environ.get("PORT", 8959))
    # debug=False when a PORT is injected: that means a real host is running
    # this, and the reloader would fork a second process on the same port.
    app.run(debug="PORT" not in os.environ, host="0.0.0.0", port=port)
