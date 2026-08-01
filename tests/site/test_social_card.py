"""The social card and the installable-app surfaces of llms.2plot.dev.

Ported from dash-documentation-boilerplate (the network's template). Both
things tested here fail silently and fail OUTSIDE the app — nobody sees their
own unfurls, and no browser explains why it declined to offer an install.

What this host actually shipped (measured live 2026-08-01, the last host on
the network with the bug): empty `og:image content=""`, empty `twitter:image`
and `twitter:description`, plus a static description that duplicated Dash's
per-page one. Root cause: not one of the eight register_page calls passed
`image_url=`/`description=`, so Dash's `_page_meta_tags` emitted empty tags —
and the empty tag, later in document order, is the one a scraper honours.

Note where each tag comes from, because it decides which block of app.py to
open when one of these fails: `og:image`, `twitter:image` and the rest of the
`twitter:*` set are DASH's (per page, from register_page); `og:site_name`,
`og:url`, the `og:image:*` auxiliaries and the icon links are the
index_string's. dash-improve-my-llms adds a third set, but only on the
prerender path, which social scrapers do not take — its bot list has
`facebookbot` (Meta's AI training crawler), not `facebookexternalhit` (the
link-preview fetcher).
"""

from __future__ import annotations

import json
import re
import struct

import pytest

from _helpers import REPO_ROOT, meta, visible
from lib.constants import (
    OG_IMAGE_ALT,
    OG_IMAGE_HEIGHT,
    OG_IMAGE_TYPE,
    OG_IMAGE_URL,
    OG_IMAGE_WIDTH,
    SITE_BRAND,
)

MANIFEST = REPO_ROOT / "assets" / "favicon" / "site.webmanifest"
LOCAL_CARD = REPO_ROOT / "build" / "social-cards" / "llms.2plot.dev.png"


# ------------------------------------------------------------- the og image --


def test_the_og_image_is_never_empty(site_client, site_page_paths):
    """One register_page without image_url= and this fails — deliberately."""
    for path in site_page_paths:
        images = meta(site_client.get(path).text, "og:image")
        assert images, f"{path} declares no og:image at all"
        assert all(
            src.strip() for src in images
        ), f"{path} serves an EMPTY og:image {images} — the card renders blank"


def test_the_twitter_surface_is_never_empty(site_client, site_page_paths):
    """The other two tags measured empty on the live host."""
    for path in site_page_paths:
        html = site_client.get(path).text
        for tag in ("twitter:image", "twitter:description"):
            values = meta(html, tag)
            assert values, f"{path} declares no {tag}"
            assert all(v.strip() for v in values), f"{path} serves an EMPTY {tag}"


def test_the_image_is_declared_exactly_once(site_client, site_page_paths):
    """The duplicate-tag regression, and why the index_string stops at alt."""
    for path in site_page_paths:
        html = site_client.get(path).text
        assert len(meta(html, "og:image")) == 1, (
            f"{path} has {meta(html, 'og:image')} — a scraper picks one, and "
            "it will not be the one you meant"
        )
        assert len(meta(html, "twitter:image")) == 1


def test_the_image_is_not_an_svg(site_client):
    """SVG is rejected by Facebook, Twitter/X, LinkedIn and Slack alike.

    Dash also INFERS an og:image from the assets folder when image_url= is
    omitted, so this is one missing kwarg away from returning.
    """
    for prop in ("og:image", "twitter:image"):
        for src in meta(site_client.get("/").text, prop):
            assert not src.lower().endswith(".svg"), f"{prop} is an SVG: {src}"


def test_the_image_is_absolute_and_matches_the_constant(site_client):
    for prop in ("og:image", "twitter:image"):
        values = meta(site_client.get("/").text, prop)
        assert values, f"no {prop} on the home page"
        for src in values:
            assert src.startswith("http"), f"{prop}={src!r} is not absolute"
            assert src == OG_IMAGE_URL


