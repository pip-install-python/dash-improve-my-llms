"""
Audience #2 — Web crawlers.

Shows what Googlebot, GPTBot, ClaudeBot, and friends actually see when
they hit this app: the live /robots.txt, the current RobotsConfig
knobs, which pages are hidden, and how to configure for common
policies.
"""

import dash
from dash import dcc, html, register_page

from dash_improve_my_llms import is_hidden, register_page_metadata
from dash_improve_my_llms.bot_detection import (
    AI_SEARCH_BOTS,
    AI_TRAINING_BOTS,
    TRADITIONAL_BOTS,
)

register_page(__name__, path="/audiences/web-crawlers", name="Web Crawlers")


LLMS_DOC = """\
# Web Crawlers — what they see and how to control them

> Googlebot, GPTBot, ClaudeBot, PerplexityBot, Bingbot, and friends.
> Plain HTTPS, often no JavaScript.

## What this audience needs

Crawlers walk the public web following links and reading HTML. Most
respect `robots.txt`. Many — Googlebot included — render some
JavaScript, but Dash's full JS shell is fragile to index reliably. AI
training crawlers (GPTBot, CCBot) usually skip JS entirely.

For this audience, 2.0 ships:

1. `/robots.txt` with bot-class access policies via `RobotsConfig`.
2. `/sitemap.xml` generated from `dash.page_registry` minus hidden pages.
3. A bot-detection middleware that intercepts every request, classifies
   the User-Agent, and returns a prerendered static HTML page for
   crawlers — so they get the page's `LLMS_DOC` as visible content
   instead of an empty Dash shell.
4. AI-training-bot blocking via `block_ai_training=True`, which
   returns 403 to known training UAs.

## How configuration flows

```python
from dash_improve_my_llms import RobotsConfig, mark_hidden

app._base_url = "https://myapp.com"
app._robots_config = RobotsConfig(
    block_ai_training=True,    # GPTBot, CCBot, anthropic-ai → 403
    allow_ai_search=True,      # ClaudeBot, ChatGPT-User → allowed
    allow_traditional=True,    # Googlebot, Bingbot → allowed
    crawl_delay=10,            # seconds between requests
    disallowed_paths=["/admin"],
)

mark_hidden("/admin")          # 404 for crawlers, skipped in sitemap
```

`RobotsConfig` drives both the `/robots.txt` body and the middleware's
runtime decisions — they always agree.

## Bot classes recognized

- **AI Training** — GPTBot, anthropic-ai, Claude-Web, CCBot,
  Google-Extended, FacebookBot, Omgili, ByteSpider.
  Default policy: blocked.
- **AI Search** — ChatGPT-User, ClaudeBot, PerplexityBot, OAI-SearchBot.
  Default policy: allowed.
- **Traditional** — Googlebot, Bingbot, DuckDuckBot, Yandex, plus
  generic patterns (`bot`, `crawler`, `spider`).
  Default policy: allowed.

## Verifying it works

Use `curl` to impersonate a crawler:

```bash
# Training bot — should return 403 with block_ai_training=True
curl -A "Mozilla/5.0 (compatible; GPTBot/1.0)" https://myapp.com/

# Search bot — should return prerendered static HTML
curl -A "Mozilla/5.0 (compatible; Googlebot/2.1)" https://myapp.com/

# Inspect the prose surface
curl https://myapp.com/llms.txt
```
"""


register_page_metadata(
    path="/audiences/web-crawlers",
    name="Web Crawlers",
    description="What crawlers see when they hit this app, and how to configure RobotsConfig for common policies.",
)


# -----------------------------------------------------------------------------
# Layout helpers
# -----------------------------------------------------------------------------

_BRAND = "#667eea"
_OK_GREEN = "#2b8a3e"
_BLOCK_RED = "#c92a2a"

_CARD = {
    "background": "white",
    "border": "1px solid #eee",
    "borderRadius": "8px",
    "padding": "20px",
}

_CODE_BLOCK = {
    "background": "#1e1e1e",
    "color": "#d4d4d4",
    "padding": "16px",
    "borderRadius": "6px",
    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
    "fontSize": "13px",
    "lineHeight": "1.55",
    "overflowX": "auto",
    "whiteSpace": "pre-wrap",
}


def _policy_pill(label: str, blocked: bool) -> html.Span:
    return html.Span(
        label,
        style={
            "display": "inline-block",
            "padding": "2px 10px",
            "borderRadius": "10px",
            "fontSize": "12px",
            "fontWeight": "600",
            "background": "#ffe3e3" if blocked else "#d3f9d8",
            "color": _BLOCK_RED if blocked else _OK_GREEN,
        },
    )


