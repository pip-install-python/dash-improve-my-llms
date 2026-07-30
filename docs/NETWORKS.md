# Configuring a multi-domain network

How to make a family of separately-hosted Dash apps legible as one
ecosystem to search engines and AI agents.

This guide is written for the case where you run more than one app: a
primary domain, a set of subdomains, some projects on their own unrelated
domains, and dependencies on third-party documentation. If you run a single
app on a single host, you don't need any of this — `add_llms_routes(app)` is
the whole story.

---

## Why per-host SEO isn't enough

Each surface the package already serves is scoped to one origin:

- `sitemap.xml` **must** only list URLs on its own host. That's the spec.
- Internal links in prose point within the app.
- `robots.txt` governs one host.

So a network of twenty hosts produces twenty disconnected islands. Nothing
in any of them says the other nineteen exist.

The consequences differ by audience, and the second one is the expensive
one:

**Search engines** treat cross-host links as weak signals, but they at least
have crawlers that follow them. Given enough time and enough inbound links,
Google will find your subdomains.

**Agents don't crawl.** A model answering a question about your ecosystem
fetches one or two URLs and reasons from what came back. If it lands on
`leaflet.example.dev`, it sees one library. There is no second request, no
link graph traversal, no accumulation over time. Whatever that one page
says *is* the ecosystem as far as that answer is concerned.

Fixing this needs an explicit, machine-readable statement of the
relationships, served from every host.

---

## The three tiers

```python
from dash_improve_my_llms import register_network

register_network(
    name="The 2plot network",
    description=(
        "A family of open-source Dash component libraries and the "
        "applications built on them."
    ),
    hub_url="https://2plot.dev",
    peers=[...],
    affiliated=[...],
    external=[...],
)
```

### `peers` — same network, same operator

The hosts you own that are genuinely part of one product family.

```python
peers=[
    {"name": "2plot.ai", "url": "https://2plot.ai",
     "description": "Network hub, account origin, and the heartbeat."},
    {"name": "2plot.dev", "url": "https://2plot.dev",
     "description": "Package index for every open-source component."},
    {"name": "dash-leaflet2", "url": "https://leaflet.2plot.dev",
     "description": "Leaflet maps as Dash components."},
    {"name": "Documentation boilerplate", "url": "https://boilerplate.2plot.dev",
     "description": "The markdown-driven docs template these sites use."},
]
```

Peers get `<link rel="related">` tags in `<head>`, a `## Network` section in
`/llms.txt`, and followed links in the prerendered HTML. This is the tier
that builds your actual cross-host graph, so put real relationships here and
nothing else.

### `affiliated` — yours, on its own domain

Projects you built, on domains that aren't part of the primary brand.

```python
affiliated=[
    {"name": "Pirate's Bargain", "url": "https://piratesbargain.com",
     "description": "Deal aggregator. Same Dash stack, separate product."},
    {"name": "ai-agent.buzz", "url": "https://ai-agent.buzz",
     "description": "Agent tooling directory."},
]
```

Listed under `## Related projects`, with followed links. Separating these
from `peers` is what lets an agent answer "what is the 2plot network?"
without sweeping in every unrelated domain you happen to own — while still
being able to find them when asked what else you've built.

### `external` — third-party references

Documentation you depend on or point users at. **Not yours.**

```python
external=[
    {"name": "Dash Mantine Components",
     "url": "https://www.dash-mantine-components.com",
     "description": "The UI component layer these docs are built on."},
    {"name": "Plotly Dash documentation", "url": "https://dash.plotly.com",
     "description": "Upstream framework documentation."},
]
```

Listed under `## External references` and emitted with
`rel="nofollow noopener"`. They are references, not endorsements, and
shouldn't pass ranking signal.

Point at the machine-readable URL when one exists:

```python
{"name": "Dash Mantine Components",
 "url": "https://www.dash-mantine-components.com",
 "llms_txt": "https://www.dash-mantine-components.com/llms.txt"}
```

`llms_txt` defaults to `{url}/llms.txt`. Set it explicitly when the site
puts its document somewhere else — or when it has none, in which case point
at the best available documentation URL rather than a 404.

---

## The hub

```python
register_network(hub_url="https://2plot.dev", ...)
```

The single most valuable piece. One canonical host that lists every member
means an agent has exactly one URL to fetch and enumerate from, instead of
depending on which member it happened to reach first.

The hub is an ordinary app running this package, with every other host in
its `peers`. Its `/llms.txt` becomes the network manifest:

```
# 2plot.dev

> Package index for the 2plot network.

## Pages
- [dash-leaflet2](https://2plot.dev/pip/leaflet): Leaflet maps for Dash.
  - Machine-readable: https://2plot.dev/pip/leaflet/llms.txt
...

## Network
- [2plot.ai](https://2plot.ai): Network hub and account origin.
  - Machine-readable: https://2plot.ai/llms.txt
...
```

Once that exists, an MCP server over the network is a thin wrapper around
documents that are already being served.

### Tiered hubs

`hub_url` points **one level up**, not all the way to the root. A network with
a root domain and a subdomain family therefore forms a chain:

