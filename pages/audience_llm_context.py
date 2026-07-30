"""
Audience #3 — Paste-into-chat users.

A human who wants to drop docs about this app into a chat window
(Claude.ai, ChatGPT, an in-product assistant) needs a one-click way
to grab the prose. This page is that affordance: every page's LLMS_DOC
is exposed with a copy button and a direct-to-text link.
"""

import sys
from typing import Optional

import dash
from dash import dcc, html, register_page

from dash_improve_my_llms import is_hidden, register_page_metadata

register_page(__name__, path="/audiences/llm-context", name="Paste-to-Chat")


LLMS_DOC = """\
# Paste-into-Chat — copy this app's docs into an LLM

> One-shot HTTP fetch into an LLM context window. /llms.txt and
> /<page>/llms.txt return the page's LLMS_DOC verbatim.

## What this audience needs

A human sitting in front of Claude.ai, ChatGPT, or an in-product
assistant wants to *tell the model what your app is about*. They need
the prose in a known location, in a paste-friendly format, with the
smallest possible friction between "I want context" and "the model
has it."

For this audience, 2.0 serves:

1. `/llms.txt` — the site-wide prose (the home page's LLMS_DOC).
2. `/<page>/llms.txt` — every page's prose at a predictable URL.
3. A `<link rel="alternate" type="text/markdown" href="/llms.txt">`
   in every HTML response so AI-aware browsers can find it.

## How to use it

**Direct paste.** Open `/llms.txt` (or any per-page variant) in your
browser, select all, paste into the chat.

**Direct fetch.** Most chat clients accept URLs as context — paste
the URL itself and let the assistant fetch it.

**Headless / programmatic.** Pipe the content from `curl`:

```bash
curl https://myapp.com/llms.txt | pbcopy           # macOS
curl https://myapp.com/llms.txt | xclip            # Linux

# Or stuff it straight into a chat client that accepts stdin:
curl https://myapp.com/audiences/llm-context/llms.txt | \\
    claude "Explain how this audience differs from MCP clients"
```

## Why prose, not structured data

This audience does NOT want JSON, TOON, or MCP JSON-RPC. They want
flat markdown that the model will treat as natural-language context.
Structured formats are for programmatic consumers (MCP clients,
crawlers parsing sitemaps). Humans paste prose.

## The copy buttons on this page

The buttons next to each page entry copy that page's `LLMS_DOC`
string directly to your clipboard, byte-for-byte identical to what
you'd get from `curl /<page>/llms.txt`.
"""


register_page_metadata(
    path="/audiences/llm-context",
    name="Paste-to-Chat",
    description="Copy any page's LLMS_DOC to your clipboard for one-shot fetches into Claude, ChatGPT, or an in-product assistant.",
)


# -----------------------------------------------------------------------------
# Style + helpers
# -----------------------------------------------------------------------------

_BRAND = "#667eea"

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
}


def _resolve_llms_doc(page_entry: dict) -> Optional[str]:
    module_name = page_entry.get("module")
    if module_name and module_name in sys.modules:
        return getattr(sys.modules[module_name], "LLMS_DOC", None)
    return None


def _copy_button(content: str, button_id: str, label: str = "Copy") -> html.Div:
    """A labeled copy-to-clipboard control. dcc.Clipboard handles the actual copy."""
    return html.Div(
        [
            dcc.Clipboard(
                content=content,
                id=button_id,
                title="Copy to clipboard",
                style={
                    "display": "inline-flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "width": "32px",
                    "height": "32px",
                    "background": _BRAND,
                    "color": "white",
                    "borderRadius": "6px 0 0 6px",
                    "cursor": "pointer",
                    "fontSize": "16px",
                },
            ),
            html.Span(
                label,
                style={
                    "display": "inline-flex",
                    "alignItems": "center",
                    "height": "32px",
                    "padding": "0 12px",
                    "background": _BRAND,
                    "color": "white",
                    "borderRadius": "0 6px 6px 0",
                    "fontSize": "13px",
                    "fontWeight": "600",
                    "marginLeft": "-1px",
                },
            ),
        ],
        style={"display": "inline-flex", "alignItems": "center"},
    )


