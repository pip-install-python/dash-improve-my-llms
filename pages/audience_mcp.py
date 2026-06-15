"""
Audience #1 — MCP clients.

This page is a directory of the resources that dash-improve-my-llms
registers with Dash 4.3+'s dash.mcp server. It iterates the live
page_registry, finds each page's LLMS_DOC, and shows what URI an MCP
client would see.

The page itself uses the same LLMS_DOC pattern — see the module-level
string immediately below.
"""

import sys
from typing import Optional

import dash
from dash import dcc, html, register_page

from dash_improve_my_llms import is_hidden, register_page_metadata

register_page(__name__, path="/audiences/mcp-clients", name="MCP Clients")


LLMS_DOC = """\
# MCP Clients — directory and integration notes

> How dash-improve-my-llms 2.0 talks to MCP-aware clients (Claude Desktop,
> agentic IDEs, MCP-aware chatbots) on Dash 4.3+.

## What this audience needs

MCP clients speak JSON-RPC over Streamable HTTP. They don't browse
the rendered UI and they don't curl `/llms.txt`. They expect to call
`resources/list` to see what's available, then `resources/read` to
fetch the body of any resource by URI.

## What 2.0 registers

When `add_llms_routes(app)` runs, the MCP bridge walks
`dash.page_registry`, skips any page that has been `mark_hidden()`,
resolves each page's `LLMS_DOC` (either from a module-level attribute
or `register_page_metadata(llms_doc=...)`), and registers it as an
MCP resource with a URI of the form `llms:///<page-path>`.

Each resource carries:
- `uri` — `llms:///audiences/mcp-clients`, `llms:///analytics`, etc.
- `name` — e.g. `llms.txt for Analytics Dashboard`
- `description` — the same prose as the page's `<meta name="description">`
- `mimeType` — `text/markdown`

## What this audience does NOT get

Dash 4.3's MCP server itself exposes layouts and component metadata
live as MCP resources. This package does **not** duplicate that — it
only ships the hand-written prose. If an MCP client wants live
component data, it should use Dash's native MCP endpoints.

## Code sample — what a client sends

A minimal JSON-RPC `resources/list` looks like:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "resources/list"
}
```

A `resources/read` for one URI:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "resources/read",
  "params": { "uri": "llms:///audiences/mcp-clients" }
}
```

## Disabling the MCP bridge

If you want to register resources yourself or skip MCP entirely:

```python
from dash_improve_my_llms import LLMSConfig, add_llms_routes

add_llms_routes(app, LLMSConfig(register_mcp_resources=False))
```

The HTTP surfaces (`/llms.txt`, `/robots.txt`, `/sitemap.xml`) keep
working unchanged.
"""


register_page_metadata(
    path="/audiences/mcp-clients",
    name="MCP Clients",
    description="Directory of pages this app registers as dash.mcp resources for Claude Desktop and other MCP-aware clients.",
)


# -----------------------------------------------------------------------------
# Helpers — these mirror what the package's MCP bridge does at register time
# -----------------------------------------------------------------------------


def _resolve_llms_doc(page_entry: dict) -> Optional[str]:
    """Mirror of dash_improve_my_llms.handlers._resolve_llms_doc, simplified."""
    module_name = page_entry.get("module")
    if module_name and module_name in sys.modules:
        return getattr(sys.modules[module_name], "LLMS_DOC", None)
    return None


def _mcp_status() -> dict:
    """Best-effort detection of dash.mcp availability on the running Dash."""
    result = {"installed": False, "module": None, "version": None}
    try:
        from dash import mcp as dash_mcp  # type: ignore

        result["installed"] = True
        result["module"] = dash_mcp.__name__
        result["version"] = getattr(dash_mcp, "__version__", "unknown")
    except ImportError:
        try:
            import dash_mcp  # type: ignore

            result["installed"] = True
            result["module"] = dash_mcp.__name__
            result["version"] = getattr(dash_mcp, "__version__", "unknown")
        except ImportError:
            pass
    return result


# -----------------------------------------------------------------------------
# Layout
# -----------------------------------------------------------------------------

