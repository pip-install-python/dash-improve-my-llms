"""Icons are found in the app's assets folder when nobody declares them.

`configure_seo()` shipped in 2.5 to give the crawler document the identity
this package strips off it. It is opt-in, and an opt-in fix to a SILENT
problem does not reach a fleet: measured across a 25-app network in August
2026, four apps called it and twenty-one did not — and all twenty-one had a
perfectly good favicon sitting in `assets/`. Nothing warned them, and nothing
could, because each app's own HTML was correct; the loss happened on the way
out, inside this package.

So: when no icons are declared, look for them. An explicit declaration always
wins; this only fills a vacuum.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dash_improve_my_llms import seo


@pytest.fixture(autouse=True)
def _clean():
    seo.reset()
    yield
    seo.reset()


def _app(folder, prefix="/assets/"):
    app = SimpleNamespace(config=SimpleNamespace(assets_folder=str(folder)))
    app.get_asset_url = lambda rel: prefix + rel
    return app


def _write(folder, *names):
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    return folder


# --------------------------------------------------------------- discovery --


def test_a_conventional_favicon_directory_is_found(tmp_path):
    _write(
        tmp_path / "favicon",
        "favicon.ico",
        "favicon-32x32.png",
        "android-chrome-192x192.png",
        "apple-touch-icon.png",
    )
    icons = seo.discover_icons(_app(tmp_path))
    assert [i["href"] for i in icons] == [
        "/assets/favicon/favicon.ico",
        "/assets/favicon/android-chrome-192x192.png",
        "/assets/favicon/favicon-32x32.png",
        "/assets/favicon/apple-touch-icon.png",
    ]


def test_a_lone_favicon_at_the_assets_root_is_found(tmp_path):
    _write(tmp_path, "favicon.ico")
    assert [i["href"] for i in seo.discover_icons(_app(tmp_path))] == ["/assets/favicon.ico"]


def test_a_dedicated_directory_beats_a_stray_root_copy(tmp_path):
    """Apps commonly keep both, and the loose one is usually the old one.
    Merging them declared rel="icon" twice, once pointing at a replaced file.
    """
    _write(tmp_path, "favicon.ico")
    _write(tmp_path / "favicon", "favicon.ico", "favicon-32x32.png")
    hrefs = [i["href"] for i in seo.discover_icons(_app(tmp_path))]
    assert hrefs == ["/assets/favicon/favicon.ico", "/assets/favicon/favicon-32x32.png"]
    assert "/assets/favicon.ico" not in hrefs


def test_unconventional_filenames_are_still_found(tmp_path):
    """A real app in the fleet ships favicon_areachart.ico; an exact-name
    match found nothing for it."""
    _write(tmp_path / "favicon", "favicon_areachart.ico", "apple-touch-icon_areachart.png")
    icons = seo.discover_icons(_app(tmp_path))
    assert len(icons) == 2


@pytest.mark.parametrize(
    "name,expected",
    [
        ("favicon-32x32.png", "32x32"),
        ("android-chrome-192x192.png", "192x192"),
        ("favicon-512.png", "512x512"),
        ("apple-touch-icon.png", "180x180"),
        ("favicon.ico", ""),  # multi-size: one number would be a lie
        ("favicon.png", ""),
    ],
)
def test_sizes_are_inferred_from_the_filename(name, expected):
    assert seo._sizes_from_name(name) == expected


@pytest.mark.parametrize(
    "name,rel",
    [
        ("favicon-32x32.png", "icon"),
        ("apple-touch-icon.png", "apple-touch-icon"),
        ("safari-pinned-tab.svg", "mask-icon"),
    ],
)
def test_rel_is_inferred_from_the_filename(name, rel):
    assert seo._rel_from_name(name) == rel


def test_biggest_square_comes_first_after_the_ico(tmp_path):
    """Order is what a UA walks, and it decides what the root paths resolve
    to. Google wants a big square; a 16x16 first is what renders blank."""
    _write(
        tmp_path / "favicon",
        "favicon.ico",
        "favicon-16x16.png",
        "android-chrome-512x512.png",
        "favicon-32x32.png",
        "apple-touch-icon.png",
    )
    order = [i["href"].rsplit("/", 1)[-1] for i in seo.discover_icons(_app(tmp_path))]
    assert order[0] == "favicon.ico"
    assert order[1] == "android-chrome-512x512.png"
    assert order[-1] == "apple-touch-icon.png"


def test_a_path_prefix_is_honoured(tmp_path):
    """An app mounted under requests_pathname_prefix must emit reachable
    hrefs, not root-relative ones."""
    _write(tmp_path / "favicon", "favicon.ico")
    icons = seo.discover_icons(_app(tmp_path, prefix="/dash/app1/assets/"))
    assert icons[0]["href"] == "/dash/app1/assets/favicon/favicon.ico"


# ----------------------------------------------------------- autoconfigure --


def test_discovery_fills_the_crawler_head(tmp_path):
    _write(tmp_path / "favicon", "favicon.ico", "android-chrome-192x192.png")
    assert seo.autoconfigure_icons(_app(tmp_path)) == 2
    tags = seo.icon_link_tags()
    assert 'rel="icon"' in tags
    assert 'sizes="192x192"' in tags


def test_an_explicit_declaration_always_wins(tmp_path):
    _write(tmp_path / "favicon", "favicon.ico", "android-chrome-192x192.png")
    seo.configure_seo(icons=["/assets/brand.png"])
    assert seo.autoconfigure_icons(_app(tmp_path)) == 0
    assert seo.get_seo().icons == [
        {"rel": "icon", "href": "/assets/brand.png", "type": "image/png"}
    ]


def test_discovered_icons_answer_the_well_known_root_paths(tmp_path):
    _write(tmp_path / "favicon", "favicon.ico", "apple-touch-icon.png")
    seo.autoconfigure_icons(_app(tmp_path))
    assert seo.root_icon_target("/favicon.ico") == "/assets/favicon/favicon.ico"
    assert seo.root_icon_target("/apple-touch-icon.png") == ("/assets/favicon/apple-touch-icon.png")


def test_an_app_with_no_icons_is_warned_not_crashed(tmp_path, caplog):
    """Silence is what let this persist for months across a whole network."""
    with caplog.at_level("WARNING"):
        assert seo.autoconfigure_icons(_app(tmp_path)) == 0
    assert any("no favicon found" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    "app",
    [
        SimpleNamespace(),  # not a Dash app
        SimpleNamespace(config=SimpleNamespace()),  # no assets_folder
        SimpleNamespace(config=SimpleNamespace(assets_folder=None)),
        SimpleNamespace(config=SimpleNamespace(assets_folder="/nope/nowhere")),
    ],
)
def test_discovery_never_breaks_boot(app):
    """A courtesy feature must not be why an application fails to start."""
    assert seo.discover_icons(app) == []
    assert seo.autoconfigure_icons(app) == 0


def test_unconfigured_still_means_unconfigured_without_an_app():
    """The 2.4-compatible promise: no call, no app, no output."""
    assert seo.icon_link_tags() == ""
    assert seo.get_seo().is_empty


# ------------------------------------------------------- hardening (2.6.0) --


def test_ui_sprites_are_never_adopted_as_favicons(tmp_path):
    """assets/icons/ is where apps keep UI sprites too. icon-arrow.png as the
    site's search-result icon is worse than no icon; only the digit-anchored
    web-manifest convention (icon-192.png, icon-512x512.png) qualifies."""
    _write(tmp_path / "icons", "icon-arrow.png", "icon-close.png", "icon-192.png")
    hrefs = [i["href"] for i in seo.discover_icons(_app(tmp_path))]
    assert hrefs == ["/assets/icons/icon-192.png"]


def test_a_later_unrelated_configure_seo_keeps_discovered_icons(tmp_path):
    """The ordering hazard: discovery runs inside add_llms_routes, and an app
    may call configure_seo(social_image=...) afterwards. Wiping the
    discovered icons because a later call configured an unrelated field is
    the same silent identity loss discovery exists to end."""
    _write(tmp_path / "favicon", "favicon.ico", "android-chrome-192x192.png")
    assert seo.autoconfigure_icons(_app(tmp_path)) == 2

    seo.configure_seo(social_image="https://cdn.example/card.png")
    assert len(seo.get_seo().icons) == 2, "an unrelated call erased discovered icons"
    assert seo.get_seo().social_image == "https://cdn.example/card.png"

    # An explicit declaration still wins — including an explicit empty list,
    # which is how an app deliberately opts out.
    seo.configure_seo(icons=["/assets/brand.png"])
    assert [i["href"] for i in seo.get_seo().icons] == ["/assets/brand.png"]
    seo.configure_seo(icons=[])
    assert seo.get_seo().icons == []


def test_an_explicit_declaration_is_still_wiped_by_omission():
    """Pre-2.6 wholesale-assignment semantics are preserved for EXPLICIT
    config: only the discovered set gets the survival guarantee."""
    seo.configure_seo(icons=["/assets/brand.png"])
    seo.configure_seo(social_image="https://cdn.example/card.png")
    assert seo.get_seo().icons == []


# --------------------------------------------------------- publisher logo --


def test_publisher_logo_falls_back_to_the_biggest_qualifying_icon(tmp_path):
    """A fleet that ships android-chrome-512x512.png already has a logo on
    disk. Google's floor is 112x112 and .ico is not a supported format."""
    _write(
        tmp_path / "favicon",
        "favicon.ico",
        "favicon-32x32.png",
        "android-chrome-192x192.png",
        "android-chrome-512x512.png",
    )
    seo.autoconfigure_icons(_app(tmp_path))
    assert seo.publisher_logo("https://example.com") == (
        "https://example.com/assets/favicon/android-chrome-512x512.png"
    )


