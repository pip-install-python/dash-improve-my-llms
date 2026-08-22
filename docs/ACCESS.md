# Access control and viewer identity

A contract for an application to decide, **per request**, who may read a
document the package serves — and to show a signed-in reader who they are,
without any of it reaching an agent, a crawler, or a cache.

Status: **implemented in 2.3.0**, and consumed by 2plot.dev. Verified in
development by 44 assertions over the full access matrix — see "Verifying" at
the end.

Version note: this landed as **2.3.0**, not folded into the unpublished 2.2.0.
`dash-documentation-boilerplate` already vendors a 2.2.0 tarball, and two
artifacts with the same version and different code is exactly the failure the
staged rollout exists to prevent. Everything here is opt-in, so app 1 can stay
on 2.2.0 until it wants these.

---

## Why the package needs this

The package's only access control today is `mark_hidden(path)` — a process-wide
set consulted per request. It answers "is this page hidden?" and cannot answer
"is this page hidden **from this requester**?".

That is enough for internal pages. It is not enough for an application with
accounts. Concretely, on 2plot.dev a docs page marked `auth` in its admin control
board still serves, to anyone:

| surface | serves |
|---|---|
| `/<page>/llms.txt` | full prose, 90 KB |
| crawler HTML | full prose |
| prerendered browser HTML | full prose |
| sitemap + root index | listed |
| the interactive Dash page | ✅ correctly gated |

Only the app's own layout is gated, because that is the only surface the app
controls. Every surface the package owns serves the content. The app cannot fix
this without registering a route in front of the package's — which
2plot.dev did once and which silently ate the 2.2.0 navigation block and the
rendered viewer for a month. **The right fix is a hook, not an interception.**

## The constraint that shapes the design

The obvious implementation — gate on the session cookie — is wrong, and it is
worth stating why before anyone builds it.

These documents exist to be handed to an agent. A user signs in, copies
`https://host/guide/llms.txt`, pastes it into Claude or ChatGPT, and the agent
fetches it **with no cookie**. A cookie gate therefore returns the gate document
to the one consumer the URL exists for, and the site looks broken.

So authority has to be able to travel *in the URL*:

```
https://2plot.dev/components/dash-pos-printer/llms.txt?key=k2p_8f31…
```

The package does not define, mint or validate that key — that is the
application's business, and 2plot.dev's design is sketched at the end for
context. The package only needs to **ask the application** on every request, and
to let the application decorate the links it generates.

---

## Part 1 — `configure_access`

```python
from dash_improve_my_llms import configure_access

configure_access(
    check,                    # (path: str) -> "allow" | "gated" | "deny"
    gate_doc=None,            # (path: str) -> str   Markdown for "gated"
    link_suffix=None,         # () -> str            "" or "?key=…", this request
)
```

**Unset is a no-op.** An application that never calls this behaves exactly as it
does today — which is what makes this safe to land in a release mid-rollout,
with a dozen satellites on the old behaviour.

### The three verdicts

| verdict | document | crawler HTML / prerender | index, sitemap, MCP |
|---|---|---|---|
| `allow` | prose, 200 | prose | listed |
| `gated` | `gate_doc(path)`, **200** | gate doc, no prose | **listed** |
| `deny` | 404 | 404 | omitted |

`gated` and `deny` are genuinely different intents and both are needed:

- **`gated`** — "this document exists and you may not read it yet." The URL stays
  in the sitemap and the index because it is public knowledge that the page
  exists; only the content is restricted. This is the sign-up funnel: an agent
  that fetches it learns what the page is and how to get access.
- **`deny`** — "there is nothing here." Equivalent to today's `mark_hidden`. Use
  for admin surfaces, where advertising the URL is itself a disclosure.

### Where it must be consulted

All of these, or the gate leaks through whichever one is missed. This is the
part to get right; each of them can serve prose independently:

| module | function | why |
|---|---|---|
| `handlers` | `build_llms_txt_for_page` | the document itself |
| `handlers` | `build_llms_index` | the root index lists pages and would name a denied one |
| `bot_detection` / `handlers` | `handle_bot_request` | the crawler-facing HTML body |
| `prerender` | `apply_prerender` | injects prose into **every** visitor's HTML |
| `sitemap_generator` | `build_sitemap_xml` | inclusion |
| `_mcp_bridge` | resource registration | an MCP client reading a gated page |

A useful internal shape is one resolver — `resolve_access(path, state)` — that
folds `hidden_pages` and `check` into a single verdict, so each call site asks
once and no site can forget half the rule. `mark_hidden(path)` then simply means
"`deny`, statically".

### Failure modes

- **An exception in `check` degrades to `gated`**, logged once per path. Not
  `allow` — a bug in an app's callback must not publish gated prose. Not `deny`
  — a bug must not black-hole every document on the site. `gated` leaks nothing
  and keeps the surface answering.
- `check` runs **inside the request**, on every request, on paths that may be hot.
  Document that it must be cheap; 2plot.dev's is two dict lookups and an HMAC
  compare.
- `gate_doc` may also raise or return empty; fall back to a built-in stub
  assembled from the page's registered name and description, plus
  `network.sign_in_url` from the bulletin when one is configured.

### `link_suffix`

When a request arrives with authority in the URL, the links the package
generates **in that response** must carry it too — the navigation block's site
and network index links, and the per-page URLs in the root index. Otherwise the
agent follows them, lands unauthenticated, and the catalogue is untraversable
one hop from the document it was given.

```python
link_suffix=lambda: f"?key={key}" if key else ""
```

Appended only to same-origin generated URLs, never to peer/external links, and
never to the canonical tag or the sitemap. It is scoped to the response being
built — the package must not persist or log it.