def _config_snippet(title: str, blurb: str, code: str) -> html.Div:
    return html.Div(
        [
            html.H3(title, style={"fontSize": "15px", "margin": "0 0 4px"}),
            html.P(blurb, style={"color": "#666", "fontSize": "13px", "margin": "0 0 10px"}),
            html.Pre(code, style=_CODE_BLOCK),
        ],
        style={**_CARD, "flex": "1", "minWidth": "260px"},
    )


def _fetch_robots_txt() -> str:
    """Render the live /robots.txt by calling the package's pure handler directly."""
    try:
        from dash_improve_my_llms.handlers import build_robots_txt

        app = dash.get_app()
        return build_robots_txt(app)
    except Exception as exc:
        return f"# could not render /robots.txt at layout time: {exc}"


def _page_row(path: str, name: str) -> html.Tr:
    hidden = is_hidden(path)
    return html.Tr(
        [
            html.Td(
                html.Code(path, style={"fontSize": "13px"}),
                style={"padding": "10px 12px", "borderBottom": "1px solid #f0f0f0"},
            ),
            html.Td(
                name,
                style={
                    "padding": "10px 12px",
                    "fontSize": "14px",
                    "borderBottom": "1px solid #f0f0f0",
                },
            ),
            html.Td(
                _policy_pill("HIDDEN" if hidden else "VISIBLE", blocked=hidden),
                style={"padding": "10px 12px", "borderBottom": "1px solid #f0f0f0"},
            ),
            html.Td(
                "404" if hidden else "200",
                style={
                    "padding": "10px 12px",
                    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
                    "fontSize": "13px",
                    "color": _BLOCK_RED if hidden else _OK_GREEN,
                    "borderBottom": "1px solid #f0f0f0",
                },
            ),
            html.Td(
                "Excluded" if hidden else "Listed",
                style={
                    "padding": "10px 12px",
                    "fontSize": "13px",
                    "color": "#666",
                    "borderBottom": "1px solid #f0f0f0",
                },
            ),
        ]
    )


# -----------------------------------------------------------------------------
# Layout
# -----------------------------------------------------------------------------


