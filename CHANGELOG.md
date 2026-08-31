# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.9.4] - 2026-08-31 — HEAD on every route, a schema that tells the truth, a priced index

> **2.9.3 was tagged and never published.** Its CD run failed the gate on
> the `py3.9 · dash 4.4.1` leg and the publish job was skipped, so no
> 2.9.3 wheel exists on PyPI. Everything below shipped as 2.9.4, plus the
> fix for what that leg caught — see "the two fixes collided" at the end.

### Fixed — a browser-UA `HEAD /` returned 405 on the FastAPI backend

Seat-confirmed on two live hosts and reproduced in-process across all
three backends: `HEAD /` with a Chrome User-agent returned **405
Allow: GET** on FastAPI, with no discovery `Link` header, while
Googlebot-UA and suppressed-UA HEAD returned 200 — and **Flask and Quart
were clean on all three UA classes**.

The measured cause is neither the lane split nor ASGI:

* Werkzeug (Flask, Quart) adds HEAD to every GET rule automatically, and
  so does Starlette's own `Route`;
* **FastAPI's `APIRoute` does not** — and Dash's FastAPI backend
  registers its index route through it as `methods=["GET"]`.

The User-agent only looked causal. A crawler never reaches that route at
all: this package's middleware answers the crawler lane itself, HEAD
included, while a browser falls through to Dash's GET-only route and
Starlette rejects the method before any of our code runs again. Quart is
ASGI and was never affected.

HEAD is now added to every route that already allows GET, at
registration and again on the request path — both are needed, because
**Dash registers its page catch-all from the ASGI lifespan startup
event**, after this package has finished wiring. The matrix test asserts
HEAD == GET on status *and every header* for three UA classes × two page
routes × three backends; without the fix it reds on exactly the five
FastAPI-plus-browser cases the seat saw on the wire.

### Fixed — /openapi.json described the corpus as JSON

Measured on a live host and reproduced in-process: `/llms.txt`,
`/llms-small.txt`, `/llms-full.txt` and `/{page_path}/llms.txt` all
declared `application/json` with an empty schema while serving
`text/markdown`, and **`/sitemap.xml` declared JSON while serving
`application/xml`** (that one was not in the report). FastAPI infers the
declared media type from `response_class`, whose default is
JSONResponse — so the one surface this package exists to serve was
described to client generators as JSON.

Every route now declares what it actually sends, including the types
reachable by `Accept` negotiation: the llms.txt family declares
`text/markdown`, `text/html` (the viewer) and `text/plain`. A test
compares each declaration against the response the same app returns.

Also fixed, found while measuring: GET and HEAD shared one function per
route, so FastAPI emitted **six `Duplicate Operation ID` warnings** and a
schema whose operationIds collided, which makes a generated client lose
methods silently. Document routes are now registered as a GET operation
plus a HEAD route kept out of the schema — HEAD still answers everywhere,
it is a protocol obligation rather than a distinct operation for a client
author.

### Added — the schema says whose documentation it is

`info` was FastAPI's default `{"title": "FastAPI", "version": "0.1.0"}`.
`LLMSConfig` gains `openapi_title`, `openapi_description` and
`openapi_version`; unset, the title comes from the Dash app's own `title`
and the description says this schema describes the site's
**documentation backend** — the sentence that stops an agent reading a
docs host's schema as the API of whatever library the site documents.
A title or description the host already set is never overwritten: only
the literal FastAPI default is replaced. `info.version` is left alone
unless injected, because the package does not know the host's version and
will not invent one.

### Fixed — robots.txt promised an MCP surface no host runs

The generated file ended with two unconditional lines telling MCP-aware
clients they could fetch per-page docs as resources.
`register_mcp_resources()` has always returned whether that actually
happened, and the answer was always discarded — so every host advertised
it, including the normal case of Dash < 4.3 where `dash.mcp` does not
exist. The claim is now made only when resources really registered.
Truth-or-silence applies to the comments as much as to the directives: an
agent reads both, and a comment it cannot act on costs it a fetch to find
out.

### Added — every entry in /llms.txt carries its size

An agent choosing what to fetch is choosing how much of its context
window to spend, and until now the only way to learn the price was to pay
it. Every page entry and every corpus tier now ends with
`(14.1 KB, ~3.6k tok)`, measured from the document that URL actually
returns — built, not estimated from the prose.

* **The tier menu prices all three**, `/llms-small.txt`, `/llms.txt` and
  `/llms-full.txt`, so the top of the document tells an agent the whole
  menu's cost before it commits to any of it.
* **The index states its own size exactly.** Stating it changes it, so
  the body is built, measured, rebuilt with the measurement and measured
  again, repeating only while the stated number is still wrong. If it has
  not settled within three passes the self-annotation is dropped and the
  rest of the document ships.
* **Truth or silence.** A size that cannot be computed is left unsaid; a
  wrong number would be budgeted against, which is worse than none.
* **Parser-safe.** The annotation is a plain trailing parenthetical, so a
  reader that does not understand it can drop everything from the last
  `(` and parse the line it always parsed. It rides the
  `Machine-readable:` line rather than the page line, because the number
  is the size of the *document*, not of the page.
* The token figure is bytes/4 and is labelled `~`. The tilde is the
  contract: the package never claims an exact count for a tokenizer it
  does not know.

Cost, measured: building the index takes 0.3 ms for 10 pages and 2.2 ms
for 60, against 0.1 ms and 0.4 ms for `/llms-full.txt` on the same apps.
The tests parse the served index and compare every annotation against the
document fetched from that URL over HTTP, on each backend.

### Fixed — the two fixes above collided on older FastAPI

Caught by CI on the one leg that installs an older FastAPI
(`py3.9 · dash 4.4.1`), after a green local matrix. The HEAD pass added
HEAD to *every* GET route — including the in-schema GET routes the
OpenAPI fix had just split out precisely so FastAPI would stop emitting
one operationId for both methods. Every document route became
`['GET', 'HEAD']` again and the six colliding operationIds came back.

Newer FastAPI omits HEAD from the generated schema, so `/openapi.json`
looked correct while the route table was wrong — which is why a green
matrix run said nothing. Two changes make that unrepeatable:

* the HEAD pass now skips any path that **already** has a route
  answering HEAD, so a deliberate GET/HEAD split is never folded back
  together;
* both the pass and its test now walk **nested routers**. Starlette 1.x
  with FastAPI 0.14x does not flatten an included router into
  `app.routes` — this package's own routes sit behind an
  `_IncludedRouter` — while older versions do. Walking both shapes is
  what stops the package's behaviour, and the test that pins it, from
  depending on which FastAPI a host happens to have installed.

The regression test asserts on the route table rather than the schema
and fails on **both** FastAPI generations when the guard is removed;
it also asserts it found all six document routes, because a pin that can
pass by finding nothing is not a pin.

## [2.9.2] - 2026-08-30 — the vendor's class reaches the row

### Fixed — `vendor_class` was computed, held, and then dropped

`classify()` has returned `vendor_class` since 2.8.0 and `build_event`
has had the whole classification dict in hand the entire time. The field
simply was not in `EVENT_FIELDS`, and not in the event `build_event`
returns. Since the documented way to store a row is

```python
{key: event[key] for key in EVENT_FIELDS}
```

every consumer dropped the class at the application boundary, on every
host — so a fleet-wide rollup keyed on it had `null` for every vendor,
and a ledger view showed "—" in the class column for all of them. Found
by the first fork to build that view, against the 2.8.0 wheel, and
confirmed against 2.9.1's.

`vendor_class` is now the sixteenth field, emitted from every emission
point — the middleware's crawler lane and all three adapters — and
present on every event including 403s. It is `None` when no vendor
matched, which is a real answer rather than a gap: a generic `bot` token
gives a `bot_type` without saying whose.

No key was renamed and no key was removed: the field names are the
consumer contract. A consumer that iterates `EVENT_FIELDS` picks the new
column up automatically; one with a hand-written column list adds
`vendor_class` where it wants it.

## [2.9.1] - 2026-08-29 — name the rest of the Google family

Registry only. 2.9.0's ledger had its first real day on a live host and
the null-vendor row turned out to contain real, verifiable Google
traffic: three of Google's own common crawlers carry no `googlebot`
substring, so they never matched a vendor at all.

### Added — five Google crawlers the registry could not name

| Entry | robots token(s) | was, before 2.9.1 |
|---|---|---|
| `googleother` | `GoogleOther`, `GoogleOther-Image`, `GoogleOther-Video` | `bot_type=unknown`, no vendor |
| `google-inspectiontool` | `Google-InspectionTool` | `bot_type=unknown`, no vendor |
| `storebot-google` | `Storebot-Google` | `traditional`, no vendor — it matched the generic `bot` token inside its own `+http://www.google.com/bot.html` URL |
| `adsbot-google` | `AdsBot-Google` | `traditional`, no vendor |
| `google-safety` | *(none — see below)* | `bot_type=unknown`, no vendor |

All five now verify against Google's published ranges, so a real one is
`verified` and an impostor is `unverified`, the same as Googlebot.

**GoogleOther is classified `traditional`, not `training`** — stated
deliberately, because Google describes it as serving "one-off internal
R&D crawls". Three reasons: `Google-Extended` is the token that governs
training use and is already in the registry as `training`; Google groups
GoogleOther with the common crawlers and says it does not affect Search
ranking; and classifying it `training` would silently start 403ing it on
every host that blocks AI training — from a patch release. A host that
reads Google's "R&D" as AI use has the exact control it needs,
`vendor_policy={"googleother": "block"}`, which works only because the
vendor now exists.

**`Google-Safety` is deliberately never named in robots.txt.** Google
documents that it ignores robots.txt entirely; publishing a directive the
vendor openly disregards is a promise the site cannot keep. That is the
`anthropic-legacy` rule, reached for a different reason. **`AdsBot-Google`
is the mirror case**: Google documents that AdsBot ignores the global
`User-agent: *` rule, so naming it explicitly is the only way a site can
address it at all.

### Added — shared range snapshots (`Vendor.ranges_key`)

Google publishes ONE ranges document for its whole common-crawler family
and one for its special-case crawlers, so `_ranges/` is now keyed by
snapshot rather than by vendor: `googlebot.json` is read by `googlebot`,
`googleother`, `google-inspectiontool` and `storebot-google`, and the new
`google-special.json` (135 v4 + 135 v6, from `special-crawlers.json`) by
`adsbot-google` and `google-safety`. The alternative was shipping the same
315 CIDRs four more times and re-fetching them four more times per
release. The parse cache is keyed on the snapshot too, so a family is
parsed once for all its members. A vendor without `ranges_key` still reads
`<its own key>.json`; nothing else in `_ranges/` moved.

### robots.txt — what changes, exactly

Measured against the 2.9.0 renderer across nine configurations: **byte-identical
on seven**, including every default, `block_ai_training=False`,
`allow_ai_search=False`, `default_unknown_ai=...`, `crawl_delay`,
`disallowed_paths` and any `vendor_policy` naming an older vendor. Two
move, both deliberately:

1. `vendor_policy` naming one of the five new keys — which is the point of
   adding them. At 2.9.0 such an entry was dropped with a warning
   (`unknown vendor 'googleother'`).
