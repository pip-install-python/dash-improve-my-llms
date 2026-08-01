"""
v2.0 Features Demo Page

Demonstrates the new dash-improve-my-llms 2.0 surface:

  - Narrowed scope: crawler/SEO + prose docs only.
  - LLMS_DOC pattern: prose lives next to the layout, no extraction.
  - Multi-backend: works under Flask, FastAPI, and Quart.
  - MCP bridge: prose registers as dash.mcp resources automatically.

The module-level LLMS_DOC string below IS the body of /v200-features/llms.txt.
The same string is rendered visually further down via dcc.Markdown so
the human-facing UI matches what crawlers and MCP clients receive.
"""

from dash import dcc, html, register_page

from dash_improve_my_llms import register_page_metadata
from lib.constants import OG_IMAGE_URL, PAGE_TITLE_PREFIX

_DESCRIPTION = (
    "What changed in dash-improve-my-llms 2.0: narrowed scope, LLMS_DOC "
    "pattern, multi-backend support, and the MCP bridge."
)

register_page(
    __name__,
    path="/v200-features",
    name="v2.0 Features",
    title=f"{PAGE_TITLE_PREFIX}v2.0 Features",
    description=_DESCRIPTION,
    image_url=OG_IMAGE_URL,
)


# This is the canonical 2.0 pattern: a module-level LLMS_DOC string.
# The /v200-features/llms.txt endpoint serves this verbatim.
LLMS_DOC = """\
# dash-improve-my-llms 2.0 — What Changed

> A focused rescope for the Dash 4.x / MCP era.

## Why 2.0

Dash 4.1+ runs on FastAPI/Quart in addition to Flask. Dash 4.3 ships
an MCP server that exposes layout and component structure live, over
JSON-RPC. That made most of 1.x redundant: the package was extracting
the component tree and shipping it over HTTP, which MCP now does
natively and better.

2.0 narrows the package to the surfaces MCP and native Dash do NOT
cover:

- `/robots.txt` with bot-class policies
- `/sitemap.xml` for search-engine discovery
- `/llms.txt` per page as prose for paste-into-chat use
- Static-HTML prerender for crawlers that do not run JavaScript
- A thin MCP bridge that registers the same prose as MCP resources

## The LLMS_DOC pattern

Every page module exports a `LLMS_DOC` string. That string IS the body
of `/<page>/llms.txt`. No layout walking, no extraction, no surprises:

```python
# pages/analytics.py
LLMS_DOC = '''
# Analytics Dashboard

Headline metrics, a trend chart, and a recent-activity feed.
...
'''
```

If a page has no `LLMS_DOC`, the package emits a single warning at
`add_llms_routes()` listing the missing pages, and the endpoint
returns a small stub so bots still get a 200.

## Multi-backend support

`add_llms_routes(app)` detects whether `app.server` is Flask, FastAPI,
or Quart and dispatches to the matching adapter. Existing 1.x code on
Flask keeps working unchanged.

```python
pip install dash-improve-my-llms[flask]      # default for Dash 3.x
pip install dash-improve-my-llms[fastapi]    # Dash 4.1+
pip install dash-improve-my-llms[quart]      # Dash 4.1+ async
```

## What was removed

These endpoints are gone in 2.0 because Dash 4.3 MCP covers the same
ground better:

- `/page.json`
- `/architecture.txt`
- `/architecture.toon`
- `/llms.toon` (and per-page variants)

Helpers tied to those endpoints — `TOONConfig`, `PageType`,
`generate_llms_toon`, `extract_prose_content`, `mark_important`,
`mark_component_hidden` — are removed or shimmed as deprecated no-ops
for one release.

## The MCP bridge

When `dash.mcp` is available (Dash 4.3+) and enabled on the app, every
non-hidden page's `LLMS_DOC` is registered as an MCP resource with a
URI like `llms:///audiences/mcp-clients`. MCP-aware clients can fetch the same
prose through a tool call instead of HTTP.
"""


register_page_metadata(
    path="/v200-features",
    name="v2.0 Features",
    description=_DESCRIPTION,
)


def layout():
    return html.Div(
        [
            html.Header(
                [
                    html.H1("dash-improve-my-llms 2.0"),
                    html.P(
                        "A focused rescope for the Dash 4.x / MCP era.",
                        style={"fontSize": "18px", "color": "#666"},
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            html.Section(
                [
                    html.H2("This page IS the demo"),
                    html.P(
                        [
                            "The markdown below is the literal value of ",
                            html.Code("LLMS_DOC"),
                            " in ",
                            html.Code("pages/v200_features.py"),
                            ". It is also what you get when you fetch ",
                            html.A(
                                "/v200-features/llms.txt",
                                href="/v200-features/llms.txt",
                                target="_blank",
                            ),
                            " — byte for byte.",
                        ]
                    ),
                ],
                style={"marginBottom": "24px"},
            ),
            html.Section(
                dcc.Markdown(LLMS_DOC, link_target="_blank"),
                style={
                    "padding": "24px",
                    "background": "#fafafa",
                    "borderLeft": "4px solid #667eea",
                    "borderRadius": "4px",
                },
            ),
            html.Section(
                [
                    html.H2("Try the surfaces", style={"marginTop": "32px"}),
                    html.Ul(
                        [
                            html.Li(
                                html.A(
                                    "/v200-features/llms.txt — this page's prose",
                                    href="/v200-features/llms.txt",
                                    target="_blank",
                                )
                            ),
                            html.Li(
                                html.A(
                                    "/llms.txt — landing-page prose",
                                    href="/llms.txt",
                                    target="_blank",
                                )
                            ),
                            html.Li(
                                html.A(
                                    "/robots.txt — bot policy",
                                    href="/robots.txt",
                                    target="_blank",
                                )
                            ),
                            html.Li(
                                html.A(
                                    "/sitemap.xml — for search engines",
                                    href="/sitemap.xml",
                                    target="_blank",
                                )
                            ),
                        ]
                    ),
                ]
            ),
            html.Footer(
                dcc.Link("← Home", href="/"),
                style={"marginTop": "40px", "paddingTop": "16px", "borderTop": "1px solid #e0e0e0"},
            ),
        ],
        style={"maxWidth": "900px", "margin": "0 auto", "padding": "24px"},
    )
