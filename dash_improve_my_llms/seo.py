"""Site-level search metadata — the half of the head a crawler was missing.

The package serves crawlers a generated document (``html_generator``) instead
of the application's own HTML. That document carried the page's *content*
signals — title, description, canonical, JSON-LD — but none of its *identity*
signals: no ``<link rel="icon">``, no ``og:image``, no ``twitter:*``. Measured
across a live 18-host network in August 2026: browsers received four to seven
icon links, Googlebot received zero on every host, and search results showed
the generic globe. Sites that served crawlers the same document a browser gets
showed their real mark.

The rule this module exists to enforce:

    Content may differ between the crawler document and the browser document.
    Identity may not.

Identity is site-level, not per-page, so it lives here rather than on every
``register_page_metadata`` call — one declaration, every crawler surface.
Per-page overrides still win where they make sense (``og_image`` on a page
with its own card).

Unconfigured falls back to discovery (2.6.0): with no ``configure_seo()``
call, ``add_llms_routes`` looks for icons in the app's own assets folder and
adopts what it finds — see ``discover_icons``. An app with no assets icons
either still gets the 2.4.0-identical head, plus one warning naming what a
blank identity costs.

    configure_seo(
        icons=["/assets/favicon/favicon.ico",
               {"href": "/assets/favicon/icon-192.png", "sizes": "192x192"},
               {"href": "/assets/favicon/apple-touch-icon.png",
                "rel": "apple-touch-icon", "sizes": "180x180"}],
        social_image="https://cdn.example.com/card.png",
        publisher="Example LLC",
        same_as=["https://github.com/example", "https://pypi.org/project/x"],
    )
"""

from __future__ import annotations

import html as _stdlib_html
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Google reads the icon from the home page of the document it CRAWLS, and
# falls back to these well-known root paths when it finds no link. Dash's page
# catch-all answers all three with the app shell (200 text/html) unless
# something claims them first — an actively poisoned fallback, not a missing
# one. `root_icon_target` maps each to a declared icon.
ROOT_ICON_PATHS = (
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
)

