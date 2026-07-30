# The network bulletin

A contract for one host to publish tips and announcements that every other
site in a network renders in its `llms.txt` viewer header.

Twenty documentation sites have no shared place to say "here is what changed
this week" without twenty commits. The bulletin gives them one: the hub
serves a small JSON document, every satellite fetches and renders it, and the
message is written once.

---

## What renders where

The bulletin appears **only in the browser-facing view** of an `llms.txt`
document. Agents and crawlers fetching the same URL receive the Markdown
unchanged, with no banner and no bulletin bytes.

That split is the whole design. The banner is chrome for people; putting it
in the Markdown would charge every agent tokens for content it did not ask
for and cannot use.

```
GET /guide/llms.txt
  Accept: */*                        → text/markdown, no banner
  Accept: text/html (real browser)   → text/html, banner + rendered document
  Accept: text/html (Googlebot UA)   → text/markdown, no banner
  ?raw=1                             → text/markdown, always
  ?format=html                       → text/html, always (for previewing)
```

Both variants send `Vary: Accept` so a CDN cannot serve a cached HTML body to
the next agent that asks for the document.

---

## Consuming it

```python
from dash_improve_my_llms import configure_bulletin

configure_bulletin(
    url="https://2plot.dev/api/network/bulletin",
    ttl=900,      # seconds before the cached copy is refreshed
    timeout=3.0,  # socket timeout for the fetch
)
```

Fetching is **opt-in**. Without this call the package makes no outbound
requests at all — an open-source library that phones home by default is not a
surprise anyone wants in their deployment.

Three guarantees, because this puts a remote dependency in front of a route
that has to keep working:

- **It never blocks a response.** Requests read the cache and return.
  Refreshes run on a daemon thread. The first request after startup renders
  without a bulletin rather than waiting for one.
- **It never raises.** Timeout, DNS failure, malformed JSON, wrong shape,
  hostile payload — all degrade to "no bulletin". A page does not 500 because
  a sibling host is down.
- **A failed fetch backs off** for one TTL instead of retrying on every
  request that notices the cache is stale.

---

## Producing it

Serve JSON from any route on the hub. On a Dash app with a FastAPI backend:

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/network/bulletin")
def bulletin():
    return {
        "version": 1,
        "network": {
            "name": "2plot.ai",
            "tagline": "Open-source Dash component libraries.",
            "url": "https://2plot.ai",
            "llms_txt": "https://2plot.dev/llms.txt",
            "wordmark": [
                " ██████  ██████  ██       ██████  ████████",
                "      ██ ██   ██ ██      ██    ██    ██   ",
                "  █████  ██████  ██      ██    ██    ██   ",
                " ██      ██      ██      ██    ██    ██   ",
                " ███████ ██      ███████  ██████     ██   ",
            ],
        },
        "tips": [
            {"title": "Append /llms.txt to any URL",
             "body": "Every page has a Markdown twin."},
            {"title": "Start at the network index",
             "body": "Enumerate every site from one document.",
             "url": "https://2plot.dev/llms.txt"},
        ],
        "whats_new": [
            {"title": "dash-leaflet2 1.0",
             "body": "Leaflet 2 core, no react-leaflet.",
             "date": "2026-07-20",
             "url": "https://leaflet.2plot.dev"},
        ],
    }
```

Back it with whatever the admin portal writes to — a table, a JSON blob, a
CMS. The package does not care; it only reads.

Serve it with permissive CORS and a short `Cache-Control` (the satellites
already cache for `ttl`, so the origin does not need to).

### Schema

| Field | Type | Notes |
|---|---|---|
| `version` | string/int | Advisory. Not currently interpreted. |
| `network.name` | string | Shown in the banner title bar. ≤120 chars. |
| `network.tagline` | string | One line under the app name. ≤400 chars. |
| `network.url` | string | Must be `http(s)`. Anything else is dropped. |
| `network.llms_txt` | string | The network index — the most important field. |
| `network.sign_in_url` | string | Where accounts come from. Must be `http(s)`. |
| `network.account_label` | string | e.g. "2plot account". ≤120 chars. |
| `network.wordmark` | string[] | Optional ASCII art. ≤12 lines × ≤120 chars. |
| `tips[]` | array | ≤5 rendered. |
| `whats_new[]` | array | ≤5 rendered. Also accepted as `whatsNew`. |
| `*.title` | string | ≤120 chars. |
| `*.body` | string | ≤400 chars. Also accepted as `text`. |
| `*.url` | string | Optional; must be `http(s)`. |
| `*.date` | string | Optional free-form label. ≤40 chars. |

A bare string in `tips` or `whats_new` is accepted as `{"title": ...}`.

### The wordmark lives here, not in the package

ASCII art is served in the payload rather than shipped in the library for two
reasons: an open-source package should not carry one network's branding, and
keeping it remote means changing the wordmark does not require a release of
this library. Omit it and the banner renders `network.name` as styled text,
which looks fine.

---

### Sign-in, and what must never travel here

`network.sign_in_url` and `network.account_label` exist so a satellite that
gates documents but does not own the accounts can say where access comes from —
"Sign in at 2plot.ai" — without every repository hardcoding the hub. They are
network-wide, static, and cacheable, which is exactly why they belong in the
bulletin.

> **The visitor's identity must never travel in this payload.** The bulletin is
> TTL-cached and shared by every viewer of every satellite, so a username in it
> would be served to whoever asked next: a privacy bug wearing a cache. Identity
> is per-request and local — see `configure_viewer_identity()` in
> [`handoff/ACCESS.md`](../handoff/ACCESS.md).

## Treat the payload as untrusted

It arrives over the network, it is rendered into HTML, and the host serving
it is a separate deployment that can be compromised independently of the one
rendering it. So the client:

- caps every string and the total response (64 KB);
- rejects any URL that is not `http://` or `https://`, which drops
  `javascript:` and `data:`;
- flattens newlines out of every field;
- HTML-escapes everything at render time and never interprets a field as
  markup, including the wordmark.

If you point `configure_bulletin` at a host you do not control, you are
trusting it with a text panel on your documentation pages. Point it at your
own hub.

---

## Verifying

```bash
# The endpoint itself.
curl -s https://2plot.dev/api/network/bulletin | python -m json.tool

# A satellite's rendered viewer should contain the tips.
curl -s -H 'Accept: text/html' -A 'Mozilla/5.0 Chrome/120' \
  https://leaflet.2plot.dev/api/llms.txt | grep -c "Tips for getting started"

# And an agent must still get clean Markdown with no banner.
curl -s https://leaflet.2plot.dev/api/llms.txt | head -5
curl -s https://leaflet.2plot.dev/api/llms.txt | grep -c "dv-banner"   # expect 0
```

That last check is the one to automate. If a banner ever shows up in the
Markdown, the negotiation has broken and every agent in the network is paying
for chrome.
