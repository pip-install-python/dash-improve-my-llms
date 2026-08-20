# Search identity — `configure_seo`

**Status:** shipped in 2.5.0. Companion to `docs/ACCESS.md` (per-request access)
and `docs/NETWORKS.md` (the cross-host directory).

## The bug this exists to close

This package serves crawlers a **generated document** instead of the
application's own HTML. That is the whole point — a Dash app is an empty div
plus a JS bundle, and the prerender is what makes its prose indexable. But the
generated document carried only *content* signals:

```
title · description · robots · canonical · alternate · sitemap
og:type · og:title · og:description · og:url · JSON-LD
```

and none of the *identity* signals a browser got from `index_string`. Measured
across a live 18-host network in August 2026:

| Signal | Browser | Googlebot |
|---|---|---|
| `<link rel="icon">` | 4–7 | **0 on every host** |
| `og:image` | present | **absent** |
| `twitter:card` | present | **absent** |
| inner-page `<title>` | `pkg \| Attribution` | **`Attribution`** |

Consequences: every host showed the generic globe in Google results, every
Slack and Twitter unfurl was image-less, and every inner page competed in search
under a heading like "Draw & Edit" with nothing identifying the package.

The rule to build to:

> **Content may differ between the crawler document and the browser document.
> Identity may not.**

## Usage

```python
from dash_improve_my_llms import configure_seo

configure_seo(
    icons=[
        "/assets/favicon/favicon.ico",
        {"href": "/assets/favicon/favicon-96x96.png", "sizes": "96x96"},
        {"href": "/assets/favicon/icon-192.png", "sizes": "192x192"},
        {"href": "/assets/favicon/apple-touch-icon.png",
         "rel": "apple-touch-icon", "sizes": "180x180"},
    ],
    social_image="https://cdn.example.com/card.png",   # 1200×630, off-app
    social_image_alt="Example — what it does",
    social_image_width=1200,
    social_image_height=630,
    publisher="Example LLC",
    same_as=[
        "https://pypi.org/project/example/",
        "https://github.com/example/example",
    ],
)
```

Call it once, anywhere before `add_llms_routes`.

**Icons find themselves since 2.6.0.** An app that never calls
`configure_seo()` no longer loses its favicon: `add_llms_routes` reads the
app's own assets folder and adopts what it finds (see "Auto-discovery"
below). Everything else — card, publisher, `same_as` — stays declared-only:
the package cannot infer a CDN card URL or an organisation's identity graph,
and does not guess.

### `icons`

A URL string, or a dict with `href` and optionally `rel` / `sizes` / `type`
(`type` is inferred from the extension). Emitted as `<link>` elements in the
crawler head, and used to answer the well-known root paths.

Include at least one **≥192px square**. Google prefers a multiple of 48px, and
it is what an installable app needs. Note it is a preference, not a
requirement — sites shipping only 16/32/180 still resolve a favicon, because
what actually decides it is whether the crawler can *see* a declaration at all.

### Auto-discovery of icons (2.6.0)

