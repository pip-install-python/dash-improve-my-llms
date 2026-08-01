"""Site identity: one brand, every surface, verbatim.

The network standard says a site states what it is in the same words
everywhere an agent or a reader can reach. The failure this pins is silent —
nothing errors when a surface falls back to a default or goes stale. On THIS
host the live og:title read "dash-improve-my-llms 2.0" while 2.3.x was
current: a version number baked into a brand string, quietly wrong for four
releases. Hence the rule these tests encode: the version lives in the header
chip (read live from the package), never in the brand.

Library-satellite naming rules (subdomain_blueprint/STANDARD.md §1):
package name FIRST in the brand; "Pip Install Python" is the byline and
belongs in the description, never in the brand.
"""

from __future__ import annotations

import re

from _helpers import REPO_ROOT, meta
from lib.constants import (
    PAGE_TITLE_PREFIX,
    SITE_BRAND,
    SITE_DESCRIPTION,
    SITE_SHORT_NAME,
)

# Spelled out rather than imported, so that renaming the constant cannot
# silently rename the site. Changing the brand should require changing this
# line, deliberately.
EXPECTED_BRAND = "dash-improve-my-llms — crawler / SEO companion for Dash apps"

BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def test_brand_constant_is_the_agreed_identity():
    assert SITE_BRAND == EXPECTED_BRAND


def test_the_brand_carries_no_version_number():
    """ "dash-improve-my-llms 2.0" was live og:title well into 2.3.x."""
    assert not re.search(
        r"\d+\.\d+", SITE_BRAND
    ), f"{SITE_BRAND!r} bakes a version into the brand — it WILL go stale"


def test_the_package_name_leads_the_brand():
    """Library rule: package name FIRST. The byline stays out of the brand."""
    assert SITE_SHORT_NAME == "dash-improve-my-llms"
    assert SITE_BRAND.startswith(SITE_SHORT_NAME)
    assert "Pip Install Python" not in SITE_BRAND
    assert "Pip Install Python" in SITE_DESCRIPTION


def test_app_title_is_the_brand(site_app):
    """`Dash(title=...)` — the <title> and resolve_site_title's fallback."""
    assert site_app.title == EXPECTED_BRAND


def test_llms_index_h1_is_the_brand(site_client):
    """The single most-read line of this site, and the one nobody looks at."""
    response = site_client.get("/llms.txt", accept="text/markdown")
    assert response.ok
    assert response.text.splitlines()[0] == f"# {EXPECTED_BRAND}"


def test_llms_index_tagline_is_the_description(site_client):
    body = site_client.get("/llms.txt", accept="text/markdown").text
    assert f"> {SITE_DESCRIPTION}" in body


def test_home_prose_opens_unversioned():
    """pages/home.py's LLMS_DOC H1 said "2.0" — prose about the package may
    discuss releases, but the document must not TITLE itself with one."""
    text = (REPO_ROOT / "pages" / "home.py").read_text()
    match = re.search(r'LLMS_DOC = """\\\n(# .+)', text)
    assert match, "home LLMS_DOC no longer opens with an H1?"
    assert match.group(1) == "# dash-improve-my-llms"


def test_the_viewer_brand_chip_names_this_site(site_client):
    """The llms.txt viewer banner, rendered from the same resolve_site_title
    call as the H1 — a browser-Accept fetch of a page's llms.txt shows it."""
    page = site_client.get("/networks/llms.txt", accept=BROWSER_ACCEPT).text
    assert EXPECTED_BRAND in page, "the viewer banner does not name this site"


def test_no_surface_falls_back_to_a_generic_title():
    """The values resolve_site_title is designed to skip. If the brand were
    ever one of these, the package would silently publish something else."""
    from dash_improve_my_llms.handlers import _GENERIC_SITE_TITLES

    assert SITE_BRAND.strip().lower() not in _GENERIC_SITE_TITLES


def test_llms_package_floor_is_the_network_standard():
    """resolve_site_title arrived in 2.3.4; this repo hosts the source, so
    this documents the floor rather than defends it — until the site is ever
    pointed at a published wheel instead."""
    import dash_improve_my_llms as pkg

    parts = tuple(int(p) for p in pkg.__version__.split(".")[:3] if p.isdigit())
    assert parts >= (2, 3, 4)


# ---------------------------------------------------------------------------
# The per-page title — a share-card surface, not just a browser tab. Dash
# passes each page's `title` straight into og:title and twitter:title.
# ---------------------------------------------------------------------------


def test_the_page_title_prefix_is_this_site():
    assert PAGE_TITLE_PREFIX == f"{SITE_SHORT_NAME} | "


def test_the_short_name_cannot_drift_from_the_brand():
    assert SITE_BRAND.startswith(SITE_SHORT_NAME)


def test_the_home_share_card_headline_is_the_brand(site_client):
    """og:title and twitter:title on the site root, as a scraper reads them."""
    html = site_client.get("/").text
    for tag in ("og:title", "twitter:title"):
        found = meta(html, tag)
        assert found, f"no {tag} on the home page"
        for value in found:
            assert value == EXPECTED_BRAND, f"{tag}={value!r}"


def test_inner_pages_carry_the_prefixed_title(site_client):
    html = site_client.get("/analytics").text
    found = meta(html, "og:title")
    assert found and found[0].startswith(
        PAGE_TITLE_PREFIX
    ), f"og:title={found!r} does not open with {PAGE_TITLE_PREFIX!r}"


def test_no_identity_surface_still_says_two_point_oh(site_app):
    """The stale-version sweep, scoped to surfaces that PUBLISH identity.

    Prose that discusses the 2.0 release is legitimate (the /v200-features
    page exists to do exactly that); the <title>, the head block and the
    manifest are not prose.
    """
    assert "2.0" not in site_app.title
    assert "2.0" not in site_app.index_string, "the index_string still hard-codes a version"
    manifest = (REPO_ROOT / "assets" / "favicon" / "site.webmanifest").read_text()
    assert "2.0" not in manifest


def test_the_manifest_no_longer_wears_another_sites_name():
    """It shipped saying "2plot.dev — Dash Components Documentation"."""
    manifest = (REPO_ROOT / "assets" / "favicon" / "site.webmanifest").read_text()
    assert "Dash Components Documentation" not in manifest