2. **`allow_traditional=False`** — a host that blocks every traditional
   crawler now publishes `Disallow` groups for GoogleOther (×3 tokens),
   Google-InspectionTool, Storebot-Google and AdsBot-Google, **and the
   middleware 403s them**, where 2.9.0 served them. This is the one
   behaviour change in the release. It is the correct rendering of a policy
   such a host already chose, and the alternative — classifying them but
   never naming them — is exactly the enforced-but-unpublished defect
   (soak finding #2) that 2.8 fixed. If you run Google Ads against a host
   that sets `allow_traditional=False`, add
   `vendor_policy={"adsbot-google": "allow"}`.

## [2.9.0] - 2026-08-29 — the posture on every row, `twitter:url`, monitors get a name

2.8.0 started recording the read. Its first consumer put a ledger behind
it, rolled up by `(vendor, verified, policy)`, and found the third key
empty on every row of a default host. This release fills it in, and fixes
the two smaller things that day of production traffic surfaced.

**Why 2.9.0 and not 2.8.1.** `get_bot_type()` has answered with three
strings since 1.x and now answers with four; a headless browser changes
lanes; and `default_unknown_ai` widens to cover clients it did not cover
before. Any one of those is more than a patch.

### Fixed — `policy` was `None` on every event of a default host

Measured on the 2.8.0 wheel, 2026-08-29: `/` on a host with no explicit
`vendor_policy` emitted `policy=None` for Googlebot, GPTBot and ClaudeBot
alike. The field became a string only for a registry vendor on a host
that carried a `RobotsConfig`, or for a generic-pattern bot on a host
that had set `default_unknown_ai`. Everything else got `None` — and the
three adapters, which serve `/llms.txt`, `/llms-small.txt`,
`/llms-full.txt`, `/robots.txt`, `/sitemap.xml` and the per-page
documents, passed no `policy` at all. A consumer rolling up by posture
had nothing to group on.

The invariant now: **every emitted event carries `policy` ∈ {`allow`,
`meter`, `block`}. Never `None`.** One resolver, `resolve_policy`, and
the middleware and all three adapters ask it:

- a registry vendor → the same `effective_policies` fold robots.txt
  renders from;
- no vendor → `default_unknown_ai`, with CLI tools (curl, wget,
  python-requests) always `allow` — they are the paste-into-chat lane;
- no `RobotsConfig` on the app → `allow`; the document was served, and
  `None` never described that;
- a 403 from the block branch → `block`, by construction.

That the *same* function decides the block and names the posture is the
point, not an implementation detail: a ledger row that reports something
other than what the middleware did is the defect this fixes, and two
copies of the rule is how it comes back.

### Changed — `default_unknown_ai` now covers the unidentified, not just the generic

2.8 moved `httpx`, `Go-http-client`, `node-fetch` and an absent
User-agent onto the crawler lane. This knob kept covering only the
GENERIC patterns (`bot`/`crawler`/`spider`/`scraper`), so the one class
of reader a host cannot enumerate was also the one it could not govern.
It now covers both.

**If you set `default_unknown_ai="block"`**, a request with an
unrecognised or absent User-agent that 2.8.0 served now receives 403,
exactly as a `some-crawler/1.0` already did. The default is `allow` and
is unchanged; hosts that never set the knob see no difference. CLI tools
remain exempt.

### Added — `twitter:url` on the crawler document

`og:url` was emitted unconditionally while every `twitter:*` tag lived
inside `_social_tags()`, which returns nothing unless a social image is
declared. So a host with no card image published a document whose URL X
could not read. The tag is now emitted beside `og:url`, from the same
`base_url` — so it follows the forwarded scheme wherever `og:url` does —
with `name=`, not `property=`, which is the difference between X reading
it and X ignoring it silently. The card set (`twitter:card`, `:title`,
`:image`, …) stays opt-in behind `social_image`; only the URL is
unconditional. This unblocks the boilerplate template's verbatim
`tests/test_proxy_scheme.py`, which asserted on the tag and reddened on
every fork because a default-UA request lands on the crawler lane where
the tag did not exist.

### Added — `monitor`, the fourth bot class

Uptime probes and headless automation were `unknown` with no vendor
(`pingdom`, `better-uptime`, `headlesschrome`, `phantomjs`) or hidden
inside `traditional` (`uptimerobot`, which the generic `bot` token caught
and said nothing more about). Either way the null-vendor row in a host's
ledger was part monitoring traffic and part everything else, and
unreadable. Registry entries: `pingdom`, `uptimerobot`, `betteruptime`,
`statuscake`, `site24x7`, and `headless` (HeadlessChrome, PhantomJS,
Puppeteer, Playwright); plus the unnamed probes — Uptime Kuma and a dozen
self-hosted checkers — which classify `monitor` with `vendor_key=None`
rather than being misattributed to a vendor they are not.

`render-health` was **not** added: Render's health probe publishes no
documented User-agent token, and a registry entry that matches nothing is
worse than an honest gap.

Monitors are **always `allow`** by default, under every coarse flag —
`allow_traditional=False` is a statement about search engines, and a host
that makes it has not asked to start 403ing its own health checks at
3 a.m. They carry **empty `robots_tokens`**, the same rule
`anthropic-legacy` carries for a different reason: robots.txt is a
crawling policy, and telling a health check what it may crawl is a
category error. Verified byte-for-byte: `/robots.txt` is identical to
2.8.0's across eight configurations.

**Two contract changes ride with it.** `get_bot_type()` can now return
`"monitor"` — a consumer switching exhaustively on the other four needs a
branch. And a headless browser now takes the **crawler** lane: its UA
claims a browser, so through 2.8.x it was handed the JavaScript shell,
and vendor matching runs before the browser check. Screenshot services,
synthetic checks and Playwright scripts against a page route therefore
receive the crawler document. That is the right document for automation
and the wrong one for a service that is deliberately rendering your app;
such a service should send its own User-agent.

## [2.8.0] - 2026-08-29 — one classifier, one lane, one read event

The package has always known who was asking, what policy applied and
which document went out. It just never said so, and on two of the paths
it decided, it decided wrongly. 2.8 fixes the lane and starts recording
the read.

### Changed — a permitted AI crawler now gets the crawler document

**If your site allows AI crawlers, they were being served the wrong
document, and nothing reported it.**

Through 2.7.x the crawler branch required an *explicit* `vendor_policy`
entry before it would serve a training-class vendor. A vendor merely
not-blocked by the coarse flags fell through to the application. So on a
host whose posture was *allow*, measured on the wire: `ClaudeBot/1.0` and
`GPTBot/1.2` received the **204,611-byte JavaScript shell**, while
`Googlebot` and bare `curl` received the **12,515-byte crawler
document**. Both at 200, both with a correct `Link` header — which is why
it survived two minor versions. The hosts that had deliberately opted in
to AI crawlers were serving them the worst document on the site.

The lane now follows the registry: a request whose *effective* policy is
`allow` or `meter` — explicit or defaulted — is served the crawler
document. `block` keeps its 403 semantics unchanged, including the
documentation-route carve-out.

Retired deliberately: byte-identity of the served document between a
flag-only configuration and an explicit `vendor_policy`. That property
was only ever preserved by serving the wrong document to one of them.

### Changed — an unidentified client is treated as a machine, not a person

`is_any_bot()` returning false was never evidence of a human. `httpx`,
`aiohttp`, `node-fetch`, `Go-http-client` and an **absent** User-agent
all landed in the browser lane and were handed a JavaScript shell
containing none of the prose they came for. For a package whose thesis is
machine readers, the fallback was backwards.

Browser identification is now positive: a User-agent carrying `Mozilla/`
**and** an engine token (`AppleWebKit`, `Gecko/`, `Trident`, `Edg/`,
`Chrome/`, `Safari/`, `Firefox/`) is a browser. Everything else takes the
crawler lane with `vendor_key=None`, `bot_type="unknown"`. Vendor
matching runs first, so ClaudeBot — whose real header opens
`Mozilla/5.0 AppleWebKit/537.36 ...` — stays on the crawler lane.

Dash's own endpoints are never short-circuited regardless of User-agent;
`/_dash-update-component`, `/_dash-layout`, `/_dash-dependencies`,
`/_dash-component-suites/*`, `/_reload-hash`, `/_favicon.ico` and
`/assets/*` are now named explicitly rather than left to a prefix match.

*Sharp edge worth knowing:* a client sending `Mozilla/5.0` with no engine
token is now read as a machine. No mainstream browser does this, but a
synthetic or heavily-stripped User-agent will get static HTML instead of
the app shell.

### Added — `Vary: User-Agent` on every response that varies by it

The same URL answers a browser and a crawler with different bytes, and
through 2.7.x the package told no cache so — `_doc_headers()` emitted
`Vary: Accept` alone and the page routes emitted nothing. It went
unnoticed only because the edge in front of these hosts marks document
responses `DYNAMIC`; a shared cache that did not would hand a crawler the
document built for a browser, or the reverse. Now emitted on the document
routes, the crawler HTML, and the prerendered page responses, on all
three adapters, merging with rather than clobbering existing tokens.

### Added — the read event: `on_document_read`

One structured event per document the package serves, delivered to a
callback the application registers. The package does **no I/O** with it.

```python
from dash_improve_my_llms import on_document_read

@on_document_read
def record(event: dict) -> None:
    db.insert(event)
```

The event carries `ts`, `host`, `path`, `method`, `tier`, `lane`,
`bot_type`, `vendor_key`, `verified`, `policy`, `verdict`, `status`,
`bytes`, `ua` and `client_ip`. Every key is always present; `None` means
"not known here". Emitted from every place a document leaves the package
— the middleware's 403/429/404/gate/offer/crawler-HTML returns, and each
adapter's `/llms.txt`, tier, `/robots.txt` and `/sitemap.xml` handlers —
through one shared `emit_read()`, so the shape cannot drift between
backends.

A callback that raises is caught and warned about once; the response is
unaffected. Same fail-open rule as the rate limiter, for the same reason:
a bookkeeping failure is not a reason to stop serving documents. With no
callback registered — the default — emission costs one truth-test.

### Added — verified crawler identity

`get_bot_vendor()` matches a substring, so "who is asking" has always
been a claim the client makes about itself. For the eleven registry
vendors whose operators publish crawler IP ranges (Google, OpenAI,
Microsoft, Apple, Perplexity, DuckDuckGo, Common Crawl), the client
address is now checked against the published list and the event reports
`verified`, `unverified`, or `n/a`.

**It is never a gate.** An unverified client is served exactly the
document a verified one is served; it gets a row that says so. Making it
a block would put a third-party JSON file's uptime in the request path.

Ranges ship in the wheel (`_ranges/*.json`) and are refreshed by
`scripts/refresh_ip_ranges.py` at release time. Nothing is fetched on the
request path; a runtime refresh is opt-in via
`configure_identity(refresh=True)` and falls back to the shipped
snapshot. The package gains no new dependency. Anthropic publishes no
crawler ranges, so ClaudeBot reports `n/a` rather than a guess.

### Added — `classify()`, the one classification fold

```python
from dash_improve_my_llms import classify

classify(user_agent, client_ip=None)
# {'bot_type', 'vendor_key', 'vendor_class', 'verified', 'lane'}
```

*The* classification entry point, so an application can delete its own
User-agent lists. Hand-written lists drift — they keep retired tokens
alive and miss new vendors — and that drift is how bot traffic gets
mis-attributed downstream. The existing predicates still work and
delegate here.

### Added — the accounting line in the corpus policy block

`build_policy_block` now states, in one line, that reads are recorded and
where the policy lives, pulling the URL from the network bulletin or the
registered hub — never a hard-coded host. Emitted only when a callback is
actually registered: this section's standing rule is that every input
degrades and the text stays truthful on every host, and a host recording
nothing must not claim otherwise.

### Notes

- `handle_bot_request()` gained a keyword-only `method` parameter
  (default `"GET"`), used for the event. Existing callers are unaffected.
- `Vendor` gained an `ip_ranges_url` attribute; readers using `getattr`
  with a default are unaffected.
- The geo guardrail still runs before classification and emits no event —
  a 451 is a jurisdictional refusal, not a document read.

## [2.7.2] - 2026-08-27 — HEAD on the ASGI lane

### Fixed — `HEAD` returned 405 on FastAPI-backed apps

Through 2.7.1 the FastAPI adapter registered every crawler-facing route
with `@router.get(...)`. FastAPI's `APIRoute` takes that literally, and
Starlette answers an undeclared method with **405 Method Not Allowed** —
while Werkzeug (Flask, and Quart by descent) derives `HEAD` from every
`GET` automatically. The same package version therefore answered
`HEAD /llms.txt` with 200 on a Flask host and 405 on an ASGI one.

**Operators of FastAPI-backed apps: this was the package, not your
configuration.** Uptime monitors, link checkers and crawlers that
preflight with `HEAD` before fetching have been receiving 405 from
`/llms.txt`, the per-page `/<page>/llms.txt` twins, `/llms-small.txt`,
`/llms-full.txt`, `/robots.txt`, `/sitemap.xml` and the operator panel
since those routes existed. `GET` was never affected, so a monitor
checking with `GET` saw nothing wrong. Only the root icon routes were
correct, because they alone declared their methods explicitly.

Every one of those routes now declares `GET` and `HEAD`. The methods are
stated once, in `handlers.DOC_ROUTE_METHODS`, and all three adapters
register from it — Flask and Quart included, where the behaviour was
previously inherited from Werkzeug rather than chosen. Their responses do
not change; the declaration does, so the three adapters now read the same
and the guarantee is deliberate.

Response bodies are unaffected: a `HEAD` returns the status and headers
its `GET` would, and the body is suppressed by the serving layer as
before (Werkzeug on WSGI; uvicorn and hypercorn both suppress a `HEAD`
body on ASGI).

### Added — HEAD parity is now covered on every backend

`TestHeadParity` in `tests/test_adapters.py` sweeps every registered
route on all three adapters and asserts `HEAD` matches `GET` on status
and content-type, and is never 405. The test was checked for
non-vacuity: with the FastAPI declaration reverted, its FastAPI leg goes
red and the Flask and Quart legs stay green — the asymmetry that let this
reach 2.7.1 without a failing test.

## [2.7.1] - 2026-08-23 — the standards fast-follow

Three additive features tracking llms.txt v2's August 2026 discovery
update, all default-on, none changing existing bytes' meaning — shipped
quick so the fleet's floor round happens once (to >=2.7.1).

### Added — discovery relations on every page

`rel="alternate" type="text/markdown"` (the page's twin — emitted since
2.x) is joined by `rel="describedby"` pointing at the covering
`/llms.txt`, in the HTML head of BOTH document lanes (the
prerender/browser path and the static crawler document), and both
relations now ALSO ride an HTTP `Link` header on page responses — an
agent that reads only headers still finds the machine surface.

### Added — the text/plain compatibility ramp

An `Accept` header naming `text/plain` (and not markdown) gets the same
bytes with `Content-Type: text/plain` on every llms surface (root,
per-page twins, both tiers) — a mainstream agent retrieval stack was
measured rejecting `text/markdown` outright. `*/*` keeps the historical
markdown type; `Vary: Accept` already travels on these responses.

### Added — the representation source digest

`sha256:<hex>` of the markdown source a lane serves, exposed as
`<meta name="llms-source-digest">` on both HTML lanes and an
`X-Llms-Source-Digest` header on the markdown twin — representation
parity becomes provable rather than plausible: deployment batteries can
assert the page, its twin, and the crawler document were generated from
the same source. The digest is of the SERVED source, so parity holds
for every access verdict (a gated page's three lanes all carry the gate
document's digest, and the withheld prose's hash never leaks). The root
`/llms.txt` is a composite built from many sources and carries no
digest — the documented exception.

## [2.7.0] - 2026-08-22 — "the agent toll gate"

The release the 2026-08-13 agent-exchange design specified (W1–W6 + P6),
plus the owner's 2026-08-20 scope additions (the geo guardrail G0/G1 and
the read-only operator panel P1) and the 2026-08-22 fleet addendum's
idempotency hardening. Standing rule kept throughout: every new knob
unset ⇒ output byte-identical to 2.6.1 — except the deliberate,
documented contract changes listed under each item.