def test_the_image_is_hosted_off_the_app():
    """The card must be on the CDN, not served by this app.

    A card the app serves is fetched by the scraper at unfurl time; on a cold
    free-tier Render container that request lands mid-wake and times out, the
    preview renders blank ONCE, and the platform caches the miss. That the
    CDN URL resolves is deliberately not checked here — the live battery
    checks the real pixels after deploy, and an offline suite must not depend
    on Cloudflare being up.
    """
    assert OG_IMAGE_URL.startswith(
        "https://cdn.2plot.ai/github_assets/"
    ), f"{OG_IMAGE_URL} is not on the network CDN"
    assert "/assets/" not in OG_IMAGE_URL, "the app is serving its own card"


def test_the_auxiliary_image_tags_match_the_constants(site_client):
    """A declared width/height that disagrees with the file is worse than
    declaring none — the platform reserves the wrong box and crops into it."""
    html = site_client.get("/").text
    assert meta(html, "og:image:width") == [str(OG_IMAGE_WIDTH)]
    assert meta(html, "og:image:height") == [str(OG_IMAGE_HEIGHT)]
    assert meta(html, "og:image:alt") == [OG_IMAGE_ALT]
    assert meta(html, "og:image:type") == [OG_IMAGE_TYPE]
    assert meta(html, "og:image:secure_url") == [
        OG_IMAGE_URL
    ], "secure_url must be the same file as og:image, not a stale copy"


def test_the_declared_ratio_suits_a_large_image_card():
    """`summary_large_image` wants roughly 1.91:1."""
    ratio = OG_IMAGE_WIDTH / OG_IMAGE_HEIGHT
    assert 1.7 <= ratio <= 2.05, f"{OG_IMAGE_WIDTH}x{OG_IMAGE_HEIGHT} is {ratio:.2f}:1"


def test_the_twitter_card_is_a_large_image(site_client):
    assert meta(site_client.get("/").text, "twitter:card") == ["summary_large_image"]


@pytest.mark.skipif(not LOCAL_CARD.exists(), reason="no local card render (build/ is gitignored)")
def test_the_local_card_render_matches_the_declared_dimensions():
    """Raw bytes, never a text decode — errors='replace' destroys the IHDR."""
    data = LOCAL_CARD.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "build/social-cards card is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (
        OG_IMAGE_WIDTH,
        OG_IMAGE_HEIGHT,
    ), f"card is {width}x{height}, constants say {OG_IMAGE_WIDTH}x{OG_IMAGE_HEIGHT}"


# ------------------------------------------------- the index_string contract --


def test_no_meta_tag_dash_emits_is_also_declared_statically(site_client):
    """The rule the head block in app.py is built on.

    Dash emits all of these per page from register_page. A static copy makes
    two of each, the static one describes the SITE where Dash's describes the
    PAGE, and the LAST tag wins with scrapers. This host's static description
    duplicated Dash's until this pass.
    """
    html = site_client.get("/").text
    for tag in (
        "description",
        "og:type",
        "og:title",
        "og:description",
        "og:image",
        "twitter:card",
        "twitter:url",
        "twitter:title",
        "twitter:description",
        "twitter:image",
    ):
        found = meta(html, tag)
        assert len(found) <= 1, f"{tag} is declared {len(found)} times: {found}"


def test_the_tags_dash_omits_are_declared_here(site_client):
    """The other half of the rule — do not delete these thinking Dash covers them."""
    html = site_client.get("/").text
    for tag in (
        "og:site_name",
        "og:url",
        "og:image:alt",
        "twitter:image:alt",
        "og:image:secure_url",
        "og:image:type",
        "og:image:width",
        "og:image:height",
    ):
        assert meta(html, tag), f"{tag} is missing and Dash does not emit it"


