# Country guardrail

Opt-in denial of whole geographies: every listed country receives
**HTTP 451 Unavailable For Legal Reasons on every surface** — app pages,
client-side navigation, assets, the llms.txt family, `sitemap.xml`,
`robots.txt`, root-icon redirects — humans and bots alike. The
application does not exist for that geography.

Status: **shipped in 2.7.0.** Unconfigured is a strict no-op — with no
`configure_geo()` call (or an empty denylist) every response is
byte-identical to a build without the feature, and the suite pins that.

---

## What this is — and is honestly not

**A compliance guardrail and a uniform-response layer. Not a security
boundary.**

The country of a request comes from edge headers, and edge headers are
exactly as trustworthy as the edge in front of your origin. Behind
Cloudflare, `CF-IPCountry` is set by Cloudflare and client-supplied
copies are stripped — the header is reliable. A client that reaches the
origin **directly** (no proxy, or a leaked origin hostname) can spoof or
omit any header. No trusted-proxy validation exists in this package or
in the reference deployments, deliberately: half of one would imply a
promise the header model cannot keep.

If the block matters adversarially, enforce it **at the edge as well**
(a Cloudflare country WAF rule) and treat this package as the layer that
makes the origin's answer uniform across every surface — the thing an
edge rule alone cannot do, because an edge rule doesn't know that
`/_dash-update-component` carries page navigations or that
`/llms-full.txt` is the corpus.

## Deployment precondition — verify per host BEFORE enabling

Geo requires the host to be **edge-proxied** (or an app-side
`resolver=`). Verified on this fleet 2026-08-22: llms.2plot.dev sits
behind Cloudflare and `CF-IPCountry` reaches the origin. A DNS-only
host — no proxy in front — resolves every request "unknown", and under
the default `unknown="allow"` the feature ships **inert**: configured,
tested, and blocking nobody.

The live per-host check is the operator panel's line
*"this request resolved to: `DE` (via cf-ipcountry)"* — see
[PANEL.md](PANEL.md). If it says "unknown" for a request you KNOW came
through your edge, the header is not being forwarded; fix that before
trusting the denylist.

## Usage

```python
from dash_improve_my_llms import configure_geo

configure_geo(deny_countries=["RU", "CN", "IR"])
```

Call it any time before traffic arrives (alongside `configure_seo` is
the natural spot). Full signature:

```python
configure_geo(
    deny_countries=["RU", "CN", "IR"],   # or a zero-arg callable — see below
    unknown="allow",                     # "allow" (default) | "deny"
    resolver=None,                       # (headers) -> "US" | None, optional
    exempt_paths=("/healthz", "/health", "/livez", "/readyz"),
    body=None,                           # override the one-line 451 body
    policy_url="",                       # emitted as Link: rel="blocked-by" (RFC 7725)
)
```

### `deny_countries` — the reloadable seam

A static sequence is validated **at config time** (`ValueError` on
anything that isn't an ISO 3166-1 alpha-2 code). A **zero-argument
callable** is evaluated on **every request** — this is the seam a
writable control board wires a persisted store through:

```python
# lib/policy_store.py — file-backed example (the control-board wiring)
import json, pathlib

_STORE = pathlib.Path("/var/data/policy_overrides.json")

def geo_deny():
    try:
        return json.loads(_STORE.read_text()).get("geo_deny", [])
    except FileNotFoundError:
        return []

# run.py
configure_geo(deny_countries=geo_deny)
```

A store edit takes effect on the **next request in every worker** — no
restart, no redeploy. Callable failures degrade the safe way: a raising
callable or a malformed entry is logged **once** and treated as an empty
denylist (fail-open); it can never take down the request path. The
fleet's writable board is the boilerplate's inherited template control
board (see PANEL.md), and 2.8's bot × country matrix extends this same
seam — nothing here needs to change for it.

### `unknown` — the posture for unresolvable countries

`"allow"` (default) is deliberately fail-open. It is what keeps three
real traffic classes working on a geo-enabled host: platform health
checks (origin-internal, no country header), internal monitoring sweeps,
and direct-to-origin fetches. `"deny"` is for operators whose edge
guarantees the header on every real request — with it, health checks
survive only via `exempt_paths`, so confirm your platform's actual
health path first.

There are **no UA-based exemptions** — a User-Agent is trivially
spoofable, so an "allow our monitoring bot" rule would be a hole, not a
feature. Monitoring rides `unknown="allow"`; under `"deny"`, allowlist
the sweep's origin at your edge instead.

### Resolution order

1. Your `resolver(headers)`, if configured (exceptions → unknown,
   warned once). For apps with their own geo-IP database. **Never do
   network I/O in it** — this runs inside every request.
2. `CF-IPCountry` (Cloudflare — the fleet's edge)
3. `CloudFront-Viewer-Country` (AWS, when the distribution forwards it)
4. `X-Vercel-IP-Country` (Vercel)
5. `Fastly-Geo-Country`, then `X-Country-Code` — conventional names
   operators set from `client.geo.country_code`; Fastly has no
   universal built-in header.

`XX` (Cloudflare unknown), `T1` (Tor), empty, and anything not two
ASCII letters mean **unknown**, not a country.

ip-api-style network lookups are not supported and never will be here:
the fleet's analytics tracker's own lookup is asynchronous *by design*
(a cache miss returns None and resolves in the background) — correct
for analytics, useless and forbidden as a request gate.

## The 451 response

One line of `text/plain`, status 451, `Cache-Control: no-store`, plus
`Link: <policy_url>; rel="blocked-by"` when a policy URL is configured.

`no-store` is load-bearing: the response varies by country and **no
`Vary` token exists for edge geo headers** — a shared cache storing one
country's 451 would serve it to the world. Corollary for allowed
responses: origin `Vary` can't express country either, so if you cache
at a CDN, cache-key on country there (Cloudflare does by default for
its own features) — or accept that a denied country's cache-miss path
is the only one this package can promise.

## Two consequences, accepted and deliberate

- **The discovery floor.** The network's standing guardrail keeps
  `robots.txt`, `sitemap.xml` and the root `llms.txt` public,
  everywhere, always. Geo denial is a **deliberate, owner-decided
  exception** (2026-08-20): compliance, not monetization. Do not "fix"
  this in either direction — do not open the machine surfaces for
  denied countries, and do not cite this exception as precedent for
  gating them anywhere else.
- **robots.txt at 451.** RFC 9309 reads a 4xx robots.txt as "no rules"
  — moot here, because every fetch that policy would govern also
  answers 451.

Also accepted: a browser session established before geo was enabled
451s on its next navigation (the pages-router POST is covered — that is
the point), surfacing Dash's standard error state. Total block means
total.

## Verifying

1. Unset is a no-op: with no `configure_geo()` call, every route's
   bytes are identical with and without a country header
   (`tests/test_adapters.py::TestGeoAcrossAdapters::test_geo_unset_is_byte_identical`).
2. A denied country gets 451 on ALL of: a page, `/llms.txt`,
   `/llms-full.txt`, `/robots.txt`, `/sitemap.xml`, `/favicon.ico`, an
   asset path, and a POST target (`/_dash-update-component`) — on all
   three backends.
3. An allowed country's statuses equal an unconfigured build's.
4. Unknown country: default posture allows; `unknown="deny"` blocks
   but exempt paths still answer.
5. The callable seam: mutate the backing store, next request reflects
   it, no restart. A raising callable fails open with one warning.
6. Live, per host: the panel's resolved-via line shows a real country
   for an edge-proxied request BEFORE the denylist is trusted.
