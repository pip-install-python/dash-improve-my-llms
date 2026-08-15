"""
Landing page for the dash-improve-my-llms demo app.

Demonstrates the canonical pattern: a module-level LLMS_DOC string
is the canonical prose for this page, served verbatim at /llms.txt and
also registered with dash.mcp as a resource when Dash 4.3+ is detected.
"""

from dash import dcc, html, register_page

from dash_improve_my_llms import __version__ as DIMLL_VERSION, register_page_metadata
from lib.constants import OG_IMAGE_URL, SITE_BRAND, SITE_DESCRIPTION

register_page(
    __name__,
    path="/",
    # `name` labels the navbar link, so it stays "Home"; the site identity
    # (register_page_metadata below, resolve_site_title's input) is the brand.
    name="Home",
    # `title` is what Dash puts in og:title/twitter:title for this page —
    # the headline of every unfurl of the site root.
    title=SITE_BRAND,
    description=SITE_DESCRIPTION,
    # image_url= at EVERY register_page: one missing and Dash emits an empty
    # og:image, and the empty tag, later in document order, wins with scrapers.
    image_url=OG_IMAGE_URL,
)


LLMS_DOC = """\
# dash-improve-my-llms

> Crawler / SEO companion for Dash apps, with a thin MCP bridge.

Video demo: https://youtu.be/sC4IDScKlTA

## What this package is

A small set of HTTP routes and middleware that make a Dash application
legible to the parts of the web that *don't* speak Dash:

- Search-engine and AI crawlers (Googlebot, GPTBot, ClaudeBot, …)
- Users pasting a URL into a chat window for context
- MCP-aware clients on Dash 4.3+

It is intentionally small. Dash 4.3 already ships an MCP server that
exposes layouts and component metadata live over JSON-RPC, so this
package no longer tries to compete on that surface.

## The three audiences

| Audience              | How they talk to your app       | What the package gives them                  |
|-----------------------|---------------------------------|----------------------------------------------|
| MCP clients           | JSON-RPC over Streamable HTTP   | `LLMS_DOC` registered as `dash.mcp` resource |
| Web crawlers          | Plain HTTPS, no JavaScript      | `/robots.txt`, `/sitemap.xml`, static HTML   |
| Paste-into-chat users | One-shot HTTP fetch             | `/llms.txt`, `/<page>/llms.txt` as markdown  |

## What it serves

- `/llms.txt` — the site index: home prose, every page, the network directory
- `/llms-small.txt` — compact briefing for a small context window (2.4.0+)
- `/llms-full.txt` — the full corpus, every page's prose in one document (2.4.0+)
- `/<page>/llms.txt` — that page's `LLMS_DOC`, verbatim
- `/robots.txt` — bot-class access policies via `RobotsConfig`
- `/sitemap.xml` — generated from `dash.page_registry`
- `/favicon.ico` + apple-touch paths — 302 to a `configure_seo()` icon (2.5.0+)
- Static HTML prerender — served to crawlers that hit a normal page URL

Every llms document content-negotiates: agents get raw Markdown, browsers get
the same Markdown rendered (`?raw=1` forces raw). There are no `/page.json`,
`/architecture.txt`, or `/llms.toon` endpoints — 2.0 removed them, and
component-tree introspection lives in Dash 4.3 MCP.

## The LLMS_DOC pattern

Every page module exports a `LLMS_DOC` string. That string is the
literal body of `/<page>/llms.txt`:

```python
# pages/home.py
LLMS_DOC = '''
# Home
...
'''
```

If a page has no `LLMS_DOC`, the package emits a single warning at
`add_llms_routes()` listing the missing pages, and the endpoint returns
a small stub so bots still get a 200.

## Multi-backend support

`add_llms_routes(app)` detects whether `app.server` is Flask, FastAPI,
or Quart and dispatches to the matching adapter. Pick one extra at
install time:

```
pip install dash-improve-my-llms[flask]     # Dash 3.x and earlier
pip install dash-improve-my-llms[fastapi]   # Dash 4.1+
pip install dash-improve-my-llms[quart]     # Dash 4.1+ async
```

## Quick start

```python
from dash import Dash
from dash_improve_my_llms import add_llms_routes, RobotsConfig, mark_hidden

app = Dash(__name__, use_pages=True)
app._base_url = "https://myapp.com"
app._robots_config = RobotsConfig(block_ai_training=True, allow_ai_search=True)

mark_hidden("/admin")
add_llms_routes(app)
```

## Pages in this demo

Each of the three audience cards above has a dedicated demo page:

- `/audiences/mcp-clients` — directory of resources this app registers with dash.mcp
- `/audiences/web-crawlers` — live /robots.txt, RobotsConfig knobs, per-page visibility
- `/audiences/llm-context` — copy any page's LLMS_DOC to your clipboard

Plus a few supporting pages:

- `/analytics` — a regular Dash page (Plotly + callbacks) with its own LLMS_DOC
- `/admin` — hidden via `mark_hidden`, shows visitor analytics
- `/v200-features` — walks through what changed from 1.x
"""