def test_no_dash_placeholder_is_named_inside_a_comment(site_app):
    """Dash resolves its percent-brace tokens by plain string replacement over
    the whole index_string, comments included — a placeholder spelled inside a
    comment emits its block TWICE. That was dash-email's 'two empty og:image
    tags', invisible in a browser and fully visible to scrapers."""
    index = site_app.index_string
    for comment in re.findall(r"<!--.*?-->", index, flags=re.S):
        hits = re.findall(r"\{%\w+%\}", comment)
        assert not hits, f"placeholder {hits} named inside an HTML comment"


def test_the_index_string_is_still_wired_in(site_app):
    """The static head looks removable and is not: dash-improve-my-llms's own
    OG injection runs only on the prerender path, which social scrapers do
    not take. Deleting it kills every unfurl, the icons and the manifest."""
    index = site_app.index_string
    for placeholder in (
        "{%metas%}",
        "{%title%}",
        "{%favicon%}",
        "{%css%}",
        "{%app_entry%}",
        "{%config%}",
        "{%scripts%}",
        "{%renderer%}",
    ):
        assert placeholder in index, f"{placeholder} missing from index_string"
    assert index.startswith("<!DOCTYPE html>")


# ------------------------------------------------------------- the manifest --


def test_the_manifest_is_linked_and_served(site_client):
    html = visible(site_client.get("/").text)
    assert 'rel="manifest"' in html, "no manifest link — no install prompt"
    match = re.search(r'<link[^>]+rel="manifest"[^>]+href="([^"]+)"', html)
    assert match
    assert site_client.get(match.group(1)).ok, "the manifest link 404s"


def test_the_manifest_describes_THIS_site():
    """It shipped naming "2plot.dev — Dash Components Documentation", copied
    in from another repo. An installed app takes its home-screen label from
    `short_name`, so a wrong string here becomes a permanent icon label."""
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["name"] == SITE_BRAND
    assert "2plot.dev —" not in manifest["short_name"]
    assert "Dash Components Documentation" not in manifest["description"]


def test_the_manifest_is_installable():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["name"].strip(), "empty name — no browser will offer install"
    assert manifest["short_name"].strip(), "empty short_name"
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"


def test_every_manifest_icon_resolves(site_client):
    manifest = json.loads(MANIFEST.read_text())
    icons = manifest.get("icons") or []
    assert icons, "the manifest declares no icons"
    for icon in icons:
        assert site_client.get(icon["src"]).ok, f"manifest icon {icon['src']} 404s"
    assert any(i.get("sizes") == "192x192" for i in icons)
    assert any(i.get("sizes") == "512x512" for i in icons)


def test_the_apple_touch_icon_is_declared_and_resolves(site_client):
    """iOS ignores the manifest and uses this for Add to Home Screen."""
    html = visible(site_client.get("/").text)
    match = re.search(r'<link[^>]*rel="apple-touch-icon"[^>]*href="([^"]+)"', html)
    assert match, "no apple-touch-icon link"
    assert site_client.get(match.group(1)).ok, f"{match.group(1)} does not resolve"


def test_the_theme_colour_agrees_with_the_manifest(site_client):
    """A mismatch is one colour in the browser chrome, another on the splash."""
    manifest = json.loads(MANIFEST.read_text())
    declared = meta(site_client.get("/").text, "theme-color")
    assert declared, "no theme-color"
    assert declared[0].lower() == manifest["theme_color"].lower()


def test_every_asset_the_head_references_resolves(site_client):
    """The half-landed-commit guard: the boilerplate once shipped a template
    pointing at /assets/favicon/ while the icon set sat UNTRACKED in git —
    production 404'd the whole installable-app surface while every local boot
    looked perfect. A checkout is what CI tests, so this fails there the
    moment a referenced asset is not committed."""
    html = visible(site_client.get("/").text)
    referenced = sorted(set(re.findall(r'(?:href|content|src)="(/assets/[^"]+)"', html)))
    assert referenced, "no /assets/ references found — did the head change?"

    missing = [ref for ref in referenced if not site_client.get(ref).ok]
    assert missing == [], (
        f"the document head references assets that do not resolve: {missing}. "
        "If they exist on disk, they are untracked — the deploy builds from git."
    )
