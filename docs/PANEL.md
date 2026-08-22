# The operator policy panel

A read-only, token-gated page (default `/llms-policy`) showing the live
effective policy of every surface this package governs. Opt-in:

```python
add_llms_routes(app, LLMSConfig(panel=True))
# token via LLMSConfig(panel_token=...) or the DIMLL_PANEL_TOKEN env var
```

Status: **shipped in 2.7.0.** `panel=False` (default) registers nothing —
the path falls through to the app exactly as before.

## What it shows

| Section | Source | The point |
|---|---|---|
| Identity | package version, base_url, page count | which build answered |
| Vendor policy | `vendors.effective_policies()` — **the same fold robots.txt renders from** | the panel cannot drift from `/robots.txt`; a test pins it |
| Bot policy flags | the attached `RobotsConfig` (or the defaults — exactly what robots.txt serves when none is attached) | says == does, even unconfigured |
| Tier documents | `LLMSConfig` | corpus posture |
| Access control | callback **qualnames only** — request-scoped checks are never invoked outside a request (test-pinned) | who gates, without running the gate |
| Geo guardrail | `geo.effective_policy()` + **"this request resolved to: `DE` (via cf-ipcountry)"** | the live per-host deployment check GEO.md mandates before trusting a denylist |
| Rate limiting | `rate_limit_per_minute` | W4 posture |
| Network | directory, bulletin state, hub tightenings | what the hub has tightened |

Every section ends with the copy-paste call that would change it.

## The gate

- Token compared with `hmac.compare_digest`; transported via the
  `X-LLMS-Panel-Token` header (preferred) or `?token=` (**lands in access
  logs** — use the header where that matters).
- The env var is read **per request**: rotate it and the old token dies
  on the next request, no redeploy. `LLMSConfig(panel_token=...)` beats
  the env var.
- **Unset token ⇒ 404, unconditionally.** Wrong token ⇒ 404 with an
  unrevealing body. The panel never advertises its own existence — and it
  is deliberately absent from robots.txt (a Disallow line publishes the
  path: the `/admin` lesson), the sitemap, and the llms index.
- Success responses carry `X-Robots-Tag: noindex, nofollow` and
  `Cache-Control: private, no-store`.
- The geo guardrail 451s the panel too. Intended: "451 on everything"
  includes the operator standing in a denied country.

## Read-only, and why

Package config is per-process module state. Under gunicorn's N workers, a
panel that *mutated* config would change one worker and lie on the next
refresh — a nondeterministically lying control plane — and a
write-capable endpoint behind a single token is a remote policy override.
So this panel displays and never writes.

**The writable layer above it is your site's control board** — for fleet
sites, the boilerplate's inherited template control board
(`lib/page_visibility.py` + `pages/control_board.py`, boilerplate ≥1.6.0;
the llms satellite extends it with the geo and vendor sections). It
mutates a persisted store on the mounted disk, and the store reaches this
package through the callable seams the panel's hints show:
`configure_geo(deny_countries=store.geo_deny)`,
`RobotsConfig(vendor_policy=store.vendor_policy)` — read per request by
every worker, which is exactly what dissolves the multi-worker problem
the read-only decision guards against. Do not build a from-scratch board;
extend the inherited one.

The footer shows the serving worker's pid and boot time: values that flip
between refreshes mean different workers booted with different code or
env — a deployment diagnostic, not a panel bug.