def _page_row(path: str, name: str, doc: Optional[str]) -> html.Tr:
    has_doc = doc is not None
    size_str = f"{len(doc.encode('utf-8')):,} B" if has_doc else "—"
    href = f"{path.rstrip('/') or ''}/llms.txt".replace("//llms.txt", "/llms.txt")

    return html.Tr(
        [
            html.Td(
                [
                    html.Code(path, style={"fontSize": "13px"}),
                    html.Div(name, style={"fontSize": "12px", "color": "#888", "marginTop": "2px"}),
                ],
                style={
                    "padding": "12px",
                    "borderBottom": "1px solid #f0f0f0",
                    "verticalAlign": "top",
                },
            ),
            html.Td(
                size_str,
                style={
                    "padding": "12px",
                    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
                    "fontSize": "13px",
                    "color": "#666",
                    "textAlign": "right",
                    "borderBottom": "1px solid #f0f0f0",
                    "verticalAlign": "top",
                },
            ),
            html.Td(
                (
                    _copy_button(
                        content=doc, button_id=f"copy-{path.replace('/', '-').strip('-') or 'root'}"
                    )
                    if has_doc
                    else html.Span("no LLMS_DOC", style={"color": "#999", "fontSize": "12px"})
                ),
                style={
                    "padding": "12px",
                    "borderBottom": "1px solid #f0f0f0",
                    "verticalAlign": "top",
                },
            ),
            html.Td(
                html.A(
                    "view raw →",
                    href=href,
                    target="_blank",
                    style={"color": _BRAND, "textDecoration": "none", "fontSize": "13px"},
                ),
                style={
                    "padding": "12px",
                    "borderBottom": "1px solid #f0f0f0",
                    "verticalAlign": "top",
                },
            ),
        ]
    )


# -----------------------------------------------------------------------------
# Layout
# -----------------------------------------------------------------------------