# The name here is the site's public identity: it becomes the H1 of the
# root /llms.txt, which is the first thing an agent fetching this host
# cold ever reads. So it is the package name, NOT "Home" — "Home" stays
# on register_page() above, where it only labels the navbar link. (The
# package also refuses to promote generic labels like "Home" to the index
# title, but every *.2plot.dev site should set this explicitly anyway.)
register_page_metadata(
    path="/",
    # The H1 of /llms.txt and the viewer's brand chip, via resolve_site_title.
    # Unversioned on purpose: a version baked into the identity goes stale
    # (this said "2.0" until 2.3.4 was current).
    name=SITE_BRAND,
    description=SITE_DESCRIPTION,
)


# -----------------------------------------------------------------------------
# Visual layout
# -----------------------------------------------------------------------------

# Shared style chunks
_BRAND = "#667eea"
_INK = "#222"
_MUTED = "#666"

_CARD_STYLE = {
    "background": "white",
    "padding": "20px",
    "borderRadius": "8px",
    "boxShadow": "0 2px 4px rgba(0,0,0,0.08)",
    "border": "1px solid #eee",
}

_HEADING_STYLE = {"color": _INK, "marginTop": "32px"}

_CODE_BLOCK_STYLE = {
    "background": "#1e1e1e",
    "color": "#d4d4d4",
    "padding": "16px 20px",
    "borderRadius": "6px",
    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
    "fontSize": "13px",
    "lineHeight": "1.55",
    "overflowX": "auto",
}


def _audience_card(title: str, channel: str, served: str, accent: str, href: str) -> dcc.Link:
    """Linked audience card — clicking opens the matching /audiences/* demo page."""
    return dcc.Link(
        html.Div(
            [
                html.Div(
                    [
                        html.Span(
                            title,
                            style={"fontWeight": "600", "fontSize": "15px", "color": accent},
                        ),
                        html.Span(
                            "→",
                            style={"float": "right", "color": accent, "fontWeight": "600"},
                        ),
                    ],
                    style={"marginBottom": "6px"},
                ),
                html.Div(
                    channel, style={"fontSize": "13px", "color": _MUTED, "marginBottom": "10px"}
                ),
                html.Div(served, style={"fontSize": "14px", "color": _INK, "lineHeight": "1.5"}),
            ],
            style={
                **_CARD_STYLE,
                "borderTop": f"3px solid {accent}",
                "height": "100%",
                "boxSizing": "border-box",
            },
        ),
        href=href,
        style={"flex": "1", "textDecoration": "none", "color": "inherit", "minWidth": "240px"},
    )


def _route_link(href: str, label: str) -> html.Li:
    return html.Li(
        [
            html.A(href, href=href, target="_blank", style={"fontFamily": "monospace"}),
            html.Span(f" — {label}", style={"color": _MUTED}),
        ],
        style={"marginBottom": "6px"},
    )


