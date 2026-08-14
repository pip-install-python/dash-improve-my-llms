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

Unconfigured is a no-op: with no ``configure_seo()`` call the generated head
is byte-identical to 2.4.0.

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
        same_as: URLs for the JSON-LD ``sameAs`` — the other properties that
            are the same entity (GitHub, PyPI, sibling domains). This is how
            a family of domains tells a search engine it is one thing.
        root_icons: Answer ``/favicon.ico`` and the apple-touch paths by
            redirecting to a declared icon. Only takes effect when ``icons``
            is non-empty.
    """
    _config.icons = _normalize_icons(icons)
    _config.social_image = str(social_image or "").strip()
    _config.social_image_alt = str(social_image_alt or "").strip()
    _config.social_image_width = str(social_image_width or "").strip()
    _config.social_image_height = str(social_image_height or "").strip()
    _config.twitter_site = str(twitter_site or "").strip()
    _config.twitter_card = str(twitter_card or "summary_large_image").strip()
    _config.publisher = str(publisher or "").strip()
    _config.same_as = [str(u).strip() for u in (same_as or []) if str(u).strip()]
    _config.root_icons = bool(root_icons)


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


def reset() -> None:
    """Drop all configuration. Tests only."""
    global _config
    _config = SEOConfig()