Measured across a 25-app network in August 2026: four apps called
`configure_seo()`, twenty-one did not — and every one of the twenty-one had a
perfectly good favicon sitting in `assets/`. The package was the reason it
went missing (it serves crawlers a generated head instead of the app's own),
so the package now carries the identity forward instead of asking each app to
declare it a second time.

When **no icons are declared**, `add_llms_routes(app)`:

- searches `assets/favicon/`, `favicons/`, `favicon_io/`, `icons/`, `img/`,
  then the assets root — **first directory with icons wins** (a curated
  `favicon/` set beats a stale loose `favicon.ico`);
- matches by glob (`favicon*.ico`, `apple-touch-icon*.png`,
  `android-chrome-*.png`, `icon-[0-9]*.png`, …) so real-world names like
  `favicon_areachart.ico` are found. The `icon-` pattern is digit-anchored
  on purpose: `assets/icons/` holds UI sprites too, and `icon-arrow.png`
  must never become the site's search-result icon;
- infers `rel`/`sizes`/`type` from filename and extension, emits hrefs via
  `app.get_asset_url()` so path prefixes are honoured, and orders `.ico`
  first, then the biggest square;
- **warns** when it finds nothing — a silent blank identity is exactly the
  failure this exists to end.

An explicit `configure_seo(icons=[...])` always wins, and an explicit
`icons=[]` opts out entirely. A discovered set also survives a later
`configure_seo()` call that configures *other* fields — only an explicit
`icons=` argument replaces it. `discover_icons(app)` and
`autoconfigure_icons(app)` are public if you want to inspect or trigger it
yourself.

### `social_image`

Host it **off the app**, on a CDN. An app-served card races a cold container at
unfurl time and the platform caches the miss. If you declare
`social_image_width`/`height` they MUST match the real file — a wrong
declaration is worse than none.

Twitter tags are emitted with `name=`, not `property=`. Declaring them with
`property=` makes them invisible to Twitter; it is a common, silent mistake.

### `publisher` / `logo`

`publisher` names the organisation in JSON-LD. Since 2.6.0 it also carries a
`logo` — what Google shows beside the site in branded results. Declare one
with `configure_seo(logo=...)`, or let the largest declared/discovered raster
icon of at least **112×112** (Google's floor; `.ico` excluded) stand in. The
URL must end up absolute to be crawlable, so a root-relative candidate is
joined onto the app's base URL — and dropped when there is none.

### `same_as`

The other properties that are the same entity: sibling domains, the GitHub
repo, the PyPI project. For a family of domains this is how they tell a search
engine they are one thing rather than N unrelated sites.

### `root_icons`

Defaults True, and only takes effect when `icons` is non-empty. The package
answers `/favicon.ico`, `/apple-touch-icon.png` and
`/apple-touch-icon-precomposed.png` with a 302 to a declared icon.

This matters more than it looks. Google falls back to `<origin>/favicon.ico`
when the page it crawled declares no icon — and Dash's page catch-all answers
that path with the **app shell**, 200 `text/html`, ~100 KB of markup where an
image belongs. That is a poisoned fallback, not a missing one, and it was true
of every host measured. The package redirects rather than serving bytes: it has
no business reading an application's asset folder, and every consumer of these
paths follows a redirect. (Discovery *reads* the assets folder to learn what
the app ships; it still never serves the bytes — the hrefs it emits are
Dash's own asset routes.)

With no icons declared the paths answer 404 — a deliberate change from the
app shell: a crawler that gets 404 correctly concludes "no icon" instead of
parsing HTML where an image belongs.

Set False if your app already serves them. A route your app registered for one
of these paths **before** `improve()` keeps precedence automatically — the
package only claims paths nobody else has. A route registered *after*
`improve()` cannot be honoured; register it first, or pass `root_icons=False`.

## Per-page fields

On `register_page_metadata`:

| Field | Effect |
|---|---|
| `title` | The full `<title>`. Without it the site name is appended to `name`. |
| `og_image` | This page's card, overriding `social_image`. |
| `image_url` | Alias for `og_image`, so a page can pass what it already gives `dash.register_page`. |
| `schema_type` | schema.org `@type`, default `WebPage`. |
| `lastmod` | `YYYY-MM-DD` for the sitemap. When absent, `<lastmod>` is **omitted** — it used to be invented as "today", and a date that always says today is one search engines learn to ignore (2.6.0). |

### Titles

Inner pages become `<page> · <site>`. The home page is left alone (there, the
site name *is* the title), a `name` that already carries the site name is not
double-suffixed, and the suffix uses only the part of the site title **before
its tagline separator** — `"dash-leaflet2 — Leaflet 2 maps for Dash"` suffixes
as `dash-leaflet2`, because Google shows about 60 characters and a 45-character
pitch repeated on every page buys nothing. Pass `title` to override entirely.

The `<h1>` remains the page's own name.

### `schema_type`

Supported since 2.0 and, as of this writing, set by almost nobody — so most
Dash docs sites publish generic `WebPage` when a precisely-fitting type exists:

- a package's home page → `SoftwareApplication` or `SoftwareSourceCode`
- a documentation page → `TechArticle`

## Verifying

The one assertion worth adding to every deploy battery — it would have caught
every defect above:

```python
# Fetch the same URL twice and compare IDENTITY, not content.
for path in ("/", "/some-inner-page"):
    crawler = get(path, ua=GOOGLEBOT)
    browser = get(path, ua=CHROME)
    assert count_icon_links(crawler) == count_icon_links(browser)
    assert has_og_image(crawler) == has_og_image(browser)
    assert title_of(crawler).endswith(SITE_SHORT_NAME)
```

Plus:

1. Unconfigured is a no-op: no `rel="icon"`, no `og:image`, no `twitter:` in
   the crawler head.
2. `/favicon.ico` returns a redirect to a real image, never `<!DOCTYPE html`.
3. At least one declared icon is ≥192px.
4. `twitter:*` tags use `name=`, never `property=`.
5. Declared `og:image:width`/`height` match the real file's pixels.
