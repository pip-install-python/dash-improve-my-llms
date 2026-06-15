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
from datetime import datetime
from pathlib import Path

import dash_mantine_components as dmc
from dash import Dash, dcc, html, page_container

from dash_improve_my_llms import RobotsConfig, add_llms_routes, mark_hidden
from dash_improve_my_llms.bot_detection import get_bot_type, is_any_bot


# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    title="dash-improve-my-llms 2.0",
)
server = app.server


# AI-discovery hints in the document <head>. Notice: only /llms.txt is
# advertised — /page.json and /architecture.* are gone in 2.0.
app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}

        <link rel="alternate" type="text/markdown" href="/llms.txt" title="LLM-friendly documentation">
        <link rel="sitemap" type="application/xml" href="/sitemap.xml">
        <meta name="description" content="dash-improve-my-llms 2.0 — crawler/SEO companion for Dash apps with an MCP bridge for Dash 4.3+.">

        <noscript>
            <div style="padding: 24px; font-family: sans-serif; max-width: 720px; margin: 0 auto;">
                <h1>dash-improve-my-llms 2.0</h1>
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


# Set this to your real production URL — used in /sitemap.xml and /robots.txt.
app._base_url = "https://example.com"

# Configure bot-class access policies. RobotsConfig is the package's only
# imperative API for crawler control; everything else flows from this and
# from mark_hidden() calls below.
app._robots_config = RobotsConfig(
    block_ai_training=True,    # GPTBot, CCBot, anthropic-ai, etc.
    allow_ai_search=True,      # ChatGPT-User, ClaudeBot, PerplexityBot
    allow_traditional=True,    # Googlebot, Bingbot, DuckDuckBot
    crawl_delay=10,
    disallowed_paths=["/admin"],
)

# Wire up /llms.txt, /robots.txt, /sitemap.xml, bot middleware, and the MCP
# bridge. add_llms_routes detects the backend (Flask here) and dispatches.
add_llms_routes(app)

# Exclude /admin from sitemap and robots, and 404 it for crawlers.
mark_hidden("/admin")


# -----------------------------------------------------------------------------
# Visitor tracking (example-only — powers the /admin dashboard)
# -----------------------------------------------------------------------------

ANALYTICS_FILE = Path(__file__).parent / "visitor_analytics.json"
_ASSET_MARKERS = (".css", ".js", ".png", ".jpg", ".ico", "_dash", "_reload-hash")


def load_analytics():
    if not ANALYTICS_FILE.exists():
        return {"visits": [], "stats": {k: 0 for k in ("desktop", "mobile", "tablet", "bot", "total")}}

    with open(ANALYTICS_FILE, "r") as f:
        data = json.load(f)

    clean_visits = [
        v for v in data.get("visits", [])
        if not any(m in v.get("path", "") for m in _ASSET_MARKERS)
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
        if any(m in path for m in _ASSET_MARKERS):
            return

        user_agent = request.headers.get("User-Agent", "Unknown")
        device_type = detect_device_type(user_agent)

        analytics = load_analytics()
        analytics["visits"].append({
            "timestamp": datetime.now().isoformat(),
            "path": path,
            "device_type": device_type,
            "bot_type": get_bot_type(user_agent) if device_type == "bot" else None,
            "user_agent": user_agent[:200],
        })
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
                    "v2.0",
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
                html.Span("Docs:", style={"color": "#999", "fontSize": "12px", "marginRight": "4px"}),
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
                    html.A("Dash", href="https://dash.plotly.com", target="_blank", style={"color": _BRAND}),
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
    print("dash-improve-my-llms 2.0 — example app")
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

    app.run(debug=True, port=8959)
