# dash-improve-my-llms

**Crawler / SEO companion for Dash apps, with a thin MCP bridge for Dash 4.3+.**

[![PyPI version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://pypi.org/project/dash-improve-my-llms/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Dash 3.x · 4.1+](https://img.shields.io/badge/dash-3.x%20·%204.1+-blue.svg)](https://dash.plotly.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## What 2.0 is

A small package that handles the parts of "making your Dash app
AI-friendly" that Dash itself doesn't:

- **`/robots.txt`** — bot-class access policies (block AI training,
  allow AI search, etc.)
- **`/sitemap.xml`** — generated from `dash.page_registry` minus hidden
  pages
- **`/<page>/llms.txt`** — each page's hand-written prose at a
  predictable URL
- **Static-HTML prerender** — bot middleware serves crawlers the prose
  view instead of an empty Dash JS shell
- **MCP bridge** — registers each page's prose as a `dash.mcp` resource
  on Dash 4.3+

It does **not** try to introspect your layouts or callbacks. Dash 4.3's
MCP server does that natively and better.

## The three audiences

| Audience              | How they reach the app          | What 2.0 serves them                         |
|-----------------------|---------------------------------|----------------------------------------------|
| MCP clients           | JSON-RPC over Streamable HTTP   | `LLMS_DOC` registered as `dash.mcp` resource |
| Web crawlers          | Plain HTTPS, often no JS        | `/robots.txt`, `/sitemap.xml`, static HTML   |
| Paste-into-chat users | One-shot HTTP fetch             | `/llms.txt`, `/<page>/llms.txt` as markdown  |

FastAPI's `/docs` describes HTTP routes, not callbacks or layouts. MCP
fills that gap for audience #1. Audiences #2 and #3 are unchanged by
either — and they have no native Dash story. That's the gap this
package fills.

## Install

Pick the extra that matches your Dash backend:

```bash
pip install "dash-improve-my-llms[flask]"     # Dash 3.x (default)
pip install "dash-improve-my-llms[fastapi]"   # Dash 4.1+
pip install "dash-improve-my-llms[quart]"     # Dash 4.1+ async
pip install "dash-improve-my-llms[all]"       # all three
```

The package detects which backend `app.server` is using and dispatches
to the right adapter. Your code looks the same regardless.

## Quick start

```python
from dash import Dash, register_page
from dash_improve_my_llms import add_llms_routes, RobotsConfig, mark_hidden

app = Dash(__name__, use_pages=True)
app._base_url = "https://myapp.com"
app._robots_config = RobotsConfig(
    block_ai_training=True,    # GPTBot, CCBot, anthropic-ai → 403
    allow_ai_search=True,      # ClaudeBot, ChatGPT-User → allowed
    allow_traditional=True,    # Googlebot, Bingbot → allowed
)

mark_hidden("/admin")
add_llms_routes(app)

if __name__ == "__main__":
    app.run(debug=True)
```

Every page module then exports the prose for its own `/llms.txt`:

```python
# pages/equipment.py
from dash import html, register_page

register_page(__name__, path="/equipment", name="Equipment Catalog")

LLMS_DOC = """\\
# Equipment Catalog

Browse the equipment library with text search and a category dropdown.

## What this page does
...
"""

def layout():
    return html.Div([...])
```

That's the whole pattern. The `LLMS_DOC` string IS the body of
`/equipment/llms.txt`, byte-for-byte.

If a page has no `LLMS_DOC`, you'll see a single `UserWarning` at
`add_llms_routes()` naming the missing pages, and the endpoint returns
a small placeholder stub so bots still get a 200.

## What gets served

| Route | What it returns | For |
|---|---|---|
| `/llms.txt` | Home page's `LLMS_DOC` | Paste-into-chat |
| `/<page>/llms.txt` | That page's `LLMS_DOC` | Paste-into-chat, AI-aware crawlers |
| `/robots.txt` | Bot policy generated from `RobotsConfig` | Crawlers |
| `/sitemap.xml` | Non-hidden pages from `page_registry` | Crawlers, search engines |
| (any URL with crawler UA) | Static HTML with the page's `LLMS_DOC` rendered | Crawlers that can't run JS |

Plus, on Dash 4.3+:

| Surface | What | For |
|---|---|---|
| `llms:///<page-path>` | MCP resource carrying that page's `LLMS_DOC` | Claude Desktop, agentic IDEs, MCP clients |

## Public API

```python
from dash_improve_my_llms import (
    add_llms_routes,           # main entry point
    LLMSConfig,                # opt-out flags
    RobotsConfig,              # bot-class policies
    register_page_metadata,    # name, description, llms_doc, schema.org fields
    mark_hidden,               # exclude path from sitemap/robots/MCP
    is_hidden,                 # query
)
```

### `LLMSConfig`

```python
LLMSConfig(
    enabled=True,                       # set False to no-op the package
    warn_missing_llms_doc=True,         # the startup UserWarning
    register_mcp_resources=True,        # set False to skip MCP bridge
)
```

### `RobotsConfig`

```python
RobotsConfig(
    block_ai_training=True,
    allow_ai_search=True,
    allow_traditional=True,
    crawl_delay=10,                     # seconds between requests
    custom_rules=[],                    # extra robots.txt lines
    disallowed_paths=["/admin"],
)
```

## Bot classes

The middleware classifies User-Agents into three buckets:

- **AI Training** (default: blocked) — GPTBot, anthropic-ai,
  Claude-Web, CCBot, Google-Extended, FacebookBot, Omgili, ByteSpider
- **AI Search** (default: allowed) — ChatGPT-User, ClaudeBot,
  PerplexityBot, OAI-SearchBot
- **Traditional** (default: allowed) — Googlebot, Bingbot, DuckDuckBot,
  Yandex, plus generic patterns

Verify with curl:

```bash
# Training bot — 403 when block_ai_training=True
curl -A "Mozilla/5.0 (compatible; GPTBot/1.0)" https://myapp.com/

# Search bot — prerendered static HTML
curl -A "Mozilla/5.0 (compatible; Googlebot/2.1)" https://myapp.com/
```

## The MCP bridge

When `dash.mcp` is available (Dash 4.3+ RC and later), 2.0 registers
each non-hidden page's `LLMS_DOC` as an MCP resource:

- **URI**: `llms:///<page-path>` (e.g. `llms:///audiences/mcp-clients`)
- **mimeType**: `text/markdown`
- **content**: the page's `LLMS_DOC`, byte-for-byte identical to
  `/<page>/llms.txt`

MCP-aware clients (Claude Desktop, agentic IDEs) can `resources/list`
to discover what's available and `resources/read` by URI to fetch.

On Dash 3.x or 4.1/4.2 stable, the bridge is a silent no-op — only
the HTTP surfaces serve docs.

## Migrating from 1.x

Most of the change is removal. Run the package against your app and
the startup `UserWarning` will tell you which pages need attention.

1. **Add `LLMS_DOC`** at module scope on each page module:

   ```python
   LLMS_DOC = """\\
   # Page Title

   Short description.

   ## What this page does
   ...
   """
   ```

   Or pass it via `register_page_metadata(path, llms_doc="...")`.

2. **Remove `mark_important()` and `mark_component_hidden()` calls.**
   They're deprecation no-ops in 2.0 and will be deleted in 2.1.

3. **Remove links to dropped routes**: `/page.json`,
   `/architecture.txt`, `/architecture.toon`, `/llms.toon` (and their
   per-page variants) all return 404 now.

4. **Install the matching backend extra**: `[flask]`, `[fastapi]`, or
   `[quart]`. The bare `dash-improve-my-llms` install no longer pulls
   Flask automatically.

The HTTP surfaces that survived (`/llms.txt`, `/robots.txt`,
`/sitemap.xml`) and the `RobotsConfig`, `mark_hidden`,
`register_page_metadata` APIs are byte-compatible with 1.x.

## Example app

This repository's `app.py` is a working demo. From a clone:

```bash
pip install -e ".[all,dev]"
python app.py
# Browse http://localhost:8959/
```

The `/audiences/*` pages walk through each of the three audiences in
the running app, including a copy-to-clipboard demo for grabbing any
page's prose.

## Documentation

- [docs/SKILLS.md](docs/SKILLS.md) — practical guide for using and
  configuring the package (also written as a reference for AI coding
  assistants)
- [CHANGELOG.md](CHANGELOG.md) — full release history including 1.x

## License

MIT. See [LICENSE](LICENSE).

Built by [Pip Install Python LLC](https://pip-install-python.com).