```
leaflet.2plot.dev   hub_url = https://2plot.dev     ─┐
llms.2plot.dev      hub_url = https://2plot.dev      ├─ subdomains name the section hub
email.2plot.dev     hub_url = https://2plot.dev     ─┘

2plot.dev           hub_url = https://2plot.ai      ─── the section hub names the root

2plot.ai            hub_url = (unset, or itself)    ─── the root
```

Every `llms.txt` then has exactly one unambiguous "up" link, and an agent
walks the chain: page → site index → section hub → root.

The alternative — pointing every subdomain straight at the root — is one hop
shorter but strictly worse. It leaves the section hub with no inbound
relationship from the sites it indexes, so `2plot.dev` stops being discoverable
from the very hosts it exists to catalogue, and an agent landing on a subdomain
never learns that the component index exists at all.

Cost of the chain: two fetches to reach the root instead of one. That is
cheap, and each hop tells the reader something — which is not true of a flat
list of ten peers with no structure.

---

## Branding the viewer banner

The rendered `llms.txt` view carries a wordmark. Supply it as data, either
locally or from the [bulletin](BULLETIN.md) — the package ships none of its
own, so nothing here is tied to one network's identity.

Two forms. A **morse mark**, which encodes a word as columns of dots and
dashes:

```python
register_network(
    name="2plot.ai",
    wordmark={"morse": "plot", "prefix": "2", "suffix": ".ai", "label": "2plot.ai"},
)
```

That draws `2` + morse(`plot`) + `.ai` — the string `2.--. .-.. --- -.ai` — as
inline SVG: a metallic prefix and suffix, magenta dots, rounded dashes, and an
upward arrow in place of a trailing `i`. The symbols key on in sequence left to
right, like a signal being transmitted, which is the one animation a
machine-readable-documentation site has actually earned.

Or **ASCII art**, as a list of lines:

```python
register_network(wordmark=["  ___  ", " / _ \\ ", " \\___/ "])
```

A bulletin-published mark overrides a local one, so a hub can restyle every
satellite without redeploying any of them.

## Shared configuration across apps

Twenty apps each hand-maintaining the same directory will drift. Keep the
definition in one module and import it everywhere.

```python
# network_directory.py — vendored, or its own small package
PEERS = [
    {"name": "2plot.ai", "url": "https://2plot.ai",
     "description": "Network hub and account origin."},
    # ...
]

AFFILIATED = [...]
EXTERNAL = [...]


def apply(app_url: str) -> None:
    """Register the network from the perspective of the app at app_url."""
    from dash_improve_my_llms import register_network

    register_network(
        name="The 2plot network",
        description="A family of open-source Dash component libraries.",
        hub_url="https://2plot.dev",
        # An app should not list itself as its own peer.
        peers=[p for p in PEERS if p["url"].rstrip("/") != app_url.rstrip("/")],
        affiliated=AFFILIATED,
        external=EXTERNAL,
    )
```

Then in each app:

```python
import network_directory

app._base_url = "https://leaflet.2plot.dev"
network_directory.apply(app._base_url)
add_llms_routes(app)
```

Filtering the app's own URL out of `peers` matters: a site listing itself as
a peer of itself is noise, and it makes the directory look generated rather
than curated.

---

## Per-app landing content

The network directory is context, not content. Each app still needs its own
`/` prose saying what *it* is — that's what the root `/llms.txt` leads with,
before the page list and the directory.

```python
register_page_metadata(
    "/",
    name="dash-leaflet2",
    description="Leaflet maps as Dash components.",
    llms_doc="""
# dash-leaflet2

> Interactive Leaflet maps as first-class Dash components.

Markers, GeoJSON layers, tile providers, and draw controls, all
callback-addressable. Install with `pip install dash-leaflet2`.

## What this documentation covers
...
""",
)
```

The resulting `/llms.txt` reads: what this app is → every page in it → the
rest of the network → third-party references. An agent can stop at any
depth and have something coherent.

---

## Verifying

```bash
curl https://leaflet.2plot.dev/llms.txt          # index + directory
curl https://leaflet.2plot.dev/api/llms.txt      # one page's prose
curl https://leaflet.2plot.dev/sitemap.xml       # this host only

# What a crawler sees — the body must not be the JavaScript stub.
curl -A "Googlebot/2.1" https://leaflet.2plot.dev/api | grep -A5 "<main>"

# What a browser sees — same content, before hydration.
curl https://leaflet.2plot.dev/api | grep -c "dimll-prerender"
```

Across the whole network, the checks worth automating are:

1. No page body contains `This page contains interactive content that
   requires JavaScript` — that string means prose is missing.
2. Every host's `/llms.txt` returns 200 and contains `## Pages`.
3. Every `llms_txt` URL in every directory returns 200. A directory full of
   404s is worse than no directory.
4. `<link rel="canonical">` matches the host actually being served — a
   stale `_base_url` copied between apps will point every canonical at the
   wrong domain and deindex the app.

Item 4 is the one that bites when apps are forked from a shared template.