### Added — one vendor registry (W1)

`vendors.py`: every bot identity defined once; `get_bot_vendor(ua)` is
the new identity primitive. bot_detection classifies from it and
robots_generator renders from it, so agreement holds by construction
(the registry-agreement test makes drift unrepresentable). Deliberate
contract changes: ClaudeBot classifies **training** (robots.txt was the
published promise — P1); seven previously-unenumerated AI crawlers
(Amazonbot, Applebot-Extended, meta-externalagent, AI2Bot, Diffbot,
Timpibot, ImagesiftBot) stop falling through to `traditional` (P2);
Claude-User / Claude-SearchBot / Perplexity-User gain tokens, class
search (P3); `allow_traditional=False` emits real Disallow groups (P4);
`disallowed_paths` and `Crawl-delay` sit inside the `User-agent: *`
group (P5, RFC 9309 strict parsers).

### Added — per-vendor policy (W2)

`RobotsConfig(vendor_policy={...} | callable, default_unknown_ai=...)`.
One fold (`vendors.effective_policies`) drives robots.txt AND the
middleware. `meter` renders Allow and behaves as allow until the limiter
consumes it. Callable maps are read per request — the reloadable seam a
writable control board wires a persisted store through.

### Added — the conduct contract in the documents (W3)

`build_policy_block`: an "## Access policy" section in the index, the
small tier's tail, and the full corpus's header — terms, `?key=`
identity, the rate rule ("prefer ONE /llms-full.txt fetch"), one
coordination point, and a crawler-policy summary rendered from the same
fold robots.txt renders from. Identity-free by construction.

### Added — the rate contract, enforced (W4)

`LLMSConfig(rate_limit_per_minute=N)`: bot traffic on the corpus routes
gets 429 + Retry-After over the ceiling, keyed on the edge-header client
IP. Policy routes and humans are never limited. **Fails open on any
error** — a limiter bug must never black-hole the corpus. Per-process
(N workers ⇒ N× ceiling), documented. `user_agent=` threaded into all
corpus builders for W5's consumers.

### Added — the 402 seam, wired and OFF (W5)

`access.PRICED` behind `LLMSConfig(metering=False)`: off (default), a
"priced" verdict degrades to gated — a billing bug can neither publish
nor charge. On: offer document at 402 (`configure_access(offer_doc=,
payment_headers=)`) across every surface, priced pages stay listed, the
crawler column serves the offer at 200 + noindex (anti-cloaking), and
any payment-path exception degrades to gated. The package never computes
a price and never holds a pay-to address.

### Added — bulletin policy keys (W6)

`network.crawler_policy` / `price_default` / `prices[]` / `rate_limit`,
hard element caps. The hub may only TIGHTEN (most-restrictive overlay in
the policy fold; min() on the ceiling). **A bulletin carrying anything
shaped like a pay-to address is refused whole** — a fetched address is a
payment-redirection target.

### Added — the geo guardrail (G0/G1)

`configure_geo(deny_countries=[...] | callable, unknown="allow", ...)`:
opt-in **451 on every surface** for denied countries, humans and bots —
a deliberate, owner-decided exception to the discovery-floor guardrail
(compliance, not monetization). Header-based resolution only
(CF-IPCountry first), no network lookups in the request path, exact-match
health-path exemptions, fail-open unknown posture. Requires an
edge-proxied host — see docs/GEO.md for the trust model and the per-host
check. G0 threads normalized headers through the enforcement seam once,
serving both geo and the limiter.

### Added — the operator policy panel (P1)

`LLMSConfig(panel=True, panel_token=...)`: a read-only, token-gated,
404-silent page (default `/llms-policy`) showing live effective policy —
the vendor table renders from the same fold robots.txt renders from and
cannot drift from it. Unset token ⇒ 404 unconditionally. Absent from
robots/sitemap/index by design. The writable layer above it is the
site-side control board wired through the callable seams — docs/PANEL.md.

### Fixed — the pre-tag soak batch (llms-2plot-dev soak, 2026-08-23)

Six fixes from the boilerplate-fork soak (BUGS-2.7.0.md), landed before
the tag:

- **A `deny_countries` callable returning an unhashable entry 500'd
  every request on every surface** — `tuple()` wraps a nested object
  happily and the hash into the memo cache raised OUTSIDE the try,
  escaping the seam. The whole call-through-cache path now sits inside
  the containment; any such shape behaves as an empty denylist with one
  warning, honouring GEO.md's "it can never take down the request
  path". Load-bearing for 2.8's matrix, which arrives through this seam.
- **A per-vendor block on a traditional crawler was enforced but never
  published**: with the default `allow_traditional=True`,
  `vendor_policy={"googlebot": "block"}` 403'd Googlebot while
  robots.txt said Allow via `*` — the crawl-error/cloaking hazard. The
  allow-branch now consults the same fold the else-branch always did.
  The upstream agreement test now resolves every vendor's robots verdict
  THROUGH the `*` fallback (a vendor with no group is not unregulated,
  it is governed by `*`) so this class of gap cannot return unseen.
- **GEO.md corrections**: a malformed entry is SKIPPED, not
  list-voiding (the code's behaviour was the better one — the doc
  moved); and a RAISING resolver falls back to header resolution while
  a garbage-RETURNING resolver does not — two behaviours that shared
  one sentence.
- **Prerender H1 dedup** (SEO-audit, every host): the injected header's
  `<h1>` duplicated the doc body's own opening markdown H1. When the
  prose opens with an h1 the header contributes only the description;
  a page without one keeps the header h1 — exactly one h1 either way.
- **Home footer dedup**: the per-page llms link is skipped when it IS
  the root link ("… /llms.txt · /llms.txt …" is gone).
- **Crawler-document H1 dedup** (re-soak finding #5): the same guard,
  applied to the OTHER of the package's two document lanes — the static
  crawler document Googlebot/ClaudeBot/GPTBot actually receive still
  emitted `<header><h1>` before prose opening with its own h1 (11/11
  pages, both backends; present since ≤2.6.1). Exactly one h1 on both
  lanes now, with mirror pins on the crawler side and an end-to-end
  crawler-UA fetch pin — a prerender-side test cannot see this lane.

### Fixed — the prerender idempotency probe (fleet addendum 2026-08-22)

The already-injected check was a bare substring probe on the marker
name; the marker appearing in an index.html COMMENT silently disabled
the entire prerender on two production hosts. The probe now matches the
injected node's opening tag.

## [2.6.1] - 2026-08-22

### Fixed — the universal prerender becomes VISIBLE to non-JS consumers

An outside SEO audit read six production hosts through a
visibility-respecting text extraction and found only "Loading..." on
every URL. The audit's mechanism claims were wrong — the prerender was
firing everywhere, not UA-gated, not off — but the effective finding was
real: the injected block shipped with a literal `hidden` attribute, so
every consumer that respects visibility (html-to-text extractors, audit
tooling, plausibly crawler content-weighting) saw only the Dash loader.
The prose was present and invisible, and a young host with no crawl
budget read as N identical thin pages.

The div now ships visible, and a synchronous inline script immediately
after it sets `hidden` for JS browsers:

- a non-JS consumer never executes the script and reads fully visible
  prose — the entire fix;
- a JS browser executes it during parse, before first paint of
  subsequent content, so the pre-mount flash the old attribute existed
  to prevent stays prevented;
- React's mount wipes the whole block exactly as before (both nodes sit
  inside `#react-entry-point` and both carry `data-dimll-prerender="1"`
  so node-stripping logic keeps matching the pair).

