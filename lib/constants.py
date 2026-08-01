"""Site identity and social-card constants for llms.2plot.dev.

SITE CODE ONLY — this module belongs to the docs site (app.py + pages/), not
to the dash_improve_my_llms package. pyproject.toml enumerates its packages
explicitly (`packages = ["dash_improve_my_llms"]`), so nothing in lib/ can
leak into the wheel.

One brand, every surface. The constants here reach:

  Dash(title=SITE_BRAND)                 -> <title>, resolve_site_title fallback
  register_page_metadata(path="/",
      name=SITE_BRAND)                   -> /llms.txt H1 and the viewer brand chip
  register_page(image_url=OG_IMAGE_URL,
      description=...)                   -> og:image / twitter:image on EVERY page
  app.index_string                       -> the tags Dash does not emit itself

Network rule (subdomain_blueprint/STANDARD.md §1): a library satellite puts
the package name FIRST in the brand. "Pip Install Python" is the byline and
belongs in the description, never in the brand. And no version number in the
brand — the live site served og:title "dash-improve-my-llms 2.0" long after
2.3.x shipped, which is exactly how a baked-in version goes stale.

The tagline is the repo's own (README.md header / app header strip), not an
invention: "Crawler / SEO companion for Dash apps".
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Brand
# --------------------------------------------------------------------------

SITE_BRAND = "dash-improve-my-llms — crawler / SEO companion for Dash apps"

# The brand without its tagline: page-title prefixes, the manifest short
# name, anywhere the full string would be unwieldy.
SITE_SHORT_NAME = "dash-improve-my-llms"

# README.md's own headline sentence, with the package name and the byline —
# both belong here, in the description, rather than in the brand.
SITE_DESCRIPTION = (
    "Make a Plotly Dash app readable to search engines, crawlers and AI "
    "agents — without giving up the interactive app. dash-improve-my-llms "
    "is maintained by Pip Install Python LLC."
)

# Dash passes each page's `title` straight into og:title / twitter:title, so
# this prefix is the headline of every unfurl the inner pages produce.
PAGE_TITLE_PREFIX = f"{SITE_SHORT_NAME} | "

# --------------------------------------------------------------------------
# Origin
# --------------------------------------------------------------------------

# BASE_URL is a required NAME on the 2plot network — shared scripts and tests
# import lib.constants.BASE_URL. app.py assigns it to app._base_url, which
# drives sitemap.xml, robots.txt, absolute llms.txt URLs and the per-page
# <link rel="canonical">.
DEFAULT_BASE_URL = "https://llms.2plot.dev"
BASE_URL = os.environ.get("APP_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

# --------------------------------------------------------------------------
# The social card
# --------------------------------------------------------------------------

# The card lives on the network CDN, NOT on this app. A card the app serves
# is fetched by the scraper at unfurl time; on a cold free-tier container
# that request times out, the preview renders blank once, and the platform
# caches the miss. The CDN has no cold start.
#
# Regenerate with scripts/make_social_card.py; upload by hand to the CDN and
# verify 200 + IHDR 1200x630 BEFORE deploying code that points at it.
OG_IMAGE_URL = "https://cdn.2plot.ai/github_assets/llms.2plot.dev.png"
OG_IMAGE_WIDTH = 1200
OG_IMAGE_HEIGHT = 630
OG_IMAGE_TYPE = "image/png"
OG_IMAGE_ALT = SITE_BRAND

# --------------------------------------------------------------------------
# Internal traffic
# --------------------------------------------------------------------------

# 2plot network machinery talking to itself — hub sweeps, smoke batteries,
# sibling satellites. Trackers drop UAs carrying the token AT WRITE TIME,
# before bot classification, so internal probes never inflate analytics.
INTERNAL_UA_TOKEN = "2plot-internal"
INTERNAL_UA = "2plot-internal/1.0 (+https://2plot.ai/docs/satellite-analytics)"


def internal_ua(caller: str = "") -> str:
    """``INTERNAL_UA`` with a caller suffix, e.g. ``"smoke-test"``.

    Every outbound call this app makes on its own behalf should send this,
    so the far side can apply the same write-time drop rule.
    """
    return f"{INTERNAL_UA} {caller}" if caller else INTERNAL_UA