def _page_card(emoji: str, name: str, blurb: str, href: str, accent: str = _BRAND) -> html.Div:
    return html.Div(
        [
            html.H3(
                f"{emoji} {name}", style={"fontSize": "17px", "margin": "0 0 8px", "color": accent}
            ),
            html.P(blurb, style={"color": _MUTED, "fontSize": "14px", "minHeight": "42px"}),
            dcc.Link(
                f"Open {name} →",
                href=href,
                style={"fontWeight": "600", "color": accent, "textDecoration": "none"},
            ),
        ],
        style={**_CARD_STYLE, "flex": "1"},
    )


def layout():
    return html.Div(
        [
            # ---------- Hero ----------
            html.Header(
                [
                    html.Div(
                        # Derived, never written: this badge said "v2.0" while
                        # the site served 2.5.x. Version claims on any public
                        # surface come from the installed package.
                        f"v{DIMLL_VERSION}",
                        style={
                            "display": "inline-block",
                            "background": _BRAND,
                            "color": "white",
                            "fontSize": "12px",
                            "fontWeight": "600",
                            "padding": "2px 10px",
                            "borderRadius": "10px",
                            "letterSpacing": "0.5px",
                            "marginBottom": "12px",
                        },
                    ),
                    html.H1(
                        "dash-improve-my-llms",
                        style={"margin": "0 0 8px", "fontSize": "36px", "color": _INK},
                    ),
                    html.P(
                        "Crawler / SEO companion for Dash apps, with a thin MCP bridge for Dash 4.3+.",
                        style={"fontSize": "17px", "color": _MUTED, "marginTop": "0"},
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            # ---------- Video demo ----------
            html.Section(
                html.Div(
                    html.Iframe(
                        src="https://www.youtube.com/embed/sC4IDScKlTA",
                        title="dash-improve-my-llms — video demo",
                        allow=(
                            "accelerometer; autoplay; clipboard-write; encrypted-media; "
                            "gyroscope; picture-in-picture; web-share"
                        ),
                        style={
                            "position": "absolute",
                            "top": "0",
                            "left": "0",
                            "width": "100%",
                            "height": "100%",
                            "border": "0",
                            "borderRadius": "8px",
                        },
                    ),
                    # 16:9 letterbox: the iframe fills an aspect-ratio box so the
                    # player scales with the column instead of a fixed height.
                    style={
                        "position": "relative",
                        "paddingBottom": "56.25%",
                        "height": "0",
                        "borderRadius": "8px",
                        "boxShadow": "0 2px 4px rgba(0,0,0,0.08)",
                        "border": "1px solid #eee",
                        "overflow": "hidden",
                        "background": "#000",
                    },
                ),
                style={"marginBottom": "8px"},
            ),
            # ---------- Three audiences ----------
            html.Section(
                [
                    html.H2("Three audiences, one small package", style=_HEADING_STYLE),
                    html.P(
                        "Click any card to see how this package serves that audience — each has a live demo page in this app.",
                        style={"color": _MUTED},
                    ),
                    html.Div(
                        [
                            _audience_card(
                                "MCP clients",
                                "JSON-RPC over Streamable HTTP",
                                "Each page's LLMS_DOC registers as a dash.mcp resource on Dash 4.3+.",
                                "#667eea",
                                href="/audiences/mcp-clients",
                            ),
                            _audience_card(
                                "Web crawlers",
                                "Plain HTTPS, often no JavaScript",
                                "/robots.txt, /sitemap.xml, plus a static-HTML prerender of every page.",
                                "#51cf66",
                                href="/audiences/web-crawlers",
                            ),
                            _audience_card(
                                "Paste-into-chat users",
                                "One-shot HTTP fetch into an LLM context window",
                                "/llms.txt and /<page>/llms.txt return the page's LLMS_DOC verbatim.",
                                "#e599f7",
                                href="/audiences/llm-context",
                            ),
                        ],
                        style={
                            "display": "flex",
                            "gap": "16px",
                            "flexWrap": "wrap",
                            "alignItems": "stretch",
                        },
                    ),
                ]
            ),
            # ---------- Live routes ----------
            html.Section(
                [
                    html.H2("Try it on this app", style=_HEADING_STYLE),
                    html.P(
                        "Every link below is generated by this very page hitting the running app:",
                        style={"color": _MUTED},
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("Site-wide", style={"fontSize": "15px", "color": _INK}),
                                    html.Ul(
                                        [
                                            _route_link("/llms.txt", "this page's prose"),
                                            _route_link("/robots.txt", "bot policy"),
                                            _route_link("/sitemap.xml", "non-hidden pages"),
                                        ],
                                        style={"paddingLeft": "18px"},
                                    ),
                                ],
                                style={"flex": "1"},
                            ),
                            html.Div(
                                [
                                    html.H3("Per page", style={"fontSize": "15px", "color": _INK}),
                                    html.Ul(
                                        [
                                            _route_link(
                                                "/audiences/mcp-clients/llms.txt",
                                                "MCP audience prose",
                                            ),
                                            _route_link(
                                                "/audiences/web-crawlers/llms.txt",
                                                "crawler audience prose",
                                            ),
                                            _route_link(
                                                "/audiences/llm-context/llms.txt",
                                                "paste-to-chat prose",
                                            ),
                                            _route_link("/analytics/llms.txt", "regular Dash page"),
                                            _route_link("/admin/llms.txt", "404 — page is hidden"),
                                        ],
                                        style={"paddingLeft": "18px"},
                                    ),
                                ],
                                style={"flex": "1"},
                            ),
                        ],
                        style={"display": "flex", "gap": "24px", "flexWrap": "wrap"},
                    ),
                ]
            ),
            # ---------- Quick start ----------
            html.Section(
                [
                    html.H2("Quick start", style=_HEADING_STYLE),
                    html.Pre(
                        "from dash import Dash\n"
                        "from dash_improve_my_llms import add_llms_routes, RobotsConfig, mark_hidden\n"
                        "\n"
                        "app = Dash(__name__, use_pages=True)\n"
                        'app._base_url = "https://myapp.com"\n'
                        "app._robots_config = RobotsConfig(\n"
                        "    block_ai_training=True,\n"
                        "    allow_ai_search=True,\n"
                        ")\n"
                        "\n"
                        'mark_hidden("/admin")\n'
                        "add_llms_routes(app)\n",
                        style=_CODE_BLOCK_STYLE,
                    ),
                ]
            ),
            # ---------- LLMS_DOC pattern ----------
            html.Section(
                [
                    html.H2("The LLMS_DOC pattern", style=_HEADING_STYLE),
                    html.P(
                        [
                            "Every page module exports a ",
                            html.Code("LLMS_DOC"),
                            " string. That string is the literal body of ",
                            html.Code("/<page>/llms.txt"),
                            ". No layout walking, no extraction:",
                        ],
                        style={"color": _MUTED},
                    ),
                    html.Pre(
                        "# pages/analytics.py\n"
                        "LLMS_DOC = '''\n"
                        "# Analytics Dashboard\n"
                        "\n"
                        "Headline metrics, a trend chart, and a recent-activity feed.\n"
                        "...\n"
                        "'''\n",
                        style=_CODE_BLOCK_STYLE,
                    ),
                    html.P(
                        [
                            "If a page has no ",
                            html.Code("LLMS_DOC"),
                            ", you'll see a single ",
                            html.Code("UserWarning"),
                            " at ",
                            html.Code("add_llms_routes()"),
                            " naming the missing pages, and the endpoint returns a small "
                            "stub so bots still get a 200 instead of a 404.",
                        ],
                        style={"color": _MUTED, "fontSize": "14px"},
                    ),
                ]
            ),
            # ---------- Multi-backend ----------
            html.Section(
                [
                    html.H2("Multi-backend (Dash 4.1+)", style=_HEADING_STYLE),
                    html.P(
                        [
                            html.Code("add_llms_routes(app)"),
                            " detects whether ",
                            html.Code("app.server"),
                            " is Flask, FastAPI, or Quart and dispatches to the matching "
                            "adapter. Pick one extra at install time:",
                        ],
                        style={"color": _MUTED},
                    ),
                    html.Pre(
                        "pip install dash-improve-my-llms[flask]     # Dash 3.x and earlier\n"
                        "pip install dash-improve-my-llms[fastapi]   # Dash 4.1+\n"
                        "pip install dash-improve-my-llms[quart]     # Dash 4.1+ async\n",
                        style=_CODE_BLOCK_STYLE,
                    ),
                ]
            ),
            # ---------- Other pages tour ----------
            html.Section(
                [
                    html.H2("Other pages in this demo", style=_HEADING_STYLE),
                    html.P(
                        "Beyond the three audience demos above:",
                        style={"color": _MUTED, "marginBottom": "16px"},
                    ),
                    html.Div(
                        [
                            _page_card(
                                "📊",
                                "Analytics",
                                "A regular Dash page (Plotly metrics + callbacks) wired up with its own LLMS_DOC.",
                                "/analytics",
                            ),
                            _page_card(
                                "🔒",
                                "Admin",
                                "Hidden from sitemap and robots — the mark_hidden() side of the package.",
                                "/admin",
                                accent="#ff6b6b",
                            ),
                            _page_card(
                                "📚",
                                "v2.0 Features",
                                "What changed from 1.x and how the LLMS_DOC pattern works.",
                                "/v200-features",
                            ),
                        ],
                        style={"display": "flex", "gap": "16px", "flexWrap": "wrap"},
                    ),
                ]
            ),
            # ---------- Migration note ----------
            html.Section(
                [
                    html.H2("Migrating from 1.x", style=_HEADING_STYLE),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("Kept", style={"color": "#51cf66", "fontSize": "15px"}),
                                    html.Ul(
                                        [
                                            html.Li("/llms.txt and /<page>/llms.txt (prose only)"),
                                            html.Li("/robots.txt with RobotsConfig"),
                                            html.Li("/sitemap.xml"),
                                            html.Li("mark_hidden(), register_page_metadata()"),
                                            html.Li("Bot detection middleware"),
                                        ]
                                    ),
                                ],
                                style={"flex": "1"},
                            ),
                            html.Div(
                                [
                                    html.H3(
                                        "Dropped", style={"color": "#ff6b6b", "fontSize": "15px"}
                                    ),
                                    html.Ul(
                                        [
                                            html.Li("/page.json"),
                                            html.Li("/architecture.txt"),
                                            html.Li("/architecture.toon and /<page>/llms.toon"),
                                            html.Li("Component-tree extraction in /llms.txt"),
                                            html.Li(
                                                "mark_important() and mark_component_hidden() (no-op shims)"
                                            ),
                                        ]
                                    ),
                                ],
                                style={"flex": "1"},
                            ),
                            html.Div(
                                [
                                    html.H3("New", style={"color": _BRAND, "fontSize": "15px"}),
                                    html.Ul(
                                        [
                                            html.Li("FastAPI and Quart backend adapters"),
                                            html.Li("dash.mcp resource registration (Dash 4.3+)"),
                                            html.Li("LLMS_DOC pattern + missing-doc warning"),
                                            html.Li("Pure framework-agnostic handlers"),
                                            html.Li("llms_doc= kwarg on register_page_metadata()"),
                                        ]
                                    ),
                                ],
                                style={"flex": "1"},
                            ),
                        ],
                        style={"display": "flex", "gap": "24px", "flexWrap": "wrap"},
                    ),
                ]
            ),
            # ---------- Footer ----------
            html.Footer(
                [
                    html.Hr(
                        style={
                            "border": "none",
                            "borderTop": "1px solid #eee",
                            "margin": "40px 0 16px",
                        }
                    ),
                    html.P(
                        [
                            "Built by ",
                            html.A(
                                "Pip Install Python LLC",
                                href="https://pip-install-python.com",
                                target="_blank",
                                style={"color": _BRAND},
                            ),
                            ".",
                        ],
                        style={"color": _MUTED, "fontSize": "13px", "textAlign": "center"},
                    ),
                ]
            ),
        ],
        style={
            "maxWidth": "1000px",
            "margin": "0 auto",
            "padding": "32px 24px",
            "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            "color": _INK,
            "lineHeight": "1.6",
        },
    )
