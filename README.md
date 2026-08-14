<div align="center">

<a href="https://2plot.ai"><img src="github_assets/light_mode_2plot.png" alt="2plot.ai" width="220"></a>

# dash-improve-my-llms

**Make a [Plotly Dash](https://dash.plotly.com) app readable to search engines, crawlers and AI agents — without giving up the interactive app.**

Universal prerender · crawler-ready static HTML · `/llms.txt` on every page · rendered `llms.txt` viewer · `robots.txt` + `sitemap.xml` · multi-host network directory · per-request access control · Dash 4.3+ MCP bridge

[![PyPI version](https://img.shields.io/pypi/v/dash-improve-my-llms?color=blue)](https://pypi.org/project/dash-improve-my-llms/)
[![Python](https://img.shields.io/pypi/pyversions/dash-improve-my-llms)](https://pypi.org/project/dash-improve-my-llms/)
[![Dash 4.1+](https://img.shields.io/badge/Dash-4.1%2B-1a1a2e?logo=plotly&logoColor=white)](https://dash.plotly.com/)
[![Backends](https://img.shields.io/badge/backends-flask%20·%20fastapi%20·%20quart-4b8bbe)](#dash-compatibility)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.gg/WEnZR35mrK)
[![YouTube](https://img.shields.io/badge/YouTube-%402plotai-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/channel/UC6Bmo0t0ZUpU_xKBYW0bJuQ)

**[Documentation](https://llms.2plot.dev)** · [Discord](https://discord.gg/WEnZR35mrK) · [YouTube](https://www.youtube.com/channel/UC6Bmo0t0ZUpU_xKBYW0bJuQ) · [GitHub](https://github.com/pip-install-python/dash-improve-my-llms)

<br/>

<a href="https://youtu.be/sC4IDScKlTA"><img src="https://img.youtube.com/vi/sC4IDScKlTA/maxresdefault.jpg" alt="Video demo — dash-improve-my-llms" width="640"></a>

**[▶ Watch the video demo](https://youtu.be/sC4IDScKlTA)**

<br/>

_Maintained by **[Pip Install Python LLC](https://pip-install-python.com)**._

</div>

---

## Overview

A Dash app is a JavaScript application. Ask for any page without running
JavaScript — which is what most crawlers, link previewers and LLM fetchers
do — and you get this:

```html
<div id="react-entry-point">
    <div class="_dash-loading">Loading...</div>
</div>
```

Every URL returns the same empty shell. To a search engine, a 30-page
documentation site looks like 30 identical thin pages. To an agent, it looks
like nothing at all.

`dash-improve-my-llms` fixes that at the framework level. You write each
page's content once, as Markdown, and the package serves it everywhere a
non-JavaScript consumer will look:

| Surface | What lands there |
|---|---|
| The page's own HTML | The prose, rendered into the initial response, before React mounts |
| `/<page>/llms.txt` | The same prose as Markdown, with links back to the site and network indexes |
| `/llms.txt` | An index of every page, plus the cross-host directory |
| `/sitemap.xml` | Every non-hidden page |
| `/robots.txt` | Per-bot-class access policy |
| `dash.mcp` | The same prose as an MCP resource (Dash 4.3+) |

One source of truth, six surfaces, and the interactive app is untouched.

## Installation

```bash
pip install "dash-improve-my-llms[flask]"     # Dash's default backend
pip install "dash-improve-my-llms[fastapi]"   # Dash 4.2+
pip install "dash-improve-my-llms[quart]"     # Dash 4.2+ async
pip install "dash-improve-my-llms[all]"
```

The backend is detected from `app.server`; your code is the same either way.
Requires `dash>=4.1`. See [Dash compatibility](#dash-compatibility) for the
tested matrix.

## Quick start

```python
import dash
from dash import Dash, html
from dash_improve_my_llms import add_llms_routes, RobotsConfig

app = Dash(__name__, use_pages=True)

# Absolute URLs in sitemap.xml, llms.txt and canonical tags come from this.
app._base_url = "https://myapp.com"
app._robots_config = RobotsConfig(block_ai_training=True)

app.layout = html.Div([dash.page_container])

add_llms_routes(app)   # ← the whole integration
```

Then give each page prose, either at module scope:

```python
# pages/equipment.py
LLMS_DOC = """
# Equipment Catalog

> Browse, search and filter the equipment inventory.

Filter by category, availability, or location. Selecting a row opens the
detail view with maintenance history. See [the API guide](/api) for
programmatic access.
"""
```

…or explicitly, which is what you want when pages are generated in a loop:

```python
from dash_improve_my_llms import register_page_metadata

register_page_metadata(
    "/equipment",
    name="Equipment Catalog",
    description="Browse and filter equipment.",
    llms_doc=markdown_text,
)
```

`register_page_metadata` **merges**. Calling it again with only a name will
not erase the prose you registered earlier.

At startup the package names every page that has no prose:

```
UserWarning: dash-improve-my-llms: 4 pages have no LLMS_DOC source
(/changelog, /docs, /privacy, /terms).
```

Treat that warning as a to-do list. Those pages are the ones serving a stub.

## Documentation

Full documentation, served by this package's own demo app — the reference
deployment demonstrates every claim in this README on real URLs:

### 📚 **[llms.2plot.dev](https://llms.2plot.dev)**

Every page there also serves `/<page>/llms.txt` — the prose as Markdown,
ready to paste into a chat window. You can run the same site locally:

```bash
pip install -r requirements.txt
python app.py                 # open http://localhost:8959
```

## How the content gets served

Two independent paths, both on by default:

**1. Universal prerender.** Every visitor's initial HTML carries the page's
prose inside `#react-entry-point`, plus a per-page `<title>`, meta
description, canonical URL, and JSON-LD. Dash's `createRoot().render()`
replaces that block when React mounts, so the live app is unaffected — but
anything that reads the HTML without executing it sees real content.

**2. Crawler short-circuit.** A recognised crawler gets a complete static
HTML document before Dash runs at all. Cheaper, and it covers clients that
would choke on the app shell entirely.

The prerender is what makes this *not* cloaking: users and crawlers receive
the same content. Google
[deprecated dynamic rendering as a recommendation in 2022](https://developers.google.com/search/docs/crawling-indexing/javascript/dynamic-rendering),
and a stub-for-users/prose-for-crawlers split is the pattern that gets
flagged. Serving real HTML to everyone sidesteps the question and improves
LCP at the same time.

To fall back to crawler-only rendering:

```python
add_llms_routes(app, LLMSConfig(prerender=False))
```

## `llms.txt` is a document, not a dead end

A page's `llms.txt` gets fetched in isolation — pasted into a chat, handed to
an agent. On its own it says everything about that page and nothing about
where it sits, so there is nothing to follow and exploration stops. Each one
therefore opens with three lines of orientation:

```markdown
# FastAPI Showcase

> What the FastAPI backend unlocks in this boilerplate.

**Site index:** [https://docs.example.com/llms.txt](…) — every page on this site, as Markdown.
**Network index:** [https://hub.example.com/llms.txt](…) — The Example Network; start here to discover sibling sites.
**Sitemap:** https://docs.example.com/sitemap.xml
```

Disable with `LLMSConfig(llms_nav=False)`.

### The same URL, rendered, for people

Paste that URL into a browser and you get the document rendered behind a
header carrying the network identity — and, if you point the app at a
[bulletin endpoint](docs/BULLETIN.md), centrally-published tips and
announcements that one host controls for the whole network.

Agents, crawlers, curl and link unfurlers receive the Markdown byte for byte.
The header exists **only** in the HTML variant, so it costs an agent nothing —
which is why it isn't simply prepended to the Markdown for everyone.

```
Accept: */*                       → text/markdown
Accept: text/html (real browser)  → text/html, rendered
Accept: text/html (Googlebot UA)  → text/markdown
?raw=1                            → text/markdown, always
?format=html                      → text/html, always
```

Every variant sends `Vary: Accept`, and the rendered view is `noindex` so it
never competes with the real page. Disable with
`LLMSConfig(llms_viewer=False)`.

## Multi-domain networks

Sitemaps are scoped to one origin, so a network spread across hosts has no
crawl graph between them. An agent that lands on `maps.example.com` has
no path to `email.example.com`; a model reasoning about eighteen packages
sees one.

Declare the relationships explicitly and they appear in `/llms.txt`, in the
prerendered HTML, and as `<link rel="related">`:

```python
from dash_improve_my_llms import register_network

register_network(
    name="The Example Network",
    description="A family of open-source Dash component libraries.",
    hub_url="https://hub.example.com",    # one host an agent can enumerate from

    # Same network, same operator.
    peers=[
        {"name": "Hub", "url": "https://hub.example.com",
         "description": "Network index and account origin."},
        {"name": "Maps", "url": "https://maps.example.com",
         "description": "Mapping components for Dash."},
    ],

    # Yours, on its own unrelated domain.
    affiliated=[
        {"name": "Side Project", "url": "https://sideproject.example",
         "description": "A separate product built on the same stack."},
    ],

    # Third-party docs you depend on. Emitted with rel="nofollow".
    external=[
        {"name": "Dash Mantine Components",
         "url": "https://www.dash-mantine-components.com",
         "description": "UI layer these docs are built with."},
    ],
)
```

The three tiers stay distinct on purpose. Flattening them would either
overclaim ownership of third-party sites or bury your own network in an
undifferentiated link list — and both make the directory less useful to
whatever is reading it.

See [`docs/NETWORKS.md`](docs/NETWORKS.md) for the full multi-domain guide and
[`docs/BULLETIN.md`](docs/BULLETIN.md) for the shared tips/announcements
contract.

## Access control

Static hiding first — excluded from every surface, 404 to crawlers, never
prerendered, absent from MCP:

```python
from dash_improve_my_llms import mark_hidden

mark_hidden("/admin")
```

For applications with accounts, `configure_access` decides **per request**
who may read a document, across every surface the package owns:

```python
from dash_improve_my_llms import configure_access

configure_access(
    check,                    # (path) -> "allow" | "gated" | "deny"
    gate_doc=my_gate_doc,     # Markdown served instead of gated prose (200)
    link_suffix=my_suffix,    # authority carried in generated links
)
```

- **`allow`** serves the prose. **`gated`** serves the gate document at 200
  and keeps the URL listed — the page's existence is public, its content is
  not. **`deny`** is a 404 and delisted, indistinguishable from a page that
  never existed.
- A check that raises degrades to `gated` — a bug can neither publish gated
  prose nor black-hole the site.
- `link_suffix` lets a signed-in user's copied URL carry its own authority,
  so the one consumer these documents exist for — an agent fetching with no
  cookie — still gets in.
- `configure_viewer_identity(provider)` renders the signed-in reader in the
  HTML viewer's header; agents receive byte-identical Markdown without it.
  Identity- or authority-bearing responses send
  `Cache-Control: private, no-store` so no CDN can hand one visitor's
  document to the next.

The full contract is in [`docs/ACCESS.md`](docs/ACCESS.md).

## Dash compatibility

Verified against every supported Dash release on all three backends —
`scripts/matrix.py` reproduces the CI matrix locally.

| Dash | Flask | FastAPI | Quart |
|---|---|---|---|
| 4.1.0 | ✅ | — ¹ | — ¹ |
| 4.2.0 | ✅ | ✅ | ✅ |
| 4.3.0 | ✅ | ⚠️ ² | ✅ |
| 4.4.0 | ✅ | ✅ | ✅ |
| 4.4.1 | ✅ | ✅ | ✅ |

¹ Dash 4.1.0 has no pluggable backends; `Dash(backend=...)` does not exist.

² **Dash 4.3.0's FastAPI backend is broken upstream.** Its page catch-all
does not call `set_current_request()`, so every non-root URL raises
`RuntimeError: No active request in context` and returns a 500. This
reproduces on a stock Dash app with this package uninstalled, and is fixed
in Dash 4.4.0. The package warns at startup if it detects the combination.
Use `dash>=4.4.0`, or run Flask/Quart on 4.3.0.

## Markdown support

`LLMS_DOC` is rendered by a dependency-free subset renderer covering
headings, paragraphs, **links**, fenced code, images, blockquotes, ordered
and unordered lists, pipe tables, horizontal rules, and inline
`code`/bold/italic/strikethrough.

Links matter most: they are what gives your prose an internal crawl graph.
`[the API guide](/api)` becomes a real `<a href="/api">` in the served HTML.

All content is escaped before any tag is emitted, link targets are checked
against a scheme allowlist, and JSON-LD is `\u`-escaped so author-supplied
page names cannot break out of their `<script>` block.

rST-style directives (`.. toc::`, `.. llms_copy::`) are stripped from prose
but preserved inside code fences, so a page documenting them still renders
its examples.

## API reference

| Function | Purpose |
|---|---|
| `add_llms_routes(app, config=None)` | Wire up everything |
| `LLMSConfig(...)` | `enabled`, `warn_missing_llms_doc`, `register_mcp_resources`, `prerender`, `llms_nav`, `llms_viewer` |
| `RobotsConfig(...)` | Bot-class policy for `/robots.txt` |
| `register_page_metadata(path, ...)` | Per-page name/description/prose (merges) |
| `mark_hidden(path)` / `is_hidden(path)` | Exclude a page from every surface |
| `register_network(...)` | Declare the whole cross-host directory |
| `register_network_site(name, url, tier=...)` | Add one site |
| `describe_network(...)` | Name the network and its hub |
| `configure_bulletin(url=...)` | Opt in to hub-published tips / announcements |
| `configure_access(check, ...)` | Per-request allow / gated / deny on every surface |
| `configure_viewer_identity(provider)` | Show the signed-in reader in the HTML viewer |

## Development

```bash
pip install -e ".[dev]"

pytest tests --ignore=tests/legacy          # unit + adapter tests
python scripts/smoke_test.py                # boot a real app, all backends
python scripts/matrix.py                    # every Dash version
python scripts/matrix.py --pytest           # ...and the full suite in each
```

CI runs the same matrix on every push. Releases publish to PyPI from a
version tag via trusted publishing; see `.github/workflows/cd.yml`.

## What this package deliberately does not do

It does not introspect layouts or callbacks. Dash 4.3's MCP server exposes
that live and structured, and duplicating it means maintaining a worse copy.
`mark_important()` and `mark_component_hidden()` are deprecated no-ops —
put emphasis in your `LLMS_DOC` instead.

## Community & support

Come build with us:

- 💬 **Discord** — [discord.gg/WEnZR35mrK](https://discord.gg/WEnZR35mrK)
- ▶️ **YouTube** — [@2plotai](https://www.youtube.com/channel/UC6Bmo0t0ZUpU_xKBYW0bJuQ)
- 🐛 **Issues** — [github.com/pip-install-python/dash-improve-my-ai/issues](https://github.com/pip-install-python/dash-improve-my-ai/issues)

## More from Pip Install Python LLC

dash-improve-my-llms is one of several tools built and maintained by
**Pip Install Python LLC**:

| Project | What it is |
|---|---|
| 📚 **[Pip Install Python](https://pip-install-python.com)** | Open-source documentation index for the Python & Dash ecosystem |
| 🗺️ **[dash-leaflet2](https://pypi.org/project/dash-leaflet2/)** | Leaflet 2-native mapping components for Dash 4 |
| 🎞️ **[dash-nle-timeline](https://pypi.org/project/dash-nle-timeline/)** | Frame-accurate NLE timeline & scene compositor for Dash |
| 🔀 **[PiratesBargain.com](https://piratesbargain.com)** | E-commerce / digital commerce |
| 🧠 **[ai-agent.buzz](https://ai-agent.buzz)** | Infinite AI canvas |
| 🎬 **[2plot.media](https://2plot.media)** | Videography application |

## License

MIT — see [LICENSE](LICENSE). Built by
**[Pip Install Python LLC](https://pip-install-python.com)** to make Dash
apps first-class citizens of the agentic web.