Deliberately NOT a `<noscript>` (second-class to search engines, classic
spam vector) and NOT a stylesheet class (extractors that ignore
stylesheets are not guaranteed; the attribute was this problem's own
proof of what these tools respect).

GATED pages behave the same way: the gate document — already the exact
document the machine lane serves — is now visible to non-JS consumers
too. Correct and deliberate.

**CSP note:** the inline hide-script requires `unsafe-inline` or a nonce
under a strict `script-src` CSP. No 2plot host ships a restrictive CSP
today; a host that adds one must account for this script.

Fleet propagation: the fleet floor is `>=2.6.0` and images resolve the
newest release at build time — each host picks this up on its next
deploy with no requirements edit anywhere.

## [2.6.0] - 2026-08-20

Numbering note: the agent-exchange kickoff had earmarked 2.6.0 for the
toll gate; that work renumbers to 2.7.0 (decided 2026-08-20).

### Added — the favicon finds itself

Measured across the 25 repos depending on this package in August 2026: four
called `configure_seo()`, twenty-one did not — and **all twenty-one had a
perfectly good favicon in `assets/`**. The package is why it went missing (it
serves crawlers a generated head instead of the app's own), and an opt-in fix
to a silent problem demonstrably does not reach a fleet. So the package now
carries the identity forward itself:

- `discover_icons(app)` reads the app's own assets folder: `favicon/`,
  `favicons/`, `favicon_io/`, `icons/`, `img/`, then the root — first
  directory with icons wins, so a curated set beats a stale loose copy (the
  duplicate-`rel="icon"` defect). Glob matching finds real-world names like
  `favicon_areachart.ico` that an exact-name list missed. `rel`/`sizes`/
  `type` inferred from the filename; hrefs via `app.get_asset_url()` so
  path prefixes are honoured; `.ico` first, biggest square next.
- `autoconfigure_icons(app)` runs inside `add_llms_routes` and adopts the
  discovered set **only when no icons were declared**. Explicit
  `configure_seo(icons=[...])` always wins; explicit `icons=[]` opts out.
  It **warns** when it finds nothing — silence is what let a blank identity
  run for months across a whole network.
- The `icon-` glob is digit-anchored (`icon-[0-9]*.png`): `assets/icons/`
  holds UI sprites too, and `icon-arrow.png` must never become the site's
  search-result icon. `favicon*.svg` is matched — two real fleet apps ship
  ONLY an SVG favicon, and Google parses them.
- A discovered set survives a later `configure_seo()` call that configures
  unrelated fields; only an explicit `icons=` argument replaces it.
  (Explicitly declared config keeps the pre-2.6 wholesale-assignment
  semantics.)

### Added — JSON-LD `publisher.logo`

Google's Organization guidance wants a logo, and a publisher without one
forfeits the branded result. New `configure_seo(logo=...)`, falling back to
the largest declared/discovered raster icon ≥112×112 (Google's floor; `.ico`
excluded — not a supported logo format). Emitted absolute or not at all.

### Fixed — the llms.txt viewer banner stops repeating the brand

On every satellite's root `/llms.txt` the page name IS the site name (the
network rule puts the brand in the home page's registered name), so the
banner opened with the same string twice — once as the brand chip, once as
the page line. The page line is now suppressed when it would repeat the
chip; inner pages keep theirs.

### Fixed — the sitemap stops lying about `lastmod`

Every `<lastmod>` was invented as "today", every day, for every URL. Google
and Bing both state they use `lastmod` only when it is consistently truthful;
a sitemap of daily-changing lies is discarded wholesale, taking the honest
entries with it. Now: `register_page_metadata(lastmod="YYYY-MM-DD")` is
emitted verbatim, and an unset one **omits the tag** — truth or silence.
`SitemapEntry(lastmod=None)` likewise no longer stamps the current date.

## [2.5.1] - 2026-08-14

### Fixed — the prerender stops fighting the application's own head

Found by running the 2.5.0 Tier-B standard against the boilerplate: the
universal prerender — the browser-facing path — still had the exact defect
2.5.0 fixed for the crawler document, plus a new way to make it worse. Dash
Pages resolves per-page titles server-side, so the boilerplate served
`Dash Documentation Boilerplate | Getting Started` — and the prerender then
**rewrote it to the bare page name** and injected a second, conflicting
`og:title` beside the application's own.

- The prerender `<title>` and `og:title` now resolve through the same
  `resolve_page_title` as the crawler document: explicit `title` first, else
  `page · site`. A name that already carries a title separator
  (`pkg | Page`) is a composed title and is never suffixed — the author did
  the branding, and `pkg | Page · pkg` doubles it.
- The `<title>` is only rewritten when that is an upgrade. An explicit
  metadata title is authoritative; otherwise a document title that already
  carries the page's name is the application's own per-page title and is
  kept verbatim. The rewrite exists for Dash's static-template case, where
  every URL ships the same app-level title.
- Every injected head tag (description, canonical, `og:*`) is skipped when
  the document already declares its counterpart. Duplicate canonicals are
  ignored by crawlers, and conflicting `og:title`s make the scraper pick one
  arbitrarily — a second copy was never reinforcement.
- `image_url` is accepted as the `og_image` alias on this path too, matching
  2.5.0's crawler document.

## [2.5.0] - 2026-08-14

### Fixed — the crawler sees what the browser sees

This package serves crawlers a generated document instead of the application's
own HTML. That document carried every *content* signal — title, description,
canonical, JSON-LD — and none of the *identity* signals: no `<link rel="icon">`,
no `og:image`, no `twitter:*`. Measured across a live 18-host network: browsers
received four to seven icon links, **Googlebot received zero on every host**,
and search results showed the generic globe. The two comparison sites that
served crawlers the byte-identical document a browser gets showed their real
marks. The rule this release enforces:

> Content may differ between the crawler document and the browser document.
> Identity may not.

- **`configure_seo()`** declares site-level identity once — `icons`,
  `social_image` (+ alt/width/height), `twitter_site`, `twitter_card`,
  `publisher`, `same_as`. It follows `configure_access` / `describe_network`:
  module-level, read at render time, and **entirely opt-in — an application
  that never calls it emits no icon, image or card tags at all**, so upgrading
  cannot invent an identity for a site that never declared one.
- **`og_image` on `register_page_metadata` finally does something.** It has
  been advertised in the docstring since 2.0 as "passed through to
  html_generator" and was read by nothing. A per-page card now overrides the
  site default; `image_url` is accepted as an alias so a page can pass the
  same value it already gives `dash.register_page`.
- **The crawler `<title>` keeps the site's name.** It was the bare page name,
  so a docs page shipped as `pkg | Attribution` to a browser and `Attribution`
  to Google — a result indistinguishable from every other page on the web with
  that heading. Inner pages are now `<page> · <site>`; the home page is
  untouched, a `title` field overrides, a name that already carries the site is
  left alone, and the suffix uses only the part of the site title before its
  tagline separator so it does not spend the ~60 characters Google shows on a
  pitch. The `<h1>` is still the page's own name.
- **`/favicon.ico` and the apple-touch paths** are answered by the package,
  redirecting to a declared icon. Google falls back to `<origin>/favicon.ico`
  when the page it crawled declares no icon, and Dash's page catch-all was
  answering all three with the app shell — 200 `text/html` where an image
  belongs, a poisoned fallback rather than a missing one. Inert unless `icons`
  is declared — with no configuration the paths answer 404, which a crawler
  reads correctly as "no icon" where the app shell read as a broken one.
  `configure_seo(root_icons=False)` opts out, and a route the application
  registered for one of these paths before `improve()` keeps precedence: the
  package only claims paths nobody else has.
- **Structured data grew a graph.** `publisher` and `sameAs` from
  `configure_seo` (`sameAs` is how a family of domains tells a search engine it
  is one entity rather than N unrelated sites), the page's card as `image`, and
  a `BreadcrumbList` on every non-home page. `schema_type` already worked and
  remains the way a docs page declares `TechArticle` or a package home declares
  `SoftwareApplication`.
- `og:site_name` is now emitted.

### Changed — documentation routes obey bot policy

`handle_bot_request` exempted every documentation route *before* policy ran, so
`block_ai_training=True` protected an application's pages while leaving
`/llms.txt`, `/llms-small.txt` and `/llms-full.txt` open — the one surface built
to be read by machines, and the only one worth metering, was the only one no
configuration could reach.

Documentation routes are now evaluated like anything else, and
**the default is unchanged**: `RobotsConfig(block_ai_training_docs=False)` keeps
serving them, because the documents exist to get the packages used. Set it True
when the corpus itself is what you are protecting. Only training-class bots are
affected — search bots, browsers and agents holding a key read the corpus
exactly as before. This is also the seam a future release's per-vendor `meter`
policy slots into.

The gate covers the corpus only. `/robots.txt` and `/sitemap.xml` are never
blocked, even for a blocked bot: robots.txt is where the block is announced,
and RFC 9309 treats an unreadable (4xx) robots.txt as no-rules-at-all — a bot
that cannot read `Disallow: /` concludes the opposite and keeps crawling.

## [2.4.0] - 2026-08-13

### Added — tiered corpus documents: /llms-small.txt and /llms-full.txt

The Svelte docs popularised serving llms.txt at more than one size, because
one document cannot be both small enough to sit whole in a tight context
window and complete enough to feed an offline ingestion job. This release
adopts the same tiering; the root `/llms.txt` stays the medium index and
now advertises both sizes above its page listing (a tier the access check
denies is not advertised, same rule as a denied page).

- `/llms-small.txt` — a compact briefing: the site's identity, the home
  page's first paragraph, one document link per page, and pointers to the
  larger documents. An application can replace the synthesized version
  wholesale with `register_page_metadata("/llms-small.txt", llms_doc=…)`.
- `/llms-full.txt` — every page's prose in one document, in path order,
  each section preceded by a source comment naming the page and its own
  `llms.txt` URL so any passage stays traceable. Denied pages are omitted;
  gated pages contribute their gate document, never the prose the per-page
  route withholds; a page with no prose gets a one-line pointer instead of
  a stub. A byte budget (`LLMSConfig(llms_full_max_bytes=…)`, default
  4 MB) stops the corpus page-by-page — everything past the cap is listed
  as links under "Not included (size cap)" rather than silently dropped.
  Compression is deliberately left to the proxy: the corpus is plain
  `text/markdown`, and gzip/br belongs to the layer that already
  negotiates it per request.

The routes exist on all three backends and negotiate content exactly like
`/llms.txt` — browsers get the rendered viewer, agents/crawlers/`?raw=1`
get Markdown — with one exception: a browser asking for `/llms-full.txt`
receives a short summary card (page count, size, links to the raw corpus
and the other tiers) instead of the corpus rendered to HTML, which at full
size would freeze the tab. The full tier always carries
`X-Robots-Tag: noindex`, because a document that duplicates every page's
content would otherwise compete with those pages in search results.
`LLMSConfig(llms_tiers=False)` turns both routes off.

The tier suffixes joined `_DOC_ROUTE_SUFFIXES`, so the bot middleware
treats them as documentation routes. Without that,
`RobotsConfig(block_ai_training=True)` served training bots a 403 on the
very documents that exist for them (regression-tested).

Access control composes end to end: `configure_access` verdicts apply to
the tier paths themselves (`deny` → 404 and de-listed from the index,
`gated` → the gate document at 200 — the tier paths are pre-seeded with a
name and description so that gate never renders a bare path as its title),
and `decorate_body` now carries a request's `link_suffix` across
same-origin tier links with the same peer-host and protocol-relative
protections as the existing patterns. `build_llms_tier_doc` is
deliberately a single pure verdict→response mapping: it is the seam where
a future release maps a `priced` verdict to HTTP 402.

### Fixed — how the tier documents read

Three defects found by reading the rendered documents rather than the
tests, all in surfaces this release introduces:

- The viewer's raw-source line promises that agents fetching the URL
  receive "the Markdown below". That is true of every document except
  `/llms-full.txt`, where a browser deliberately gets a summary card and
  an agent gets the corpus — so the one surface whose whole promise is
  that humans and machines read the same bytes was stating a falsehood
  about itself. `render_llms_viewer` takes a `source_note` override and
  the full tier supplies one.
- `/llms-small.txt`'s three closing pointers (page index, full corpus,
  network hub) were emitted as bare adjacent lines. Consecutive lines are
  one paragraph in Markdown, so every renderer collapsed them into a
  single run-on sentence — in the document whose entire purpose is to be
  read quickly. They are now a list under "Other documents".