_EXT_TYPES = {
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _guess_type(href: str) -> str:
    lowered = href.lower().split("?")[0]
    for ext, ctype in _EXT_TYPES.items():
        if lowered.endswith(ext):
            return ctype
    return ""


def _icon_area(icon: Dict[str, str]) -> int:
    """Pixel area from a `sizes` string, 0 when absent or unparseable.

    Used only for ordering (which icon a root path should point at), never
    for output — an icon with no `sizes` is still emitted verbatim.
    """
    sizes = (icon.get("sizes") or "").lower()
    best = 0
    for token in sizes.replace(",", " ").split():
        if "x" not in token:
            continue
        w, _, h = token.partition("x")
        try:
            best = max(best, int(w) * int(h))
        except ValueError:
            continue
    return best


class SEOConfig:
    """Site-level identity for the crawler-facing document."""

    __slots__ = (
        "icons",
        "social_image",
        "social_image_alt",
        "social_image_width",
        "social_image_height",
        "twitter_site",
        "twitter_card",
        "publisher",
        "same_as",
        "root_icons",
        "logo",
        "icons_discovered",
    )

    def __init__(self) -> None:
        self.icons: List[Dict[str, str]] = []
        self.social_image: str = ""
        self.social_image_alt: str = ""
        self.social_image_width: str = ""
        self.social_image_height: str = ""
        self.twitter_site: str = ""
        self.twitter_card: str = "summary_large_image"
        self.publisher: str = ""
        self.same_as: List[str] = []
        self.root_icons: bool = True
        self.logo: str = ""
        # True when `icons` came from discover_icons() rather than an explicit
        # configure_seo(icons=...). Provenance matters: an explicit declaration
        # may overwrite a discovered set, but a configure_seo() call that
        # never mentioned icons must not silently erase it.
        self.icons_discovered: bool = False

    @property
    def is_empty(self) -> bool:
        return not (self.icons or self.social_image or self.publisher or self.same_as)


_config = SEOConfig()


def _normalize_icons(icons: Optional[Sequence[Any]]) -> List[Dict[str, str]]:
    """Accept strings or dicts; emit dicts with at least `rel` and `href`.

    A bad entry is skipped with a warning rather than raising: a malformed
    icon must not stop an application from booting.
    """
    out: List[Dict[str, str]] = []
    for raw in icons or []:
        if isinstance(raw, str):
            entry: Dict[str, Any] = {"href": raw}
        elif isinstance(raw, dict):
            entry = dict(raw)
        else:
            logger.warning("configure_seo: ignoring icon entry %r", raw)
            continue

        href = str(entry.get("href") or "").strip()
        if not href:
            logger.warning("configure_seo: ignoring icon with no href: %r", raw)
            continue

        icon = {"rel": str(entry.get("rel") or "icon"), "href": href}
        sizes = str(entry.get("sizes") or "").strip()
        if sizes:
            icon["sizes"] = sizes
        ctype = str(entry.get("type") or "").strip() or _guess_type(href)
        if ctype:
            icon["type"] = ctype
        out.append(icon)
    return out


def configure_seo(
    *,
    icons: Optional[Sequence[Any]] = None,
    social_image: str = "",
    social_image_alt: str = "",
    social_image_width: Any = "",
    social_image_height: Any = "",
    twitter_site: str = "",
    twitter_card: str = "summary_large_image",
    publisher: str = "",
    logo: str = "",
    same_as: Optional[Sequence[str]] = None,
    root_icons: bool = True,
) -> None:
    """Declare the site's identity for every crawler-facing surface.

    Args:
        icons: Icon declarations, each a URL string or a dict with
            ``href`` and optionally ``rel``/``sizes``/``type``. Emitted as
            ``<link>`` elements in the crawler head, and used to answer the
            well-known root paths. Include at least one ≥192px square: it is
            what Google prefers, and what an installable app needs.
        social_image: Default ``og:image`` / ``twitter:image``. Host it off
            the app (a CDN) — an app-served card races a cold container at
            unfurl time and the platform caches the miss.
        social_image_alt: Alt text for that image.
        social_image_width / social_image_height: Declared dimensions. They
            MUST match the real file; a wrong declaration is worse than none.
        twitter_site: ``@handle`` for ``twitter:site``.
        twitter_card: ``summary_large_image`` (default) or ``summary``.
        publisher: Organization name for the JSON-LD ``publisher``.
        logo: URL of the organization's logo for the JSON-LD
            ``publisher.logo`` — what Google shows next to the site in
            branded results. Absolute, or root-relative when a base URL is
            configured; ≥112x112px per Google's requirement. When omitted,
            the largest declared raster icon of at least that size is used,
            so a discovered android-chrome-512x512.png serves double duty.
        same_as: URLs for the JSON-LD ``sameAs`` — the other properties that
            are the same entity (GitHub, PyPI, sibling domains). This is how
            a family of domains tells a search engine it is one thing.
        root_icons: Answer ``/favicon.ico`` and the apple-touch paths by
            redirecting to a declared icon. Only takes effect when ``icons``
            is non-empty.
    """
    # icons=None on a config that HOLDS A DISCOVERED SET keeps it: the app
    # never declared icons, so this call cannot be revoking a declaration —
    # wiping identity because a later call configured an unrelated field is
    # the same silent loss discovery exists to end. An explicit list (even
    # []) always wins and ends the discovered provenance.
    if icons is not None or not _config.icons_discovered:
        _config.icons = _normalize_icons(icons)
        _config.icons_discovered = False
    _config.social_image = str(social_image or "").strip()
    _config.social_image_alt = str(social_image_alt or "").strip()
    _config.social_image_width = str(social_image_width or "").strip()
    _config.social_image_height = str(social_image_height or "").strip()
    _config.twitter_site = str(twitter_site or "").strip()
    _config.twitter_card = str(twitter_card or "summary_large_image").strip()
    _config.publisher = str(publisher or "").strip()
    _config.logo = str(logo or "").strip()
    _config.same_as = [str(u).strip() for u in (same_as or []) if str(u).strip()]
    _config.root_icons = bool(root_icons)


# ---------------------------------------------------------------------------
# Auto-discovery.
#
# configure_seo() is opt-in, and an opt-in fix to a SILENT problem does not
# reach a fleet. Measured across a 25-app network in August 2026: four apps
# called it, twenty-one did not, and every one of the twenty-one had a
# perfectly good favicon sitting in its assets folder. Nothing warned them.
# Nothing could: each app's own HTML was correct the whole time, so the failure
# was invisible from a browser and surfaced only as a blank icon in a search
# result, weeks later.
#
# This package is why the icon goes missing — it serves crawlers a generated
# document INSTEAD of the app's own head. A package that discards an app's head
# owes it to that app to carry the identity forward. So when no icons are
# declared, go and look: the files are on disk under a handful of conventional
# names, and Dash already knows where its assets folder is.
#
# An explicit configure_seo(icons=...) always wins. This only fills a vacuum.
# ---------------------------------------------------------------------------

# Where favicon sets actually live, MOST SPECIFIC FIRST. A dedicated favicon
# directory is the curated set; the assets root is the fallback and comes last,
# because an app that has both usually has a stale loose copy at the root and
# emitting both invites a user agent to pick the old one.
_ICON_SUBDIRS = ("favicon", "favicons", "favicon_io", "icons", "img", "")

# Globs, not exact names: real apps ship favicon_areachart.ico and
# apple-touch-icon_barchart.png. An exact-name list found nothing in those.
_ICON_PATTERNS = (
    "favicon*.ico",
    "favicon*.png",
    # Two real fleet apps ship ONLY an SVG favicon (plus an apple-touch png).
    # Google parses SVG favicons; skipping them left those apps' identity on
    # the apple-touch icon alone.
    "favicon*.svg",
    "android-chrome-*.png",
    "apple-touch-icon*.png",
    # Digit-anchored on purpose: the web-manifest convention is icon-192.png /
    # icon-512x512.png. A bare icon-*.png would adopt an app's UI sprites
    # (icon-arrow.png, icon-close.png live in assets/icons/ too) as favicons —
    # and Google picks its search-result icon from what we declare here.
    "icon-[0-9]*.png",
    "mask-icon.svg",
    "safari-pinned-tab.svg",
)

# The size Apple asks for and every generator writes, though the filename
# almost never says so.
_APPLE_TOUCH_DEFAULT = "180x180"

_SIZE_PAIR = re.compile(r"(\d{2,4})x(\d{2,4})")
_SIZE_SINGLE = re.compile(r"[-_](\d{2,4})(?:\.[a-z0-9]+)?$")


def _sizes_from_name(name: str) -> str:
    """`sizes` inferred from the filename, or "" when it says nothing.

    `favicon-32x32.png` -> 32x32; `favicon-192.png` -> 192x192. A multi-size
    `.ico` deliberately gets nothing: declaring one size for a file holding
    three would be a lie, and `sizes` is optional.
    """
    lowered = name.lower()
    pair = _SIZE_PAIR.search(lowered)
    if pair:
        return "{0}x{1}".format(pair.group(1), pair.group(2))
    if lowered.endswith(".ico"):
        return ""
    single = _SIZE_SINGLE.search(lowered)
    if single:
        return "{0}x{0}".format(single.group(1))
    if "apple-touch-icon" in lowered:
        return _APPLE_TOUCH_DEFAULT
    return ""


def _rel_from_name(name: str) -> str:
    lowered = name.lower()
    if "apple-touch-icon" in lowered:
        return "apple-touch-icon"
    if "mask-icon" in lowered or "safari-pinned-tab" in lowered:
        return "mask-icon"
    return "icon"


def _discovery_sort_key(icon: Dict[str, str]):
    """.ico first (the legacy probe), then biggest square, apple-touch last.

    The order a user agent walks when choosing one, and it decides which icon
    the well-known root paths resolve to.
    """
    rel = icon.get("rel", "icon")
    is_ico = icon.get("href", "").lower().endswith(".ico")
    return (rel == "mask-icon", rel == "apple-touch-icon", not is_ico, -_icon_area(icon))


def discover_icons(app: Any) -> List[Dict[str, str]]:
    """Icon declarations found in the app's own assets folder.

    Returns [] for anything unexpected — no folder, an odd Dash subclass, a
    permission error. Discovery is a courtesy; it must never be the reason an
    application fails to boot.
    """
    try:
        from pathlib import Path

        folder = getattr(getattr(app, "config", None), "assets_folder", None)
        if not folder:
            return []
        root = Path(str(folder))
        if not root.is_dir():
            return []

        # The FIRST directory holding any icons is the set. Not the union of
        # every directory: apps commonly keep assets/favicon/favicon.ico and a
        # loose assets/favicon.ico, and merging them declared the same rel
        # twice — once pointing at a file the app had already replaced.
        for sub in _ICON_SUBDIRS:
            directory = root / sub if sub else root
            if not directory.is_dir():
                continue
            hits: Dict[str, Dict[str, str]] = {}
            for pattern in _ICON_PATTERNS:
                for path in sorted(directory.glob(pattern)):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(root).as_posix()
                    if relative in hits:
                        continue
                    # get_asset_url, so an app mounted under a
                    # requests_pathname_prefix still emits a reachable href.
                    try:
                        href = app.get_asset_url(relative)
                    except Exception:  # noqa: BLE001
                        href = "/assets/" + relative
                    entry = {"rel": _rel_from_name(path.name), "href": href}
                    sizes = _sizes_from_name(path.name)
                    if sizes:
                        entry["sizes"] = sizes
                    hits[relative] = entry
            if hits:
                return sorted(hits.values(), key=_discovery_sort_key)
        return []
    except Exception:  # noqa: BLE001
        logger.debug("icon auto-discovery failed", exc_info=True)
        return []


def autoconfigure_icons(app: Any) -> int:
    """Adopt assets-folder icons when the app declared none.

    Returns how many were adopted (0 when the app declared its own, or when
    nothing was found). Logged either way at INFO — a silent default is what
    made the original problem so durable.
    """
    if _config.icons:
        return 0
    found = _normalize_icons(discover_icons(app))
    if not found:
        logger.warning(
            "dash-improve-my-llms: no favicon found in the assets folder, so "
            "the document served to crawlers will declare none and search "
            "engines will show a blank icon for this site. Add one under "
            "assets/favicon/ or call configure_seo(icons=[...])."
        )
        return 0
    _config.icons = found
    _config.icons_discovered = True
    logger.info(
        "dash-improve-my-llms: adopted %d favicon(s) from the assets folder "
        "for the crawler document (%s). configure_seo(icons=[...]) overrides.",
        len(found),
        ", ".join(i["href"] for i in found[:3]),
    )
    return len(found)


def get_seo() -> SEOConfig:
    return _config


def is_configured() -> bool:
    return not _config.is_empty


def icon_link_tags(indent: str = "    ") -> str:
    """The `<link rel="icon">` block for the crawler head, or "" when unset."""
    lines = []
    for icon in _config.icons:
        attrs = [f'rel="{_stdlib_html.escape(icon["rel"], quote=True)}"']
        if icon.get("type"):
            attrs.append(f'type="{_stdlib_html.escape(icon["type"], quote=True)}"')
        if icon.get("sizes"):
            attrs.append(f'sizes="{_stdlib_html.escape(icon["sizes"], quote=True)}"')
        attrs.append(f'href="{_stdlib_html.escape(icon["href"], quote=True)}"')
        lines.append(f"{indent}<link {' '.join(attrs)}>")
    return "\n".join(lines)


def root_icon_target(path: str) -> Optional[str]:
    """Which declared icon a well-known root path should redirect to.

    Redirect rather than serve: the package has no business reading an
    application's asset folder or guessing where its files live, and every
    consumer of these paths (browsers, Google, feed readers) follows a
    redirect. Returns None when unconfigured, which the adapters turn into a
    404 — a deliberate change from the app shell Dash's catch-all served:
    a crawler that gets 404 correctly concludes "no icon" instead of
    parsing HTML where an image belongs.
    """
    if not _config.root_icons or not _config.icons:
        return None

    if path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
        apple = [i for i in _config.icons if "apple" in i["rel"].lower()]
        if apple:
            return apple[0]["href"]
        pngs = [i for i in _config.icons if i.get("type") == "image/png"]
        if pngs:
            return max(pngs, key=_icon_area)["href"]
        return None

    if path == "/favicon.ico":
        ico = [i for i in _config.icons if i.get("type") == "image/x-icon"]
        if ico:
            return ico[0]["href"]
        # No .ico declared: send them to the largest raster icon. Google and
        # every current browser accept a PNG at this path; the extension is
        # a historical name, not a content-type contract.
        raster = [i for i in _config.icons if i.get("type") not in ("image/svg+xml", "")]
        if raster:
            return max(raster, key=_icon_area)["href"]
        return _config.icons[0]["href"]

    return None


# Google's floor for an Organization logo. Anything smaller is ignored by
# the systems the field exists for, so offering one would be noise.
_LOGO_MIN_AREA = 112 * 112


def publisher_logo(base_url: str = "") -> str:
    """The absolute URL for JSON-LD ``publisher.logo``, or "".

    An explicit ``configure_seo(logo=...)`` wins; otherwise the largest
    declared raster icon of at least 112x112 (Google's minimum) stands in —
    a fleet that ships android-chrome-512x512.png already has a perfectly
    good logo on disk, and the same reasoning as icon discovery applies.

    Structured-data URLs must be absolute to be crawlable, so a
    root-relative candidate is joined onto ``base_url`` — and dropped when
    there is no base to join it to. `.ico` never qualifies: it is not in
    Google's supported logo formats.
    """

    def _absolute(href: str) -> str:
        if href.startswith(("http://", "https://")):
            return href
        if href.startswith("/") and base_url:
            return base_url.rstrip("/") + href
        return ""

    if _config.logo:
        return _absolute(_config.logo)

    candidates = [
        icon
        for icon in _config.icons
        if icon.get("type") not in ("image/x-icon", "") and _icon_area(icon) >= _LOGO_MIN_AREA
    ]
    if not candidates:
        return ""
    return _absolute(max(candidates, key=_icon_area)["href"])


def reset() -> None:
    """Drop all configuration. Tests only."""
    global _config
    _config = SEOConfig()