def layout():
    registry = dict(dash.page_registry)
    rows = []
    visible_with_doc = 0
    for entry in sorted(registry.values(), key=lambda e: e.get("path", "")):
        path = entry.get("path", "/")
        if is_hidden(path):
            continue
        doc = _resolve_llms_doc(entry)
        if doc:
            visible_with_doc += 1
        rows.append(_page_row(path=path, name=entry.get("name", "Page"), doc=doc))

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
                    html.H1("Paste-into-Chat", style={"margin": "4px 0 8px", "fontSize": "32px"}),
                    html.P(
                        "One-shot HTTP fetch into an LLM context window. /llms.txt and /<page>/llms.txt return each page's LLMS_DOC verbatim.",
                        style={"fontSize": "16px", "color": "#666", "margin": 0},
                    ),
                ],
                style={"marginBottom": "28px"},
            ),
            # Primary copy affordance — this page's LLMS_DOC
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2(
                                        "Copy this page's docs",
                                        style={"fontSize": "18px", "margin": "0 0 4px"},
                                    ),
                                    html.P(
                                        [
                                            f"{len(LLMS_DOC.encode('utf-8')):,} bytes · ",
                                            html.A(
                                                "/audiences/llm-context/llms.txt",
                                                href="/audiences/llm-context/llms.txt",
                                                target="_blank",
                                                style={
                                                    "color": _BRAND,
                                                    "textDecoration": "none",
                                                    "fontFamily": "monospace",
                                                },
                                            ),
                                        ],
                                        style={"color": "#666", "fontSize": "13px", "margin": 0},
                                    ),
                                ],
                                style={"flex": "1"},
                            ),
                            _copy_button(
                                content=LLMS_DOC,
                                button_id="copy-this-page",
                                label="Copy LLMS_DOC",
                            ),
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "space-between",
                            "gap": "16px",
                            "marginBottom": "12px",
                        },
                    ),
                    dcc.Textarea(
                        value=LLMS_DOC,
                        readOnly=True,
                        style={
                            "width": "100%",
                            "minHeight": "240px",
                            "padding": "16px",
                            "border": "1px solid #e0e0e0",
                            "borderRadius": "6px",
                            "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
                            "fontSize": "13px",
                            "lineHeight": "1.6",
                            "background": "#fafafa",
                            "color": "#222",
                            "resize": "vertical",
                            "boxSizing": "border-box",
                        },
                    ),
                ],
                style={**_CARD, "marginBottom": "28px"},
            ),
            # Per-page directory
            html.Section(
                [
                    html.H2("Other pages", style={"fontSize": "18px", "marginBottom": "8px"}),
                    html.P(
                        f"All {visible_with_doc} non-hidden pages with prose. Click Copy to grab that page's LLMS_DOC, or View Raw to open the /llms.txt URL.",
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
                                                    "padding": "10px 12px",
                                                    "background": "#fafafa",
                                                    "fontSize": "12px",
                                                    "color": "#666",
                                                    "textTransform": "uppercase",
                                                    "letterSpacing": "0.5px",
                                                },
                                            )
                                            for h in ("Page", "Size", "Copy", "View")
                                        ]
                                    )
                                ),
                                html.Tbody(rows),
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
            # Curl snippets
            html.Section(
                [
                    html.H2("Headless fetching", style={"fontSize": "18px", "marginBottom": "8px"}),
                    html.P(
                        "For shells, scripts, or chat CLIs that accept stdin:",
                        style={"color": "#666", "marginBottom": "12px"},
                    ),
                    html.Pre(
                        "# macOS — pipe straight into the clipboard\n"
                        "curl http://localhost:8959/llms.txt | pbcopy\n\n"
                        "# Linux\n"
                        "curl http://localhost:8959/llms.txt | xclip -selection clipboard\n\n"
                        "# Pipe into a chat CLI (e.g. Claude Code) as context\n"
                        "curl http://localhost:8959/audiences/llm-context/llms.txt | \\\n"
                        '    claude "Explain what this audience needs"',
                        style=_CODE_BLOCK,
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            # Where to paste
            html.Section(
                [
                    html.H2("Where to paste", style={"fontSize": "18px", "marginBottom": "16px"}),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3(
                                        "Claude.ai / ChatGPT",
                                        style={"fontSize": "14px", "margin": "0 0 6px"},
                                    ),
                                    html.P(
                                        "Paste directly into the message box, prefixed with a brief context sentence like "
                                        '"Here are the docs for the app I\'m asking about:".',
                                        style={"color": "#666", "fontSize": "13px", "margin": 0},
                                    ),
                                ],
                                style={**_CARD, "flex": "1", "minWidth": "240px"},
                            ),
                            html.Div(
                                [
                                    html.H3(
                                        "System prompt / project knowledge",
                                        style={"fontSize": "14px", "margin": "0 0 6px"},
                                    ),
                                    html.P(
                                        "Drop the prose into a Project / Custom GPT / persistent system prompt so every "
                                        "conversation starts with the context loaded.",
                                        style={"color": "#666", "fontSize": "13px", "margin": 0},
                                    ),
                                ],
                                style={**_CARD, "flex": "1", "minWidth": "240px"},
                            ),
                            html.Div(
                                [
                                    html.H3(
                                        "RAG / vector store",
                                        style={"fontSize": "14px", "margin": "0 0 6px"},
                                    ),
                                    html.P(
                                        "Each /llms.txt is one document worth indexing. Pages are small enough to skip "
                                        "chunking and embed whole.",
                                        style={"color": "#666", "fontSize": "13px", "margin": 0},
                                    ),
                                ],
                                style={**_CARD, "flex": "1", "minWidth": "240px"},
                            ),
                        ],
                        style={"display": "flex", "gap": "16px", "flexWrap": "wrap"},
                    ),
                ],
                style={"marginBottom": "32px"},
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
                                "← Web Crawlers",
                                href="/audiences/web-crawlers",
                                style={"color": _BRAND, "textDecoration": "none"},
                            ),
                            html.Span(" · ", style={"color": "#ccc", "margin": "0 8px"}),
                            dcc.Link(
                                "MCP Clients",
                                href="/audiences/mcp-clients",
                                style={"color": _BRAND, "textDecoration": "none"},
                            ),
                            html.Span(" · ", style={"color": "#ccc", "margin": "0 8px"}),
                            dcc.Link(
                                "Home", href="/", style={"color": _BRAND, "textDecoration": "none"}
                            ),
                        ]
                    ),
                ]
            ),
        ],
        style={"maxWidth": "1000px", "margin": "0 auto", "padding": "32px 24px"},
    )