def test_publisher_logo_requires_an_absolute_url():
    """Structured-data URLs must be crawlable; with no base to join onto, a
    root-relative candidate is dropped rather than emitted relative."""
    seo.configure_seo(icons=[{"href": "/assets/icon-512.png", "sizes": "512x512"}])
    assert seo.publisher_logo("") == ""
    assert seo.publisher_logo("https://example.com/") == ("https://example.com/assets/icon-512.png")


def test_an_explicit_logo_beats_the_icon_fallback():
    seo.configure_seo(
        icons=[{"href": "/assets/icon-512.png", "sizes": "512x512"}],
        logo="https://cdn.example/logo.png",
    )
    assert seo.publisher_logo("https://example.com") == "https://cdn.example/logo.png"


def test_small_icons_never_pose_as_a_logo():
    seo.configure_seo(
        icons=[
            "/assets/favicon.ico",
            {"href": "/assets/favicon-32x32.png", "sizes": "32x32"},
        ]
    )
    assert seo.publisher_logo("https://example.com") == ""


def test_the_crawler_document_carries_the_publisher_logo(tmp_path):
    """End to end: discovered icons -> JSON-LD publisher.logo, absolute."""
    from dash_improve_my_llms.html_generator import generate_static_page_html

    _write(tmp_path / "favicon", "favicon.ico", "android-chrome-512x512.png")
    seo.autoconfigure_icons(_app(tmp_path))
    seo.configure_seo(publisher="Example LLC")

    html = generate_static_page_html(
        page_path="/",
        page_metadata={"name": "Home", "description": "A demo."},
        all_pages=[{"path": "/", "name": "Home"}],
        app_config={"name": "Demo", "base_url": "https://example.com"},
    )
    assert '"publisher"' in html
    assert '"logo"' in html
    assert "https://example.com/assets/favicon/android-chrome-512x512.png" in html
    # And the discovered icons made it into the head at all — the wiring,
    # not just the selector.
    assert 'rel="icon"' in html


def test_an_svg_only_favicon_is_found(tmp_path):
    """Two real fleet apps ship favicon.svg + apple-touch-icon.png and
    nothing else. The SVG is the identity; missing it left them with only
    the apple-touch icon."""
    _write(tmp_path, "favicon.svg", "apple-touch-icon.png")
    icons = seo.discover_icons(_app(tmp_path))
    hrefs = [i["href"] for i in icons]
    assert "/assets/favicon.svg" in hrefs
    assert [i for i in icons if i["href"].endswith(".svg")][0]["rel"] == "icon"
