# Deploying this app to llms.2plot.dev

The package's demo app (`app.py`) doubles as its documentation site. Hosting
it means the claims in the README are demonstrable on real URLs rather than
only in a test suite.

Target: **https://llms.2plot.dev**, Render free tier.

---

## Files

| File | Purpose |
|---|---|
| `render.yaml` | Render Blueprint — service, plan, health check, env vars |
| `Dockerfile` | Python 3.12 + gunicorn, installs the committed release sdist |
| `requirements.txt` | Runtime deps for the demo app only |
| `dist/dash_improve_my_llms-*.tar.gz` | The release artifact the Dockerfile installs |

The Dockerfile installs the package from the committed
`dist/dash_improve_my_llms-*.tar.gz` rather than from the working tree or
PyPI. That is deliberate: the other apps in the network vendor this exact
sdist, so the reference host runs byte-identical code to everyone else —
which is what the pre-PyPI production verification gate is meant to prove.
The cost is a release step: a code change reaches production only after
`python -m build` refreshes `dist/` and the new sdist is committed.

## Deploying

1. Push this repo to GitHub with `render.yaml` and `Dockerfile` at the root.
2. Render dashboard → **New → Blueprint** → select the repo.
3. Once the service is live, **Settings → Custom Domains → Add**
   `llms.2plot.dev`, then point that subdomain's CNAME at the hostname Render
   gives you.
4. Confirm `APP_BASE_URL` matches the custom domain **exactly**.

Step 4 is the one that matters. `APP_BASE_URL` drives every
`<link rel="canonical">`, the absolute URLs in `sitemap.xml` and `llms.txt`,
and the `Sitemap:` line in `robots.txt`. Point it at the wrong host and you
are asking search engines to treat this deployment as a duplicate of
somewhere else — the exact failure previously observed on the network's
`dash_pannellum` host, whose canonicals pointed at its old platform domain.

## Environment

| Variable | Default | Notes |
|---|---|---|
| `APP_BASE_URL` | `https://llms.2plot.dev` | Public origin. Must match the served host. |
| `PORT` | `8959` | Injected by Render. |
| `WEB_CONCURRENCY` | `2` | gunicorn workers. Drop to 1 if 512 MB gets tight. |
| `NETWORK_BULLETIN_URL` | unset | Hub bulletin endpoint. Safe to add later. |
| `DASH_BACKEND` | `flask` | Informational here; the demo app is Flask-only. |

`NETWORK_BULLETIN_URL` is intentionally unset at first launch. `2plot.dev`
does not serve the endpoint yet, and the banner renders fine without it — so
this can be filled in later with no code change and no redeploy of anything
else.

## Free-tier caveats

Both are acceptable for a docs site, but know them:

- **It sleeps after ~15 minutes idle** and cold-starts on the next request. A
  crawler will occasionally see a slow first byte. If Search Console starts
  reporting crawl timeouts, that is the cause, and the fix is a paid plan.
- **The filesystem is ephemeral.** `visitor_analytics.json`, which backs the
  `/admin` demo dashboard, resets on every deploy and eviction. That is fine
  here because it is demo data, not a record of anything.

## Where this host sits in the network

```
llms.2plot.dev  ──hub_url──▶  2plot.dev  ──hub_url──▶  2plot.ai
```

`llms.2plot.dev` is a `*.2plot.dev` subdomain, so its network index is
`2plot.dev/llms.txt` — the component/subdomain index. `2plot.dev` then names
`2plot.ai` as its own hub, which is the network root. See
[`NETWORKS.md`](NETWORKS.md#tiered-hubs) for why the chain beats pointing
every subdomain straight at the root.

Add this host to the shared peer list once it is live, so the rest of the
network links back to it.

## Verifying after deploy

```bash
APP=https://llms.2plot.dev

curl -s $APP/healthz                                   # ok + base_url echo
curl -s $APP/llms.txt | head -30                       # index + directory
curl -s $APP/sitemap.xml | grep -c "<url>"
curl -s $APP/robots.txt | grep Sitemap

# Canonical must be THIS host.
curl -s $APP/ | grep -o 'rel="canonical" href="[^"]*"'

# The crawler body must not be the stub.
curl -s -A "Googlebot/2.1" $APP/networks | grep -c "requires JavaScript"   # 0

# An agent must get Markdown, with a route back to the network.
curl -s $APP/networks/llms.txt | head -8
curl -s $APP/networks/llms.txt | grep -c "dv-banner"                      # 0

# A browser must get the rendered view with the wordmark.
curl -s -H 'Accept: text/html' -A 'Mozilla/5.0 Chrome/120' \
  $APP/networks/llms.txt | grep -c 'mk-wordmark'                          # 1
```

`/healthz` echoes the resolved `base_url`, which makes the most common
misconfiguration a one-request check rather than a page-source inspection.