def layout():
    app = dash.get_app()
    cfg = getattr(app, "_robots_config", None)
    base_url = getattr(app, "_base_url", "https://example.com")

    if cfg is None:
        knobs = [("RobotsConfig not configured", "—", False)]
    else:
        knobs = [
            ("block_ai_training", str(cfg.block_ai_training), cfg.block_ai_training),
            ("allow_ai_search", str(cfg.allow_ai_search), False),
            ("allow_traditional", str(cfg.allow_traditional), False),
            ("crawl_delay", str(cfg.crawl_delay) if cfg.crawl_delay else "none", False),
            (
                "disallowed_paths",
                ", ".join(cfg.disallowed_paths) if cfg.disallowed_paths else "none",
                False,
            ),
        ]

    registry = dict(dash.page_registry)
    page_rows = []
    for entry in sorted(registry.values(), key=lambda e: e.get("path", "")):
        page_rows.append(
            _page_row(
                path=entry.get("path", "/"),
                name=entry.get("name", "Page"),
            )
        )

    return html.Div(
        [
            # Hero
            html.Header(
                [
                    html.Div(
                        "Audience",
                        style={
                            "fontSize": "12px",
                            "color": _BRAND,
                            "letterSpacing": "1px",
                            "fontWeight": "600",
                        },
                    ),
                    html.H1("Web Crawlers", style={"margin": "4px 0 8px", "fontSize": "32px"}),
                    html.P(
                        "Plain HTTPS, often no JavaScript. /robots.txt, /sitemap.xml, plus a static-HTML prerender of every page.",
                        style={"fontSize": "16px", "color": "#666", "margin": 0},
                    ),
                ],
                style={"marginBottom": "28px"},
            ),
            # Current config knobs
            html.Section(
                [
                    html.H2(
                        "Current configuration", style={"fontSize": "18px", "marginBottom": "12px"}
                    ),
                    html.P(
                        [
                            "These are the values ",
                            html.Code("app._robots_config"),
                            " is using right now in this running app:",
                        ],
                        style={"color": "#666", "marginBottom": "16px"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        label,
                                        style={
                                            "fontSize": "12px",
                                            "color": "#888",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.5px",
                                            "marginBottom": "4px",
                                        },
                                    ),
                                    html.Code(
                                        value,
                                        style={
                                            "fontSize": "14px",
                                            "color": _BLOCK_RED if highlight_block else _OK_GREEN,
                                        },
                                    ),
                                ],
                                style={**_CARD, "flex": "1", "minWidth": "180px"},
                            )
                            for label, value, highlight_block in knobs
                        ],
                        style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                    ),
                    html.Div(
                        [
                            html.Span("Base URL: ", style={"fontSize": "13px", "color": "#888"}),
                            html.Code(base_url, style={"fontSize": "13px"}),
                        ],
                        style={"marginTop": "16px"},
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            # Live robots.txt
            html.Section(
                [
                    html.H2(
                        [
                            "Live ",
                            html.A(
                                "/robots.txt",
                                href="/robots.txt",
                                target="_blank",
                                style={"color": _BRAND, "textDecoration": "none"},
                            ),
                        ],
                        style={"fontSize": "18px", "marginBottom": "8px"},
                    ),
                    html.P(
                        "Generated by the package from the config above. This is what crawlers actually fetch:",
                        style={"color": "#666", "marginBottom": "12px"},
                    ),
                    html.Pre(
                        _fetch_robots_txt(),
                        style={**_CODE_BLOCK, "maxHeight": "420px", "overflowY": "auto"},
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            # Page visibility table
            html.Section(
                [
                    html.H2(
                        "Per-page visibility", style={"fontSize": "18px", "marginBottom": "8px"}
                    ),
                    html.P(
                        [
                            "How each page in this app responds to a crawler request. Pages marked HIDDEN "
                            "(via ",
                            html.Code("mark_hidden(path)"),
                            ") return 404 to crawlers and are excluded from sitemap.xml.",
                        ],
                        style={"color": "#666", "marginBottom": "16px"},
                    ),
                    html.Div(
                        html.Table(
                            [
                                html.Thead(
                                    html.Tr(
                                        [
                                            html.Th(
                                                h,
                                                style={
                                                    "textAlign": "left",
                                                    "padding": "8px 12px",
                                                    "background": "#fafafa",
                                                    "fontSize": "12px",
                                                    "color": "#666",
                                                    "textTransform": "uppercase",
                                                    "letterSpacing": "0.5px",
                                                },
                                            )
                                            for h in (
                                                "Path",
                                                "Name",
                                                "Crawler policy",
                                                "Bot HTTP",
                                                "Sitemap",
                                            )
                                        ]
                                    )
                                ),
                                html.Tbody(page_rows),
                            ],
                            style={
                                "width": "100%",
                                "borderCollapse": "collapse",
                                "background": "white",
                                "border": "1px solid #eee",
                                "borderRadius": "8px",
                                "overflow": "hidden",
                            },
                        ),
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            # Bot classes
            html.Section(
                [
                    html.H2(
                        "Bot classes recognized by the middleware",
                        style={"fontSize": "18px", "marginBottom": "16px"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3(
                                        "AI Training",
                                        style={
                                            "color": _BLOCK_RED,
                                            "fontSize": "15px",
                                            "margin": "0 0 8px",
                                        },
                                    ),
                                    html.Div(
                                        "Blocked by default",
                                        style={
                                            "fontSize": "12px",
                                            "color": _BLOCK_RED,
                                            "marginBottom": "10px",
                                        },
                                    ),
                                    html.Div(
                                        ", ".join(AI_TRAINING_BOTS),
                                        style={
                                            "fontSize": "12px",
                                            "color": "#666",
                                            "fontFamily": "monospace",
                                            "lineHeight": "1.7",
                                            "wordBreak": "break-word",
                                        },
                                    ),
                                ],
                                style={
                                    **_CARD,
                                    "flex": "1",
                                    "minWidth": "240px",
                                    "borderTop": f"3px solid {_BLOCK_RED}",
                                },
                            ),
                            html.Div(
                                [
                                    html.H3(
                                        "AI Search",
                                        style={
                                            "color": _BRAND,
                                            "fontSize": "15px",
                                            "margin": "0 0 8px",
                                        },
                                    ),
                                    html.Div(
                                        "Allowed by default",
                                        style={
                                            "fontSize": "12px",
                                            "color": _OK_GREEN,
                                            "marginBottom": "10px",
                                        },
                                    ),
                                    html.Div(
                                        ", ".join(AI_SEARCH_BOTS),
                                        style={
                                            "fontSize": "12px",
                                            "color": "#666",
                                            "fontFamily": "monospace",
                                            "lineHeight": "1.7",
                                            "wordBreak": "break-word",
                                        },
                                    ),
                                ],
                                style={
                                    **_CARD,
                                    "flex": "1",
                                    "minWidth": "240px",
                                    "borderTop": f"3px solid {_BRAND}",
                                },
                            ),
                            html.Div(
                                [
                                    html.H3(
                                        "Traditional",
                                        style={
                                            "color": _OK_GREEN,
                                            "fontSize": "15px",
                                            "margin": "0 0 8px",
                                        },
                                    ),
                                    html.Div(
                                        "Allowed by default",
                                        style={
                                            "fontSize": "12px",
                                            "color": _OK_GREEN,
                                            "marginBottom": "10px",
                                        },
                                    ),
                                    html.Div(
                                        ", ".join(TRADITIONAL_BOTS),
                                        style={
                                            "fontSize": "12px",
                                            "color": "#666",
                                            "fontFamily": "monospace",
                                            "lineHeight": "1.7",
                                            "wordBreak": "break-word",
                                        },
                                    ),
                                ],
                                style={
                                    **_CARD,
                                    "flex": "1",
                                    "minWidth": "240px",
                                    "borderTop": f"3px solid {_OK_GREEN}",
                                },
                            ),
                        ],
                        style={"display": "flex", "gap": "12px", "flexWrap": "wrap"},
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            # Recipes
            html.Section(
                [
                    html.H2(
                        "Configuration recipes", style={"fontSize": "18px", "marginBottom": "16px"}
                    ),
                    html.Div(
                        [
                            _config_snippet(
                                "Strict — block all AI",
                                "Block training AND search bots. Allow only Googlebot/Bingbot.",
                                "RobotsConfig(\n    block_ai_training=True,\n    allow_ai_search=False,\n    allow_traditional=True,\n)",
                            ),
                            _config_snippet(
                                "Balanced (default)",
                                "Block training data collection, allow AI search citations.",
                                "RobotsConfig(\n    block_ai_training=True,\n    allow_ai_search=True,\n    allow_traditional=True,\n    crawl_delay=10,\n)",
                            ),
                            _config_snippet(
                                "Lenient — allow all",
                                "No blocking. Useful for public docs and reference content.",
                                "RobotsConfig(\n    block_ai_training=False,\n    allow_ai_search=True,\n    allow_traditional=True,\n)",
                            ),
                        ],
                        style={"display": "flex", "gap": "16px", "flexWrap": "wrap"},
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            # Verify-with-curl
            html.Section(
                [
                    html.H2("Verify with curl", style={"fontSize": "18px", "marginBottom": "8px"}),
                    html.P(
                        "Pretend to be each kind of crawler and see what the middleware returns:",
                        style={"color": "#666", "marginBottom": "12px"},
                    ),
                    html.Pre(
                        "# Training bot — should return 403 when block_ai_training=True\n"
                        'curl -A "Mozilla/5.0 (compatible; GPTBot/1.0)" http://localhost:8959/\n\n'
                        "# Search bot — should return prerendered static HTML\n"
                        'curl -A "Mozilla/5.0 (compatible; Googlebot/2.1)" http://localhost:8959/\n\n'
                        "# Regular browser — passes through to the Dash app\n"
                        'curl -A "Mozilla/5.0 (Macintosh)" http://localhost:8959/',
                        style=_CODE_BLOCK,
                    ),
                ]
            ),
            # Footer nav
            html.Footer(
                [
                    html.Hr(
                        style={
                            "border": "none",
                            "borderTop": "1px solid #eee",
                            "margin": "32px 0 16px",
                        }
                    ),
                    html.Div(
                        [
                            dcc.Link(
                                "← MCP Clients",
                                href="/audiences/mcp-clients",
                                style={"color": _BRAND, "textDecoration": "none"},
                            ),
                            html.Span(" · ", style={"color": "#ccc", "margin": "0 8px"}),
                            dcc.Link(
                                "Home", href="/", style={"color": _BRAND, "textDecoration": "none"}
                            ),
                            html.Span(" · ", style={"color": "#ccc", "margin": "0 8px"}),
                            dcc.Link(
                                "Paste-to-chat →",
                                href="/audiences/llm-context",
                                style={"color": _BRAND, "textDecoration": "none"},
                            ),
                        ]
                    ),
                ]
            ),
        ],
        style={"maxWidth": "1000px", "margin": "0 auto", "padding": "32px 24px"},
    )