_BRAND = "#667eea"
_CARD = {
    "background": "white",
    "border": "1px solid #eee",
    "borderRadius": "8px",
    "padding": "20px",
    "boxShadow": "0 1px 2px rgba(0,0,0,0.04)",
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


def _status_pill(text: str, ok: bool) -> html.Span:
    return html.Span(
        text,
        style={
            "display": "inline-block",
            "padding": "2px 10px",
            "borderRadius": "10px",
            "fontSize": "12px",
            "fontWeight": "600",
            "letterSpacing": "0.3px",
            "background": "#d3f9d8" if ok else "#fff3bf",
            "color": "#2b8a3e" if ok else "#5c4a00",
        },
    )


def _resource_row(uri: str, name: str, description: str, byte_count: int, path: str) -> html.Tr:
    return html.Tr(
        [
            html.Td(
                html.Code(uri, style={"fontSize": "13px", "color": _BRAND}),
                style={"padding": "10px 12px", "borderBottom": "1px solid #f0f0f0"},
            ),
            html.Td(
                name,
                style={"padding": "10px 12px", "fontSize": "14px", "borderBottom": "1px solid #f0f0f0"},
            ),
            html.Td(
                f"{byte_count:,} B",
                style={
                    "padding": "10px 12px",
                    "fontSize": "13px",
                    "color": "#666",
                    "textAlign": "right",
                    "borderBottom": "1px solid #f0f0f0",
                    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
                },
            ),
            html.Td(
                html.A(
                    "view HTTP →",
                    href=f"{path.rstrip('/') or ''}/llms.txt".replace("//llms.txt", "/llms.txt"),
                    target="_blank",
                    style={"fontSize": "13px", "color": _BRAND, "textDecoration": "none"},
                ),
                style={"padding": "10px 12px", "borderBottom": "1px solid #f0f0f0", "textAlign": "right"},
            ),
        ]
    )


def layout():
    status = _mcp_status()
    registry = dict(dash.page_registry)

    visible_pages = []
    missing_pages = []
    for entry in registry.values():
        path = entry.get("path", "/")
        if is_hidden(path):
            continue
        doc = _resolve_llms_doc(entry)
        if doc:
            visible_pages.append(
                {
                    "path": path,
                    "name": entry.get("name") or path,
                    "module": entry.get("module"),
                    "doc": doc,
                }
            )
        else:
            missing_pages.append({"path": path, "name": entry.get("name") or path})

    visible_pages.sort(key=lambda p: p["path"])

    return html.Div(
        [
            # Hero
            html.Header(
                [
                    html.Div("Audience", style={"fontSize": "12px", "color": _BRAND, "letterSpacing": "1px", "fontWeight": "600"}),
                    html.H1("MCP Clients", style={"margin": "4px 0 8px", "fontSize": "32px"}),
                    html.P(
                        "JSON-RPC over Streamable HTTP. Each page's LLMS_DOC registers as a dash.mcp resource on Dash 4.3+.",
                        style={"fontSize": "16px", "color": "#666", "margin": 0},
                    ),
                ],
                style={"marginBottom": "28px"},
            ),

            # Status card
            html.Section(
                [
                    html.H2("Live status", style={"fontSize": "18px", "marginBottom": "12px"}),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("dash.mcp available", style={"fontSize": "13px", "color": "#666", "marginBottom": "6px"}),
                                    _status_pill("YES" if status["installed"] else "NOT INSTALLED", status["installed"]),
                                    html.Div(
                                        f"module: {status['module']} · version: {status['version']}" if status["installed"] else
                                        "Falls back to HTTP-only mode. Install Dash 4.3+ to enable.",
                                        style={"fontSize": "12px", "color": "#888", "marginTop": "8px"},
                                    ),
                                ],
                                style={**_CARD, "flex": "1"},
                            ),
                            html.Div(
                                [
                                    html.Div("Pages that would register", style={"fontSize": "13px", "color": "#666", "marginBottom": "6px"}),
                                    html.Div(
                                        str(len(visible_pages)),
                                        style={"fontSize": "32px", "fontWeight": "600", "color": _BRAND},
                                    ),
                                    html.Div(
                                        f"non-hidden pages with LLMS_DOC (skipping {len(missing_pages)} without one)",
                                        style={"fontSize": "12px", "color": "#888"},
                                    ),
                                ],
                                style={**_CARD, "flex": "1"},
                            ),
                        ],
                        style={"display": "flex", "gap": "16px"},
                    ),
                ],
                style={"marginBottom": "32px"},
            ),

            # Resource directory
            html.Section(
                [
                    html.H2("Resource directory", style={"fontSize": "18px", "marginBottom": "8px"}),
                    html.P(
                        "What an MCP client would see when it calls resources/list against this app:",
                        style={"color": "#666", "marginBottom": "16px"},
                    ),
                    html.Div(
                        html.Table(
                            [
                                html.Thead(
                                    html.Tr(
                                        [
                                            html.Th("URI", style={"textAlign": "left", "padding": "8px 12px", "background": "#fafafa", "fontSize": "12px", "color": "#666", "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                                            html.Th("Name", style={"textAlign": "left", "padding": "8px 12px", "background": "#fafafa", "fontSize": "12px", "color": "#666", "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                                            html.Th("Size", style={"textAlign": "right", "padding": "8px 12px", "background": "#fafafa", "fontSize": "12px", "color": "#666", "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                                            html.Th("HTTP", style={"textAlign": "right", "padding": "8px 12px", "background": "#fafafa", "fontSize": "12px", "color": "#666", "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                                        ]
                                    )
                                ),
                                html.Tbody(
                                    [
                                        _resource_row(
                                            uri=f"llms://{p['path'].lstrip('/') or 'index'}",
                                            name=p["name"],
                                            description="",
                                            byte_count=len(p["doc"].encode("utf-8")),
                                            path=p["path"],
                                        )
                                        for p in visible_pages
                                    ]
                                ),
                            ],
                            style={"width": "100%", "borderCollapse": "collapse", "background": "white", "border": "1px solid #eee", "borderRadius": "8px", "overflow": "hidden"},
                        ),
                    ),
                    html.P(
                        [
                            "Pages without an LLMS_DOC are skipped — they don't get registered. Hidden pages "
                            "(via ",
                            html.Code("mark_hidden()"),
                            ") are also excluded.",
                        ]
                        if not missing_pages
                        else [
                            f"{len(missing_pages)} page(s) skipped because they lack an LLMS_DOC: ",
                            html.Code(", ".join(p["path"] for p in missing_pages)),
                        ],
                        style={"fontSize": "13px", "color": "#888", "marginTop": "12px"},
                    ),
                ],
                style={"marginBottom": "32px"},
            ),

            # JSON-RPC sample
            html.Section(
                [
                    html.H2("What a client request looks like", style={"fontSize": "18px", "marginBottom": "8px"}),
                    html.P("Minimal JSON-RPC payloads an MCP client would send:", style={"color": "#666", "marginBottom": "16px"}),
                    html.Div(
                        [
                            html.H3("resources/list — discover what's available", style={"fontSize": "14px", "color": "#444", "marginBottom": "8px"}),
                            html.Pre(
                                '{\n  "jsonrpc": "2.0",\n  "id": 1,\n  "method": "resources/list"\n}',
                                style=_CODE_BLOCK,
                            ),
                        ],
                        style={"marginBottom": "16px"},
                    ),
                    html.Div(
                        [
                            html.H3("resources/read — fetch one by URI", style={"fontSize": "14px", "color": "#444", "marginBottom": "8px"}),
                            html.Pre(
                                '{\n  "jsonrpc": "2.0",\n  "id": 2,\n  "method": "resources/read",\n  "params": {\n    "uri": "llms:///audiences/mcp-clients"\n  }\n}',
                                style=_CODE_BLOCK,
                            ),
                        ]
                    ),
                ],
                style={"marginBottom": "32px"},
            ),

            # Disable opt-out
            html.Section(
                [
                    html.H2("Opt out", style={"fontSize": "18px", "marginBottom": "8px"}),
                    html.P("If you want HTTP-only and no MCP registration:", style={"color": "#666", "marginBottom": "12px"}),
                    html.Pre(
                        "from dash_improve_my_llms import LLMSConfig, add_llms_routes\n\n"
                        "add_llms_routes(app, LLMSConfig(register_mcp_resources=False))",
                        style=_CODE_BLOCK,
                    ),
                ]
            ),

            # Footer nav
            html.Footer(
                [
                    html.Hr(style={"border": "none", "borderTop": "1px solid #eee", "margin": "32px 0 16px"}),
                    html.Div(
                        [
                            dcc.Link("← Home", href="/", style={"color": _BRAND, "textDecoration": "none"}),
                            html.Span(" · ", style={"color": "#ccc", "margin": "0 8px"}),
                            dcc.Link("Web Crawlers →", href="/audiences/web-crawlers", style={"color": _BRAND, "textDecoration": "none"}),
                            html.Span(" · ", style={"color": "#ccc", "margin": "0 8px"}),
                            dcc.Link("Paste-to-chat →", href="/audiences/llm-context", style={"color": _BRAND, "textDecoration": "none"}),
                        ]
                    ),
                ]
            ),
        ],
        style={"maxWidth": "900px", "margin": "0 auto", "padding": "32px 24px"},
    )