- The tier advertisement in `/llms.txt` was an unlabelled list appended
  directly to the home page's prose, so it read as a continuation of
  whatever list that prose happened to end with. It now sits under its
  own "Other sizes of this document" heading.

The viewer's block order (banner → raw source → article → footer) and the
equivalence between an agent's bytes and `?raw=1`'s bytes are now pinned
by tests on all three tiers; neither was covered before, which is how the
first defect survived review.

### Docs site only — llms.2plot.dev network-standard pass

Everything in this section is the demo/docs app (`app.py`, `pages/`, the
site-only `lib/`, `scripts/`, `tests/site/`). None of it ships in the
wheel — pyproject enumerates the packaged modules — but it lands in the
repo with this release.

llms.2plot.dev was the last host on the 2plot network serving the blank
social card: none of the eight `register_page` calls passed `image_url=` or
`description=`, so Dash emitted empty `og:image` / `twitter:image` /
`twitter:description` tags per page — and the empty tag, later in document
order, is the one scrapers honour. The head also carried a static
description duplicating Dash's per-page one, and the brand said
"dash-improve-my-llms 2.0" four releases after 2.0.

- New `lib/constants.py` (site identity + OG + internal-UA block; the wheel
  is unaffected — pyproject enumerates its packages). Brand is unversioned
  and package-name-first: "dash-improve-my-llms — crawler / SEO companion
  for Dash apps"; the header version chip now reads the package's
  `__version__` live.
- `image_url=` + `description=` + prefixed `title=` at every
  `register_page`; `register_page_metadata(path="/")` now carries the brand,
  so `/llms.txt`'s H1 and the viewer brand chip state it.