This does mean **a document fetched with authority is itself authority-bearing**.
That is the correct trade (the key is already in that agent's context), but the
consuming app should say so wherever it hands out such a link.

---

## Part 2 — `configure_viewer_identity`

```python
from dash_improve_my_llms import configure_viewer_identity

configure_viewer_identity(provider)   # () -> dict | None
```

Returning, for the current request:

```python
{"name": "pip@example.com", "since": "2026-07-30T21:14:00Z", "plan": "pro"}
```

Rendered in the `llms.txt` viewer's banner identity block, beside the app name
and wordmark. **HTML variant only** — agents, crawlers and curl already receive
the banner-free Markdown from the same URL, so this costs them nothing and
cannot reach an index.

- `None`, or never configured, renders nothing. Most satellites have no
  authentication at all and must be unaffected.
- Never raises: wrap it, render nothing on failure.
- `since` is a display string supplied by the app. The package formats, escapes
  and truncates; it does not interpret. (2plot.dev sends session-first-seen,
  because a Clerk session token is refreshed about every 60 seconds and its
  `iat` is the token's age, not a login time — a detail worth repeating in the
  docs so nobody wires `iat` and ships a clock that resets every minute.)

### Cache headers — required, not optional

`_flask_adapter.py` currently sets `Vary: Accept` and **no `Cache-Control` at
all** on either variant. That is fine while every response is identical for every
requester. It stops being fine the moment a response depends on who is asking.

Any response that is identity-bearing **or** authority-bearing must send:

```
Cache-Control: private, no-store
Vary: Accept, Cookie
X-Robots-Tag: noindex
```

Without this, a CDN in front of any host in the network can store one visitor's
banner — name included — and serve it to the next. The anonymous Markdown
variant keeps its current, cacheable headers; this applies only when identity or
a key is in play. The same requirement applies to all three adapters.

---

## Part 3 — Bulletin addition

Two optional fields under `network` in [`BULLETIN.md`](BULLETIN.md),
capped and scheme-checked like every other field:

| field | type | notes |
|---|---|---|
| `network.sign_in_url` | string | Must be `http(s)`. The network's account origin. |
| `network.account_label` | string | ≤120 chars, e.g. "2plot account". |

These belong in the bulletin because they are network-wide, static and
cacheable: a satellite with no authentication of its own can render "Sign in at
2plot.ai", and a gate document can name where access comes from, without every
repository hardcoding the hub.

> **The visitor's identity must never travel in the bulletin.** The bulletin is
> TTL-cached and shared by every viewer of every satellite. A username in it
> would be a privacy bug wearing a cache. Identity is per-request and local, and
> that is what `configure_viewer_identity` is for.

Worth adding to `BULLETIN.md` verbatim, so the distinction survives the next
person who wants to "just add the user to the payload".

---

## Security posture

- **Fail closed on the content, open on the service.** Every ambiguity resolves
  to `gated`: no prose, but the surface answers.
- **`deny` must be indistinguishable from a nonexistent page.** Same 404, no
  timing tell, no "this exists but you can't see it" — that is what `gated` is
  for, when disclosure is intended.
- **Never log the `link_suffix` or anything from it.** For 2plot.dev it contains
  a capability.
- **Authority grants documents only.** The package must not extend it to any
  other route; the application's own pages keep their own gate.
- The consuming app owns key format, lifetime and revocation. The package's
  entire involvement is calling `check` and appending `link_suffix`.

---

## Verifying

```python
# 1. Unset is a no-op: byte-identical to the previous release.
# 2. gated: 200, gate doc, no prose, still in sitemap and index.
# 3. deny:  404 on the document, absent from sitemap, index and MCP,
#           404 to a crawler UA.
# 4. Every surface honours it — assert prose is absent from ALL of:
#      /<page>/llms.txt, the crawler HTML, the prerendered block,
#      the root index, sitemap.xml, the MCP resource list.
# 5. A check that raises -> gate doc, not 500 and not prose.
# 6. link_suffix reaches the nav block and index links, and reaches
#    neither the canonical tag nor sitemap.xml.
# 7. Identity renders in the HTML variant only; the Markdown variant is
#    byte-identical with and without a signed-in provider.
# 8. Identity- or authority-bearing responses carry private, no-store.
```

Point 4 is the one to automate. A gate that covers four surfaces out of six is
not a gate, and the missing one is invisible until someone reads the wrong body.

---

## Appendix — how 2plot.dev will consume this

Context for anyone implementing the package side. None of it is required by the
contract.

- **Verdict** from an admin control board with four tiers per page —
  `public` / `auth` / `admin` / `hidden` — crossed with a per-page
  "public document" toggle. `hidden` → `deny` always. `admin` → `deny` unless
  the requester carries admin authority. `auth` + toggle off → `gated` for
  anonymous, `allow` with authority. Everything else → `allow`.
- **Authority** is a key in the URL, bound to the Clerk session that created it:
  created automatically on authentication, dead when that session ends (Clerk
  webhook), hard-capped at 30 days, one per session so multiple devices don't
  invalidate each other. Derived by HMAC over `user:session:scope:version`, so
  nothing secret is stored and revocation is a version bump.
- **Pass-through**: the site's existing "copy for LLM" button builds the URL
  client-side, so it fetches the current key from a small endpoint and appends
  it. A signed-in user gets a working link without knowing any of this exists;
  an anonymous one copies the same plain URL as today.
- **Identity**: Clerk's `current_user()` plus a first-seen timestamp per session.

The shape of that is what convinced us the hook belongs in the package and the
policy belongs in the app: nothing above needs the package to know what Clerk
is, and none of it is expressible through `mark_hidden`.


---

See also: the read-only operator panel ([PANEL.md](PANEL.md))
displays this module's configuration state — by callback name only; it
never executes a request-scoped check outside its request.
