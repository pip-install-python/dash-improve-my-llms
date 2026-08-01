"""
Multi-domain networks — making a family of hosts legible as one ecosystem.

Demonstrates register_network() with all three tiers and shows the live
directory this demo app is configured with.
"""

import dash_mantine_components as dmc
from dash import dcc, html, register_page

from dash_improve_my_llms import _state
from lib.constants import OG_IMAGE_URL, PAGE_TITLE_PREFIX

_DESCRIPTION = (
    "Explains and demonstrates register_network() — the API that turns a set "
    "of independently-hosted Dash apps into a directory that search engines "
    "and AI agents can traverse."
)

register_page(
    __name__,
    path="/networks",
    name="Multi-Domain Networks",
    title=f"{PAGE_TITLE_PREFIX}Multi-Domain Networks",
    description=_DESCRIPTION,
    image_url=OG_IMAGE_URL,
)


LLMS_DOC = """\
# Multi-Domain Networks

> One app on one host is easy. A family of apps across subdomains and
> separate domains needs the relationships stated explicitly, because
> nothing else states them.

## What this page does

Explains and demonstrates `register_network()` — the API that turns a set
of independently-hosted Dash apps into a directory that search engines and
AI agents can traverse.

## The problem it solves

Every SEO surface this package serves is scoped to a single origin, because
that is what the specifications require:

- `sitemap.xml` may only list URLs on its own host.
- `robots.txt` governs one host.
- Prose links point within the app.

Run twenty hosts and you get twenty disconnected islands. Nothing on any of
them mentions the other nineteen.

For search engines that is a slow problem — crawlers do follow cross-host
links eventually. For AI agents it is a hard wall. An agent answering a
question fetches a URL or two and reasons from what comes back. It does not
crawl, does not accumulate a graph over time, and does not come back later.
Whatever that one response says *is* the ecosystem, for that answer.

## The three tiers

`register_network()` takes three separate lists, and the separation is the
point.

- **`peers`** — hosts you own that are genuinely one product family.
  Emitted with `<link rel="related">` and followed links. This is the tier
  that builds your real cross-host graph.
- **`affiliated`** — your projects on unrelated domains. Listed under
  "Related projects", followed. Separated so an agent can answer "what is
  this network?" without sweeping in every domain you happen to own.
- **`external`** — third-party documentation you reference but do not own.
  Emitted with `rel="nofollow noopener"`, because a reference is not an
  endorsement and should not pass ranking signal.

Collapsing the tiers would either overclaim ownership of other people's
sites or bury your own network in an undifferentiated link list.

## What the user can do

- Read the worked configuration below and copy it.
- Fetch `/llms.txt` on this app to see the rendered directory.
- Inspect this page's HTML source for the `<link rel="related">` tags.

## Configuration

```python
from dash_improve_my_llms import register_network

register_network(
    name="The 2plot network",
    description="A family of open-source Dash component libraries.",
    hub_url="https://2plot.dev",
    peers=[
        {"name": "2plot.ai", "url": "https://2plot.ai",
         "description": "Network hub and account origin."},
        {"name": "dash-leaflet2", "url": "https://leaflet.2plot.dev",
         "description": "Leaflet maps as Dash components."},
    ],
    affiliated=[
        {"name": "Pirate's Bargain", "url": "https://piratesbargain.com",
         "description": "Deal aggregator on the same stack."},
    ],
    external=[
        {"name": "Dash Mantine Components",
         "url": "https://www.dash-mantine-components.com",
         "description": "The UI layer these docs are built with."},
    ],
)
```

## The hub

`hub_url` is the highest-value field. One canonical host listing every
member gives an agent exactly one URL to land on and enumerate from,
instead of depending on which member it happened to reach first. The hub is
an ordinary app running this package with every other host in its `peers`;
its `/llms.txt` becomes the network manifest.

## Keeping twenty apps in sync

Define the directory once in a shared module and import it everywhere.
Filter the current app's own URL out of `peers` — a site listing itself as
its own peer is noise. See `docs/NETWORKS.md` for the pattern.

## What it does NOT do

It does not verify that the hosts you list exist, respond, or serve an
`llms.txt`. A directory full of dead links is worse than no directory, so
check them in CI. It also does not federate content: each host still serves
its own prose, and the directory only says how they relate.
"""


def _tier_table(tier: str, empty_note: str):
    sites = _state.network.by_tier(tier)
    if not sites:
        return dmc.Alert(empty_note, color="gray", variant="light")

    return dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(html.Tr([html.Th("Name"), html.Th("URL"), html.Th("Description")])),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(site.name),
                            html.Td(dcc.Link(site.url, href=site.url, target="_blank")),
                            html.Td(site.description or "—"),
                        ]
                    )
                    for site in sites
                ]
            ),
        ],
    )


def layout():
    network = _state.network

    header = dmc.Stack(
        gap="xs",
        children=[
            dmc.Title("Multi-Domain Networks", order=1),
            dmc.Text(
                "Making a family of separately-hosted apps legible as one "
                "ecosystem to crawlers and agents.",
                c="dimmed",
                size="lg",
            ),
        ],
    )

    identity = dmc.Paper(
        withBorder=True,
        p="md",
        radius="md",
        children=dmc.Stack(
            gap="xs",
            children=[
                dmc.Text("This app's network identity", fw=600),
                dmc.Text(f"Name: {network.name or '(not set)'}", size="sm"),
                dmc.Text(f"Hub: {network.hub_url or '(not set)'}", size="sm"),
                dmc.Text(
                    f"Sites registered: {len(network.sites)}",
                    size="sm",
                    c="dimmed",
                ),
            ],
        ),
    )

    return dmc.Container(
        size="lg",
        py="xl",
        children=dmc.Stack(
            gap="xl",
            children=[
                header,
                identity,
                dmc.Alert(
                    "Every tier below is rendered into /llms.txt and into this "
                    "page's prerendered HTML. Peers additionally get "
                    '<link rel="related"> tags; external references get '
                    'rel="nofollow".',
                    title="Where this data ends up",
                    color="blue",
                    variant="light",
                ),
                dmc.Stack(
                    gap="sm",
                    children=[
                        dmc.Title("Peers — same network, same operator", order=3),
                        _tier_table(
                            "peer",
                            "No peers registered. Call register_network(peers=[...]).",
                        ),
                    ],
                ),
                dmc.Stack(
                    gap="sm",
                    children=[
                        dmc.Title("Affiliated — yours, on its own domain", order=3),
                        _tier_table(
                            "affiliated",
                            "No affiliated sites registered.",
                        ),
                    ],
                ),
                dmc.Stack(
                    gap="sm",
                    children=[
                        dmc.Title("External — third-party references", order=3),
                        _tier_table(
                            "external",
                            "No external references registered.",
                        ),
                    ],
                ),
                dmc.Stack(
                    gap="sm",
                    children=[
                        dmc.Title("See it live", order=3),
                        dmc.List(
                            [
                                dmc.ListItem(
                                    dcc.Link(
                                        "/llms.txt — the rendered directory",
                                        href="/llms.txt",
                                    )
                                ),
                                dmc.ListItem(
                                    dcc.Link(
                                        "/networks/llms.txt — this page as Markdown",
                                        href="/networks/llms.txt",
                                    )
                                ),
                            ]
                        ),
                    ],
                ),
            ],
        ),
    )