- `app.index_string` declares only what Dash omits (`og:url`,
  `og:site_name`, `og:image:*` auxiliaries, `twitter:image:alt`), plus the
  favicon set, the web manifest (which wore another site's name) and an
  og:url/canonical sync script for SPA navigation. The card itself lives on
  the network CDN: `https://cdn.2plot.ai/github_assets/llms.2plot.dev.png`
  (1200x630), regenerable via the new `scripts/make_social_card.py`.
- Visitor tracking drops the `2plot-internal` UA token at write time, never
  counts `/healthz`, and honours `VISITOR_ANALYTICS_FILE` so test runs stop
  dirtying the checked-in ledger.
- New secretless site suite in `tests/site/` (43 tests: social card,
  identity, internal traffic) alongside the untouched package suite.
- Site runtime floor: `gunicorn>=23` (request-smuggling CVEs in 21.x/22.x).

## [2.3.4] - 2026-07-31

### Fixed — generic home-page names no longer become the site title

Several network deployments served `# Home` as the H1 of their root
`/llms.txt`. The index title preferred the home page's registered name
over `app.title`, and Dash convention is to register the landing page as
`name="Home"` so the navbar link reads well — so the nav label leaked out
as the site's public identity, and agents citing those sites called them
"Home".

Title resolution now goes through `resolve_site_title()`: the registered
home name still wins (so a name-only
`register_page_metadata(path="/", name="my-package")` overrides the
index title without touching the navbar), but *generic* candidates —
`Home`, `Homepage`, `Index`, `Main`, and Dash's constructor-default
`Dash`, case-insensitively — are skipped rather than served, falling
through to `app.title`. The same resolution now feeds the crawler-facing
HTML (`og:title`, schema.org `name`, the no-JS H1) and the llms.txt
viewer's brand chip, so every surface agrees on the site's name.

Sites should still pin their identity explicitly rather than lean on the
fallback chain — see the new "name the site" section in `docs/SKILLS.md`.
The demo app now does exactly that.

## [2.3.3] - 2026-07-31

Two fixes prompted by an external review that compared this network's
llms.txt surfaces with plotly.com's and dash-mantine-components'. Both are
package-level; the consuming apps pick them up with a normal upgrade
(their pins are `>=2.3.2`, so a redeploy suffices).

### Fixed — Anthropic bots were misclassified in robots.txt

The same class of bug as 2.3.2's OAI-SearchBot fix, one vendor over, and
worse in both directions at once. `block_ai_training` disallowed
`anthropic-ai` and `Claude-Web` — deprecated aliases — while
`allow_ai_search` allowed `ClaudeBot`, which is Anthropic's actual
training crawler. So the block stopped no Anthropic training, and because
claude.ai's user-initiated fetcher honours a disallow on the legacy
aliases, it refused to fetch the very documents this package exists to
serve (observed in production: a paste-into-Claude fetch of a site
running the old default config returned ROBOTS_DISALLOWED).

Now: `ClaudeBot` is disallowed in the training branch; `Claude-User`
(fetches when a person asks Claude to read a URL) and `Claude-SearchBot`
(citation indexing) are allowed in the search branch; the deprecated
aliases are not named at all. Regression tests parse the file and assert
the directive per agent, including that the aliases never reappear.

### Fixed — the Markdown surfaces shipped rST directives raw

Directive stripping (`.. toc::`, `.. exec::page.module`,
`.. llms_copy::`) existed only in the HTML renderer, so the Markdown an
agent actually fetches at `/<page>/llms.txt` carried them verbatim —
noise to a model, and an `.. exec::` line above a fenced block reads as
though the fence were the directive's payload. Additionally, a
directive's `:option:` field lines (`:code: false`) were never stripped
on any surface.

`strip_directive_lines()` (new public helper in `markdown_renderer`) now
runs where the prose is resolved, so every surface — the page document,
the index, the crawler HTML, the MCP resource — is clean; the HTML
renderer also swallows option lines. Content inside code fences is
preserved, so a page documenting these directives still shows its
examples.

## [2.3.2] - 2026-07-30

One bug fix on top of 2.3.0, released under its own number because 2.3.0
tarballs were already vendored across the network's repos before the fix
landed — two artifacts with the same version and different code is the
failure this changelog keeps warning about. There is no 2.3.1; the number
was skipped, so no entry for it exists here.

### Fixed — OAI-SearchBot was disallowed inside the allow branch

`generate_robots_txt` emitted `User-agent: OAI-SearchBot` / `Disallow: /`
inside the `allow_ai_search=True` block — every site configured to allow AI
search was asking ChatGPT's search index to exclude it, while the package's
own docs said the default was "allowed". Present since the rule was added.
The old test only checked the agents were *mentioned*; it now parses the
file and asserts the directive on every agent in both the allow and the
block branches.

**Rollout:** every repo vendoring a 2.3.0 tarball should replace it with
`dash_improve_my_llms-2.3.2.tar.gz` and update the pinned filename in its
requirements. The live fingerprint per host is `robots.txt` showing
`User-agent: OAI-SearchBot` followed by `Allow: /`.

### Changed — reference deployment installs the built sdist

This repo's Dockerfile now installs the package from the committed
`dist/dash_improve_my_llms-*.tar.gz` instead of the working tree, so the
reference deployment runs the same artifact every consuming app vendors —
which is what the pre-PyPI verification gate is meant to verify. The sdist
is committed alongside the release; wheels stay out of git.

## [2.3.0] - 2026-07-30

Never deployed beyond dev — superseded same-day by 2.3.2, which is this
release plus the robots.txt fix below it.

Additive and opt-in: an application that calls neither new function behaves
exactly as it did on 2.2.0. Bumped rather than folded into the unpublished
2.2.0 because `dash-documentation-boilerplate` already vendors a 2.2.0 tarball,
and two artifacts with the same version and different code is the failure the
staged rollout exists to prevent.

### Added — per-request access control

`configure_access(check, gate_doc=…, link_suffix=…)`. Until now the only gate
was `mark_hidden()`, a process-wide set: it can answer "is this page hidden?"
but not "is this page hidden **from this requester?**". An application with
accounts could gate its own layout and nothing else — on the site that prompted
this, a page marked "signed-in users only" was still serving 90 KB of prose
through `/<page>/llms.txt`, the crawler HTML, the prerendered body and the
sitemap, because those are the surfaces the package owns.

Three verdicts. `allow` serves the prose. `gated` serves `gate_doc(path)` at 200
and keeps the URL listed — a page's existence is public even when its content is
not, which is what makes a sign-up funnel work. `deny` is 404 and delisted, for
surfaces where advertising the URL is itself a disclosure.

The verdict is consulted by every surface that can emit prose:
`build_llms_txt_for_page`, `build_llms_index`, `handle_bot_request`,
`apply_prerender`, `build_sitemap_xml`, and the MCP bridge. A gate covering five
of six is not a gate, and the missing one is invisible until someone reads the
wrong body.

**A check that raises degrades to `gated`** — not `allow` (a bug would publish
gated prose) and not `deny` (a bug would black-hole every document on the site),
logged once per path so a crawler cannot fill the log.

`link_suffix` exists because these documents get pasted into an agent, which
fetches with no cookie. An application can therefore carry authority in the URL,
and the package appends it to the same-origin document links it generates — and,
via `decorate_body`, to those in the application's own prose. Peer and
third-party hosts never receive it; page links never receive it, because
authority opens documents, not pages.

MCP note: the `content=`-style `dash.mcp` registration shapes bake prose in at
startup, where a per-request check cannot apply. When access control is
configured the bridge registers only through handler shapes rather than publish
prose it was asked to protect.

### Added — viewer identity

`configure_viewer_identity(provider)` renders the signed-in reader in the
llms.txt viewer's header. HTML variant only: agents and crawlers already receive
the banner-free Markdown from the same URL, so it costs them nothing and cannot
reach an index. Unconfigured renders nothing, which is what keeps a site without
authentication unaffected.

### Security — cache headers on per-requester documents

The adapters sent `Vary: Accept` and **no `Cache-Control` at all**, which was
fine while every response was identical for every requester. A response that
names its reader, or whose links carry authority, now sends
`Cache-Control: private, no-store`, `Vary: Accept, Cookie` and
`X-Robots-Tag: noindex` — otherwise a CDN could store one visitor's document, or
one visitor's name, and hand it to the next. All three adapters.

### Added — bulletin sign-in fields

`network.sign_in_url` and `network.account_label`, so a satellite that gates
documents but doesn't own the accounts can point at the hub. `docs/BULLETIN.md`
now also states, in terms, that the visitor's identity must never travel in that
payload — it is TTL-cached and shared across every satellite.

### Added — tests

`tests/test_access.py`: 27 cases over the resolver, the fail-safe, the gate
document fallbacks, link decoration, identity normalisation, and real requests
through the Flask adapter asserting both the surfaces and the headers. Includes
a regression for a key leaking to a peer host — the relative-URL pattern used to
match the `//host/llms.txt` tail of an absolute URL, because `//` after `https:`
reads as the start of a path.

Contract: [`docs/ACCESS.md`](docs/ACCESS.md).

## [2.2.0] - 2026-07-29

Everything below shipped as one release. 2.1.0 was assigned during
development and never published, so there is no 2.1.0 on PyPI and no entry
for it here — 2.0.0 upgrades straight to 2.2.0.

### Fixed — pages were serving crawlers an empty body

The headline bug. Sites were serving

```html
<main><p>This page contains interactive content that requires JavaScript.</p></main>
```

on most of their URLs, despite having prose registered and despite
`/<page>/llms.txt` returning that prose correctly. On one production site,
12 of 14 crawlable pages were affected. To a search engine the result is a
set of thin near-duplicates differentiated only by their meta description.

Two independent faults combined:

- **`register_page_metadata()` assigned instead of merging.** Any later
  call that refreshed a page's name or description silently deleted its
  `llms_doc`. Apps that loop over `dash.page_registry` to backfill titles —
  a common and reasonable pattern — erased every page's prose. It now
  merges; passing `None` leaves an existing value alone, and passing `""`
  clears a field deliberately.
- **The module-level `LLMS_DOC` fallback required `page_registry["module"]`
  to be an importable module name.** `dash.register_page` takes the module
  positionally, so pages registered in a loop commonly hold a display name
  there ("Activity · Cockpit"), which is not in `sys.modules`. Resolution
  now falls back to the module that defines the page's layout, and also
  accepts `llms_doc` passed straight through `dash.register_page(**kwargs)`.

Both fixes apply without any change to consuming applications.

### Added — universal prerender

Each page's prose, per-page `<title>`, meta description, canonical URL and
JSON-LD are now injected into the initial HTML for **every** visitor, not
only recognised crawlers. Dash's `createRoot().render()` replaces the block
when React mounts, so the interactive app is unaffected.

This removes the stub-for-users/prose-for-crawlers split, which is the
pattern search engines flag as cloaking even when the intent is benign
(Google deprecated dynamic rendering as a recommendation in 2022), and it
improves LCP. The user-agent path is kept as a cheaper fallback.

Disable with `LLMSConfig(prerender=False)`.

### Added — cross-host network directory

`register_network()`, `register_network_site()` and `describe_network()`
declare relationships between separately-hosted apps in three tiers:
`peer` (same network), `affiliated` (yours, own domain) and `external`
(third-party references, emitted `rel="nofollow"`).

Sitemaps are scoped to one origin by design, so a network spread across
hosts has no crawl graph between them — and an agent, which fetches one URL
rather than crawling, sees one app instead of twenty. The directory is
rendered into `/llms.txt`, into the prerendered HTML, and as
`<link rel="related">`. See `docs/NETWORKS.md`.

### Added — page `llms.txt` documents are no longer dead ends

A page's `llms.txt` is usually fetched in isolation: pasted into a chat,
handed to an agent. On its own it described that page and nothing else — no
link to the site's other pages, no link to the network, nothing to follow. An
agent's exploration simply stopped there.

Each page document now opens with three lines pointing at the site index, the
network index (when a network is configured) and the sitemap. Disable with
`LLMSConfig(llms_nav=False)`.

### Added — a rendered `llms.txt` view for people

The same URL now content-negotiates. Agents, crawlers, curl and link
unfurlers receive the Markdown byte for byte; a browser receives that
Markdown rendered, behind a header carrying the network identity.

The header exists only in the HTML variant, so it costs an agent nothing —
which is why it isn't prepended to the Markdown for everyone. `?raw=1`
forces Markdown, `?format=html` forces the view, both variants send
`Vary: Accept` so a CDN can't hand cached HTML to the next agent, and the
rendered view is `noindex` so it never competes with the real page. Disable
with `LLMSConfig(llms_viewer=False)`.

### Added — network bulletin

`configure_bulletin(url=...)` points an app at a hub-published JSON document
of tips and announcements, rendered in the `llms.txt` view header. It exists
so a twenty-site network can say "here is what changed" once instead of in
twenty repositories. Contract in `docs/BULLETIN.md`.

Opt-in — with no call to `configure_bulletin` the package makes no outbound
requests. Fetches happen on a daemon thread behind a TTL cache, so a request
never blocks on it, a stale copy keeps serving while a refresh runs, and a
dead endpoint degrades to "no bulletin" rather than a 500. The payload is
treated as untrusted: every string capped, non-`http(s)` URLs dropped,
everything HTML-escaped at render time.

`configure_bulletin(app_id=...)` sends the satellite's identity as `?app=`,
so a hub can target announcements at particular sites and see which of them
are actually rendering the bulletin.

### Added — wordmark rendering

The `llms.txt` view header carries a network mark, supplied as data via
`describe_network(wordmark=...)` or the bulletin payload. Two forms: a list
of ASCII-art lines, or a **morse mark** — a prefix, a word encoded as morse
and drawn as columns of dots and dashes, and a suffix:

```python
register_network(
    wordmark={"morse": "docs", "prefix": "", "suffix": "dev", "label": "docs.dev"},
)
```

Rendered as self-contained inline SVG — no external fonts, no image
requests, no script — because it lands in a documentation page that has to
render behind any CSP. Columns sit on the text's baseline, derived from the
font metrics rather than hardcoded, and the viewBox measures its vertical
bounds from what was drawn so a tall letter column cannot be cropped.

The symbols key on in sequence, left to right, like a signal being
transmitted. Animation is suppressed under `prefers-reduced-motion`.

The package ships no branding of its own; the mark is configuration.

### Added — deployment for the documentation site

`render.yaml`, `Dockerfile` and `docs/DEPLOYMENT.md` deploy this repo's demo
app as its own documentation site. The Dockerfile installs the package from
the working tree rather than PyPI, so the reference deployment cannot lag
the code it documents. `app._base_url` now reads `APP_BASE_URL` from the
environment, and a `/healthz` route echoes the resolved value — which makes
the most common misconfiguration a one-request check instead of a
page-source inspection.

### Fixed — FastAPI route annotations

`_fastapi_adapter.py` no longer uses `from __future__ import annotations`.
FastAPI resolves handler annotations against *module* globals, and `Request`
is imported inside the registration function — so with postponed evaluation
FastAPI silently treated `request: Request` as an undeclared query parameter
and every `/llms.txt` request returned 422. Caught by the Dash version matrix.

### Changed — root `/llms.txt` is now an index

It previously echoed the home page's prose. It now leads with that prose,
then lists every visible page with its own `llms.txt` URL, then the network
directory — following the llmstxt.org format.

### Changed — Markdown renderer rewritten

The previous renderer handled headings, paragraphs, bullets, blockquotes,
inline code and bold. Everything else fell through as literal text. Most
consequentially **links** did: `[text](/page)` rendered as those exact
characters, so every cross-reference written inside prose was invisible to
crawlers and the internal link graph collapsed to whatever the generated
nav contained.

Now supports links, fenced code with language classes, images with alt
text, horizontal rules, ordered lists, pipe tables, strikethrough and
italics. rST-style directives (`.. toc::`, `.. llms_copy::`) are stripped
from prose but preserved inside code fences.

New module `markdown_renderer.py`; `html_generator._render_markdown_minimal`
remains as an alias.

### Security

- **JSON-LD injection.** Page names and descriptions are author-supplied
  and were embedded in `<script type="application/ld+json">` via
  `json.dumps`, which escapes quotes but not angle brackets. A page named
  `</script><script>…` broke out of the block. Output is now
  `\u`-escaped.
- Markdown link and image targets are checked against a scheme allowlist,
  so `javascript:` and `data:` URLs in prose render as plain text.

### Changed — schema.org types

Each page is now a `WebPage` with an `isPartOf` `WebSite`, rather than
every URL being typed `WebApplication`. Override per page with
`register_page_metadata(path, schema_type="TechArticle")`.

### Added — path normalization

Registration and lookup now agree on one canonical path form, so
`"docs"`, `"/docs"` and `"/docs/"` no longer produce silent misses in
`register_page_metadata` and `mark_hidden`.

### Added — testing and CI

- Integration tests driving real requests through all three adapters.
  These previously had **zero** coverage, which is how a regression that
  emptied every page body passed a green suite.
- `scripts/smoke_test.py` boots a real app and asserts the served bytes.
- `scripts/matrix.py` runs it across every supported Dash version.
- GitHub Actions CI (Dash 4.1.0–4.4.1 × Python 3.9–3.13 × three backends)
  and CD publishing to PyPI from a version tag via trusted publishing.

### Added — upstream compatibility warnings

`_compat.py` records Dash/backend combinations that are broken in Dash
itself, verified against stock Dash with this package uninstalled, and
warns at startup:

- **Dash 4.3.0 + FastAPI** — the page catch-all does not call
  `set_current_request()`, so every non-root URL raises
  `RuntimeError: No active request in context` and returns 500. Fixed in
  Dash 4.4.0. Use `dash>=4.4.0`, or Flask/Quart on 4.3.0.
- Dash 4.1.0 has no pluggable backends; Flask is the only option.

### Changed — requirements

- `dash>=4.1,<5` (was `dash>=3.0.0`).
- Python `>=3.9` (was `>=3.8`).
- Coverage flags removed from pytest `addopts`; they made the suite
  unrunnable anywhere without `pytest-cov`. Opt in with `--cov`.

## [2.0.0] - 2026-05-26

### Breaking Changes — scope rescoped for the Dash 4.x / MCP era

2.0 narrows the package to the surfaces that Dash 4.3's MCP server and
native Dash do NOT cover. Component-tree introspection — which Dash MCP
exposes live and structurally — has been removed. The package now
focuses on three audiences:

| Audience              | How they reach the app          | What 2.0 serves them                         |
|-----------------------|---------------------------------|----------------------------------------------|
| MCP clients           | JSON-RPC over Streamable HTTP   | `LLMS_DOC` registered as `dash.mcp` resource |
| Web crawlers          | Plain HTTPS, often no JS        | `/robots.txt`, `/sitemap.xml`, static HTML   |
| Paste-into-chat users | One-shot HTTP fetch             | `/llms.txt`, `/<page>/llms.txt` as markdown  |

### Removed

- `/page.json` and `/<page>/page.json` — Dash 4.3 MCP exposes layouts as
  resources natively.
- `/architecture.txt` and `/architecture.toon` — MCP describes
  component hierarchy more accurately and live per request.
- `/llms.toon` and `/<page>/llms.toon` — the entire `toon_generator.py`
  module (~1,900 lines).
- Component-tree extraction portion of `/llms.txt` — replaced by
  the explicit `LLMS_DOC` pattern.
- `mark_important()` and `mark_component_hidden()` — these up-ranked
  and excluded sections during layout extraction; with no extraction,
  they have no job. Kept as deprecation-warning no-ops for one release.
- `TOONConfig`, `PageType`, `generate_llms_toon`,
  `generate_architecture_toon`, `generate_documentation_toon`,
  `toon_encode`, `detect_page_type`, `extract_prose_content`,
  `extract_markdown_content` — all removed from the public API.

### Added

- **Multi-backend support** via a backend-detecting dispatcher in
  `add_llms_routes(app)`. The package now works under Flask, FastAPI,
  and Quart (Dash 4.1+) without any caller changes.
  - `dash_improve_my_llms/_flask_adapter.py`
  - `dash_improve_my_llms/_fastapi_adapter.py` (new)
  - `dash_improve_my_llms/_quart_adapter.py` (new)
- **MCP bridge** (`dash_improve_my_llms/_mcp_bridge.py`) — registers
  each non-hidden page's `LLMS_DOC` as a `dash.mcp` resource when
  Dash 4.3+ is available. Silent no-op on older Dash.
- **`LLMS_DOC` pattern** — every page module exports a module-level
  `LLMS_DOC = "..."` string. That string is served verbatim at
  `/<page>/llms.txt` and registered as the MCP resource body. No layout
  walking, no extraction, no surprises.
- **`register_page_metadata(path, llms_doc="...")`** — an alternative
  way to provide prose for pages whose docs are auto-generated or
  imported.
- **Missing-LLMS_DOC warning** — `add_llms_routes()` now emits a single
  `UserWarning` naming every non-hidden page without prose. Silence with
  `LLMSConfig(warn_missing_llms_doc=False)`.
- **Stub fallback** — pages without `LLMS_DOC` get a small placeholder
  body at their `/llms.txt` endpoint so bots receive a 200 instead of
  a 404. The stub names the page and explains how to add real prose.
- **Pure framework-agnostic handlers** in
  `dash_improve_my_llms/handlers.py`. Bot decisions, page lookup, and
  body generation are now testable without spinning up a server.
- **`LLMSConfig.register_mcp_resources`** flag (default `True`) — opt
  out of MCP bridge registration without touching the HTTP surfaces.

### Changed

- `add_llms_routes(app, config)` now detects the backend via
  `dash.backends.get_server_type` (Dash 4.2+) with a fallback to
  `type(app.server).__name__` for older Dash and unusual servers.
- `register_page_metadata()` now accepts a `llms_doc=` kwarg.
- Static-HTML prerender for crawlers now renders the page's
  `LLMS_DOC` as HTML (minimal markdown parser, no extra deps) instead
  of dumping the component tree.
- `pyproject.toml` no longer hard-depends on Flask. Install one of:
  - `pip install dash-improve-my-llms[flask]` (default for Dash 3.x)
  - `pip install dash-improve-my-llms[fastapi]` (Dash 4.1+)
  - `pip install dash-improve-my-llms[quart]` (Dash 4.1+ async)
  - `pip install dash-improve-my-llms[all]`

### Migration from 1.x

For most apps, 2.0 migration is:

1. Add a `LLMS_DOC = """..."""` string at module scope on each page.
   You'll see a `UserWarning` at startup naming pages that need one.
2. Remove `mark_important(...)` and `mark_component_hidden(...)` calls.
   They're no-op shims in 2.0 and will be deleted in 2.1.
3. Update any links / references pointing at `/page.json`,
   `/architecture.txt`, or `/llms.toon` — those endpoints are gone.
4. Install the matching backend extra (`[flask]`, `[fastapi]`, or
   `[quart]`).

The HTTP surfaces that survived (`/llms.txt`, `/robots.txt`,
`/sitemap.xml`) and the `RobotsConfig`, `mark_hidden`,
`register_page_metadata` APIs are unchanged.

### Internal

- Public package surface: 4,373 → ~1,930 lines.
- `__init__.py`: 1,682 → ~290 lines (now mostly the dispatcher).
- Three new framework adapters total ~250 lines.
- Pure-function `handlers.py` (~380 lines) is testable without any
  server.

---

## [1.2.0] - 2025-12-13

### 🎯 Documentation-Aware TOON Generation

This release introduces **adaptive page type detection** and **documentation-optimized TOON generation**. The hook now intelligently detects whether a page is documentation, interactive, or hybrid, and generates TOON content optimized for each type.

### ✨ New Features

#### Page Type Detection
- **`PageType` Enum**: New enum with `DOCUMENTATION`, `INTERACTIVE`, and `HYBRID` values
- **`detect_page_type()`**: Automatically analyzes page layouts to determine content type
- **Scoring System**: Uses markdown content, section count, code blocks, callbacks, and interactive components

```python
from dash_improve_my_llms import detect_page_type, PageType

page_type = detect_page_type(layout, callback_count=2)
# Returns: PageType.DOCUMENTATION, PageType.INTERACTIVE, or PageType.HYBRID
```

#### Documentation-Optimized TOON Generation
- **`generate_documentation_toon()`**: New function for documentation-heavy pages
- **Full Prose Extraction**: Captures complete markdown content, not just structure
- **Code Block Preservation**: Maintains full code examples with language detection
- **Table Extraction**: Parses and preserves HTML tables for reference documentation
- **List Processing**: Extracts ordered and unordered lists

```python
from dash_improve_my_llms import generate_documentation_toon

toon_output = generate_documentation_toon(
    page_path="/examples/directives",
    layout=layout,
    page_name="Custom Directives",
    app=app
)
```

#### Enhanced Prose Extraction
- **`extract_prose_content()`**: New comprehensive text extraction function
- **Extracts from multiple sources**:
  - `dcc.Markdown` children (raw markdown text)
  - `html.P` paragraph content
  - `html.H1-H6` headings
  - `html.Li` list items
  - `html.Code/Pre` code elements
  - `html.Table` structures

```python
from dash_improve_my_llms import extract_prose_content

prose = extract_prose_content(layout)
# Returns: {
#   "sections": [...],
#   "code_blocks": [...],
#   "lists": [...],
#   "tables": [...],
#   "prose": [...],
#   "headings": [...],
#   "raw_markdown": [...]
# }
```

#### New TOONConfig Options
```python
from dash_improve_my_llms import TOONConfig

config = TOONConfig(
    # v1.2.0 New Options
    extract_prose=True,           # Extract prose text from components
    extract_code_blocks=True,     # Include full code blocks
    extract_tables=True,          # Preserve table structures
    max_prose_chars=5000,         # Limit prose per section
    max_code_blocks=15,           # Limit code examples per page
    section_depth=4,              # How deep to nest sections (h1-h4)
    include_examples=True,        # Include usage examples
    compress_code=True,           # Compress code (remove excess whitespace)
    page_type_override=None,      # Force: "documentation", "interactive", "hybrid"
)
```

#### Adaptive TOON Generation
`generate_llms_toon()` now automatically dispatches to the appropriate generator:
- **DOCUMENTATION pages**: Uses `generate_documentation_toon()` for prose-focused output
- **INTERACTIVE pages**: Uses component/callback-focused format
- **HYBRID pages**: Combines both with prose sections and code examples alongside interactive metadata

### 📊 Documentation TOON Format (v3.2)

Documentation pages now generate a specialized format optimized for tutorials, guides, and API docs:

```toon
meta:
  path: /examples/directives
  name: Custom Directives
  type: documentation
  generator: dash-improve-my-llms
  version: 1.2.0
  format: toon/3.2

context:
  description: Part of 7-page Dash documentation site
  totalPages: 7
  relatedPages[6]{name,path}:
    Getting Started,/getting-started
    Interactive Components,/examples/components
    ...

sections[5]:
  1:
    n: 1
    title: Table of Contents Directive
    level: 2
    content: >
      The toc directive generates navigation from markdown headings.
      Place it at the start of your documentation file...

  2:
    n: 2
    title: Execute Directive
    level: 2
    content: >
      The exec directive renders Python components inline with
      optional source code display...

codeExamples[3]:
  1:
    n: 1
    lang: python
    code: |
      from dash import html
      import dash_mantine_components as dmc

      component = dmc.Button("Click Me!", id="demo")

  2:
    n: 2
    lang: markdown
    code: |
      .. exec::docs.examples.button_example
          :code: false

tables[1]:
  1:
    n: 1
    headers: [Directive, Syntax, Purpose]
    rows[5]:
      [toc, ".. toc::", Generate table of contents]
      [exec, ".. exec::path", Render Python component]
      ...

lists[2]:
  1:
    type: unordered
    items[4]:
      - Use toc at the start of every page
      - Combine exec with source for examples
      ...

summary: Documentation page: Custom Directives. Contains 5 section(s). Includes 3 code example(s). Has 1 reference table(s).
```

### 🔧 Technical Changes

- TOON format version bumped to `toon/3.2`
- Package version bumped to `1.2.0`
- New exports in `__all__`: `PageType`, `detect_page_type`, `extract_prose_content`, `generate_documentation_toon`
- Hybrid pages now include prose sections and code examples alongside interactive metadata

### 💡 Use Cases

**For Documentation Sites (like Dash-Documentation-Boilerplate)**:
- Full prose content is captured from `dcc.Markdown` components
- Code examples are preserved for tutorials
- Directive syntax examples are maintained
- Reference tables are extractable

**For Interactive Dashboards**:
- Continues to use optimized callback/component format
- No changes to existing behavior

**For Mixed Applications**:
- Hybrid detection combines both approaches
- Documentation content appears alongside interactive metadata

### 💡 Breaking Changes

None - v1.2.0 is fully backward compatible with v1.1.0. Existing code continues to work without modification. The new page type detection is automatic and enhances output quality.

---

## [1.1.0] - 2025-12-13

### 🎯 Enhanced TOON Format: Lossless Semantic Compression

This release addresses the critical content gap between `llms.txt` and `llms.toon` formats. The TOON format now achieves **lossless semantic compression** - preserving all meaningful content while maintaining 40-50% token reduction.

### ✨ New Features

#### Enhanced Content Extraction
- **Markdown Content Extraction**: New `extract_markdown_content()` function captures content from `dcc.Markdown` components
- **Code Block Parsing**: New `parse_markdown_content()` extracts and preserves code examples from markdown
- **Smart Compression**: New `compress_code_example()` and `compress_section_content()` functions maintain essential information while reducing tokens

#### TOON Format v3.1 Improvements

**Gap #1 - Application Context**: Added explicit context framing
```toon
context: Part of multi-page Dash app with 3 total pages
related_pages[3]{path,name}:
  /,Home
  /equipment,Equipment Catalog
  /analytics,Analytics Dashboard
```

**Gap #2 - Page Purpose Explanations**: Human-readable purpose descriptions
```toon
purpose:
  flags: [data_input, interactive]
  explanation:
    - Contains form elements for data entry
    - Responds to user interactions with dynamic updates
```

**Gap #3 - Component Breakdown**: Type distribution added
```toon
components:
  total: 23
  interactive: 5
  static: 18
  breakdown:
    Div: 8
    Button: 3
    TextInput: 2
    Select: 2
    Graph: 1
```

**Gap #4 - Callback Descriptions**: Human-readable callback documentation
```toon
callbacks[2]:
  1:
    updates: equipment-list.children
    triggers: equipment-search.value, equipment-category.value
    description: Updates equipment list when search or category changes
  2:
    updates: stats-display.children
    triggers: equipment-list.children
    reads: current-filter.data
    description: Updates statistics based on filtered equipment list
```

**Gap #5 - Summary Section**: Synthesized page summary
```toon
summary: >
  Equipment Catalog is a data input and interactive page with 23 components
  (5 interactive) and 2 callbacks. Users can search and filter equipment
  with real-time updates. Contains forms and interactive visualizations.
```

**Gap #6 - Link Categorization**: Internal vs external links separated
```toon
navigation:
  internal[2]:
    Home: /
    Analytics: /analytics
  external[1]:
    Documentation: https://docs.example.com
```

#### New TOONConfig Options
```python
TOONConfig(
    preserve_code_examples=True,   # Include code snippets (NEW)
    preserve_headings=True,        # Keep section structure (NEW)
    preserve_markdown=True,        # Extract dcc.Markdown content (NEW)
    max_code_lines=30,             # Max lines per code example (NEW)
    max_sections=20,               # Max sections to include (NEW)
    max_content_items=100,         # Increased from 20 (UPDATED)
)
```

#### New Helper Functions
- `_generate_page_summary()`: Creates synthesized page summaries
- `_format_callback_description()`: Generates human-readable callback descriptions

### 🔧 Technical Changes

- TOON format version bumped to `toon/3.1`
- Package version bumped to `1.1.0`
- Enhanced `generate_llms_toon()` with all 6 gap fixes
- Improved content extraction depth and accuracy

### 📊 Token Efficiency

| Format | Tokens | Reduction |
|--------|--------|-----------|
| llms.txt | ~15,000 | baseline |
| llms.toon v1.0.0 | ~200 | 98% (too aggressive, lost content) |
| llms.toon v1.1.0 | ~6,000-8,000 | 40-50% (lossless semantic) |

### 💡 Design Principle

> **TOON should be a LOSSLESS SEMANTIC COMPRESSION of llms.txt content**
>
> The goal is not maximum token reduction, but optimal information density.
> All meaningful content is preserved while removing only formatting overhead.

### 💡 Breaking Changes

None - v1.1.0 is fully backward compatible with v1.0.0.

---

## [1.0.0] - 2025-12-07

### 🎉 Major Release: TOON Format Support

This release marks the **production-ready 1.0.0 milestone** with the addition of TOON (Token-Oriented Object Notation) format support, achieving **50-60% token reduction** compared to markdown llms.txt output.

### ✨ New Features

#### TOON Format Integration
- **New `/llms.toon` endpoint**: Token-optimized LLM documentation format
- **New `/<page>/llms.toon` endpoints**: Per-page TOON format support
- **New `/architecture.toon` endpoint**: Token-optimized application architecture
- **Built-in TOON encoder**: Works without external dependencies (fallback encoder)
- **Optional `python-toon` package support**: For full spec compliance

#### TOON Format Benefits
- **50-60% fewer tokens** compared to markdown llms.txt format
- **Tabular arrays** for uniform data structures (`[N]{fields}:` syntax)
- **Explicit length markers** for LLM validation
- **YAML-like readability** with JSON-compatible data model
- **Primitive arrays** inline format for lists

#### New Module: `toon_generator.py` (~600 lines)
- `TOONConfig` dataclass for configuration
- `TOONEncoder` class for TOON format encoding
- `toon_encode()` function with fallback support
- `generate_llms_toon()` for page-level TOON output
- `generate_architecture_toon()` for app-wide architecture

#### New Exports
```python
from dash_improve_my_llms import (
    TOONConfig,           # Configuration dataclass
    toon_encode,          # Low-level encoder
    generate_llms_toon,   # Page TOON generation
    generate_architecture_toon,  # App TOON generation
)
```

### 📝 Documentation Updates

- Updated `templates/index.html` with TOON discovery links
- Updated `html_generator.py` with TOON links in noscript sections
- Updated `app.py` with TOON route examples and documentation
- Updated `pages/home.py` with TOON feature showcase
- Created `TOON_INTEGRATION_PLAN.md` implementation guide

### 🔧 Technical Changes

- Version bumped to `1.0.0` (Production/Stable)
- Updated pyproject.toml classifiers to "Production/Stable"
- Added TOON-related keywords to package metadata
- Updated bot middleware to skip TOON routes

### 💡 TOON Format Example

**Markdown llms.txt (~312 tokens):**
```markdown
# Equipment Catalog

> Browse and filter the complete equipment catalog

## Interactive Elements
**User Inputs:**
- TextInput (ID: `equipment-search`) - Search equipment...
- Select (ID: `equipment-category`)
```

**TOON format (~127 tokens):**
```toon
page:
  path: /equipment
  name: Equipment Catalog
  description: Browse and filter the complete equipment catalog

interactive:
  inputs[2]{id,type,placeholder}:
    equipment-search,TextInput,Search equipment...
    equipment-category,Select,
```

### 📦 New Routes

| Route | Description |
|-------|-------------|
| `/llms.toon` | Token-optimized LLM documentation |
| `/<page>/llms.toon` | Per-page TOON format |
| `/architecture.toon` | Token-optimized architecture |

### 💡 Breaking Changes

None - v1.0.0 is fully backward compatible with v0.3.0.

### 🔗 References

- [TOON Specification v3.0](https://github.com/toon-format/spec)
- [python-toon PyPI](https://pypi.org/project/python-toon/)

---

## [0.3.0] - 2025-11-05

### 🎉 Enhanced Bot HTML Generation

Critical fix: AI chatbots (ChatGPT, Claude, etc.) can now properly see and navigate your Dash apps.

#### What Changed
- ✅ Bots now receive **comprehensive static HTML** with full content
- ✅ Complete **Schema.org structured data** for AI understanding
- ✅ Full **navigation structure** for proper crawling
- ✅ **SEO meta tags** and Open Graph support
- ✅ **Important sections** rendered as proper HTML

#### Technical Improvements
- Enhanced `html_generator.py` with full structured data
- Added Schema.org JSON-LD for all pages
- Improved navigation rendering for bots
- Added noscript fallback content

---

## [0.2.0] - 2025-11-04

### 🎉 Major New Features

#### Bot Detection & Response Middleware
- **Bot Detection System**: Automatically detect and categorize bots into three types:
  - **Training Bots**: GPTBot, anthropic-ai, CCBot, Google-Extended, etc.
  - **Search Bots**: ClaudeBot, ChatGPT-User, PerplexityBot, etc.
  - **Traditional Bots**: Googlebot, Bingbot, Yahoo, DuckDuckBot, etc.
- **Bot Response Middleware**: Serve different content based on bot type
  - Training bots: 403 Forbidden (when `block_ai_training=True`)
  - Search/Traditional bots: llms.txt content wrapped in HTML (solves JavaScript execution problem)
  - Browsers: Full Dash React application
- **Solves Critical Issue**: AI crawlers cannot execute JavaScript, so they now receive readable llms.txt content instead of empty `<div id="react-entry-point">` placeholders

#### robots.txt Generation
- **Dynamic robots.txt**: Automatically generated based on `RobotsConfig`
- **RobotsConfig Dataclass**: Configure bot access policies
  ```python
  RobotsConfig(
      block_ai_training=True,      # Block AI training bots
      allow_ai_search=True,        # Allow AI search bots
      allow_traditional=True,      # Allow traditional search bots
      crawl_delay=10,              # Crawl delay in seconds
      disallowed_paths=["/admin", "/api/*"]  # Paths to block
  )
  ```
- **Smart Bot Rules**: Automatically generates appropriate rules for each bot type
- **Hidden Pages**: Respects `mark_hidden()` for privacy control

#### sitemap.xml Generation
- **SEO-Optimized Sitemaps**: Automatic XML sitemap generation
- **Smart Priority Inference**: Automatically determines page priority based on:
  - Root pages (/) → High priority (0.9-1.0)
  - Important pages (marked with `mark_important()`) → Medium-high priority (0.7-0.8)
  - Detail pages (/item/:id) → Medium priority (0.5-0.6)
  - Utility pages (/settings) → Lower priority (0.3-0.5)
- **Respects Hidden Pages**: Pages marked with `mark_hidden()` are excluded from sitemap
- **Automatic Updates**: Always reflects current app structure

#### Visitor Analytics & Tracking
- **Device Detection**: Automatically detect device type (desktop, mobile, tablet, bot)
- **Bot Tracking**: Track bot visits with bot type categorization
- **Analytics Storage**: JSON-based visitor tracking with timestamps
- **Privacy-First**: File-based storage, no external services required

#### Admin Dashboard
- **Professional UI/UX**: Built with design.txt best practices
  - Restrained color palette (violet primary, gray secondary)
  - Systematic spacing tokens (xs, sm, md, lg, xl)
  - Progressive disclosure with tabs
  - Visual hierarchy (prominent numbers, small labels)
- **Three Main Tabs**:
  - **Overview**: Charts and visualizations
    - Total visits and device breakdown
    - Visits by hour (last 24h)
    - Device distribution pie chart
    - Top visited pages bar chart
  - **Bot Activity**: Detailed bot visit logs
    - Bot type categorization
    - User agent information
    - Visit timestamps
    - Path tracking
  - **Configuration**: Bot type reference and settings
    - Complete bot type documentation
    - Example user agents
    - Configuration examples
- **Real-time Data**: Auto-refreshing analytics
- **Hidden by Default**: Admin page excluded from robots.txt and sitemap.xml

### ✨ Enhanced Features

#### llms.txt Generation
- **Application Context**: Multi-page app information with related pages list
- **Page Purpose Inference**: Automatically determines page purpose
  - Data Input, Visualization, Navigation, Interactive
- **Interactive Elements**: Detailed breakdown of inputs and outputs with IDs
- **Navigation Mapping**: Internal and external links with destinations
- **Component Statistics**: Total, interactive, and static counts
- **Data Flow & Callbacks**: Complete callback information showing triggers
- **Narrative Summary**: Human-readable summary of page purpose

#### page.json Generation
- **Component IDs**: All component IDs extracted with types, modules, and properties
- **Component Categories**: Automatic categorization
  - inputs, outputs, containers, navigation, display, interactive
- **Navigation Data**: All links extracted with text and destinations
- **Interactivity Metadata**: has_callbacks, callback_count, interactive_components
- **Callback Information**: Full callback data with inputs, outputs, and state
- **Callback Graph**: Data flow graph showing trigger relationships
- **Rich Metadata**: Flags for forms, visualizations, and navigation

#### architecture.txt Generation
- **Environment Detection**: Python version, Dash version, key packages
- **Dependencies Context**: Automatically detects installed packages
- **Callback Breakdown**: Total callbacks grouped by module
- **Page Descriptions**: Includes custom metadata descriptions
- **Interactive Components**: Counts interactive vs static components per page
- **Enhanced Statistics**: Total pages, callbacks, components, interactive components
- **Top Components**: Shows most-used component types across entire app

### 🛠️ Technical Improvements

- **Flask Middleware Integration**: `before_request` hook for bot interception
- **Hidden Page Support**:
  - `mark_hidden(path)` - Hide entire page from bots
  - `mark_component_hidden(component)` - Hide specific components
- **Page Metadata Registration**: `register_page_metadata()` for custom descriptions
- **Comprehensive Testing**: 100% pass rate on bot response tests (7/7 passing)
  - Training bot blocking
  - Search bot llms.txt serving
  - Browser full app serving
  - Documentation link verification

### 📚 Documentation

- **Implementation Guides**:
  - BOT_MIDDLEWARE_IMPLEMENTATION.md - Complete middleware documentation
  - ADMIN_UX_IMPROVEMENTS.md - UI/UX design principles applied
  - IMPLEMENTATION_SUMMARY.md - Feature implementation summary
  - TEST_REPORT.md - Comprehensive test coverage report

- **Testing Scripts**:
  - test_bot_responses.py - Comprehensive Python test suite
  - test_bot_middleware.sh - Quick bash test script

- **Updated README**: Complete v0.2.0 feature documentation with examples

### 🐛 Bug Fixes

- Fixed `_reload-hash` requests being tracked in analytics
- Fixed RobotsConfig import error in __init__.py
- Fixed bot response differentiation (bots no longer receive React app)

### 💡 Breaking Changes

None - v0.2.0 is fully backward compatible with v0.1.0.

### 🔒 Security

- Training bot blocking prevents unauthorized content scraping for AI model training
- 403 Forbidden responses for blocked bots with clear error messages
- Admin dashboard hidden from search engines by default

---

## [0.1.0] - Initial Release

### Added
- Basic llms.txt generation for Dash pages
- page.json architecture export
- architecture.txt application overview
- `mark_important()` for highlighting key content
- `add_llms_routes()` hook for easy integration
- Multi-page Dash application support

---

**Made with ❤️ by Pip Install Python LLC**
- Homepage: https://pip-install-python.com
- Plotly Pro: https://plotly.pro
- Repository: https://github.com/pip-install-python/dash-improve-my-llms
