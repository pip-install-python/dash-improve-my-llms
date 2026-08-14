"""
The universal prerender's head contract: resolve titles the same way the
crawler document does, and never fight the application's own head.

These exist because the 2.5.0 Tier-B rollout found the browser-facing path
carrying the exact defect 2.5.0 fixed for crawlers: Dash Pages served
"site | page" and the prerender rewrote it to the bare page name, then
injected a second og:title beside the application's own.
"""

from __future__ import annotations

from dash_improve_my_llms.prerender import inject_prerender


def _document(title: str, head_extra: str = "") -> str:
    return (
        "<!DOCTYPE html><html><head>"
        f"<title>{title}</title>{head_extra}"
        "</head><body>"
        '<div id="react-entry-point"><div class="_dash-loading">Loading...</div></div>'
        "</body></html>"
    )


def _context(**meta) -> dict:
    page_metadata = {"name": "The Guide", "description": "How to use it.", **meta}
    return {
        "page_path": "/guide",
        "page_metadata": page_metadata,
        "all_pages": [{"path": "/", "name": "Home", "description": ""}],
        "app_config": {"name": "Test App — a demo", "base_url": "https://example.com"},
    }


class TestTitleResolution:
    def test_app_level_title_is_upgraded_to_the_resolved_title(self):
        """The static-template case the rewrite exists for: every URL ships
        the same app-level <title>, so the page gets its qualified one."""
        out = inject_prerender(_document("Test App — a demo"), _context())
        assert "<title>The Guide · Test App</title>" in out

    def test_page_specific_title_is_never_downgraded(self):
        """Dash Pages resolves per-page titles server-side. A title already
        carrying the page's name is the application's own, deliberate title
        — replacing "site | page" with a synthesized "page · site" clobbers
        it for nothing."""
        out = inject_prerender(_document("Test App | The Guide"), _context())
        assert "<title>Test App | The Guide</title>" in out

    def test_a_name_that_is_already_a_composed_title_is_not_suffixed(self):
        """A page NAME carrying a title separator ("Smoke | The Guide") is
        already branded by its author — appending the site would double it
        ("Smoke | The Guide · Smoke App"). Caught by CI's smoke script the
        first time the resolver ran on the prerender path."""
        out = inject_prerender(
            _document("App"),
            _context(name="Smoke | The Guide"),
        )
        assert "<title>Smoke | The Guide</title>" in out

    def test_explicit_metadata_title_is_authoritative(self):
        out = inject_prerender(
            _document("Test App | The Guide"),
            _context(title="Custom Title"),
        )
        assert "<title>Custom Title</title>" in out


class TestHeadDeduplication:
    def test_existing_og_title_is_not_duplicated(self):
        head = '<meta property="og:title" content="Test App | The Guide">'
        out = inject_prerender(_document("Test App | The Guide", head), _context())
        assert out.count('property="og:title"') == 1

    def test_injected_og_title_carries_the_resolved_title_not_the_bare_name(self):
        out = inject_prerender(_document("Test App — a demo"), _context())
        assert 'property="og:title" content="The Guide · Test App"' in out

    def test_existing_canonical_and_description_win(self):
        head = (
            '<link rel="canonical" href="https://example.com/guide">'
            '<meta name="description" content="The app wrote this.">'
        )
        out = inject_prerender(_document("t", head), _context())
        assert out.count('rel="canonical"') == 1
        assert out.count('name="description"') == 1

    def test_bare_index_still_gets_the_full_block(self):
        """An app that declares nothing still gets description, canonical,
        the og set, and JSON-LD — the reason the prerender injects at all."""
        out = inject_prerender(_document("Test App — a demo"), _context())
        for needle in (
            'name="description"',
            'rel="canonical"',
            'property="og:title"',
            'property="og:description"',
            'property="og:url"',
            "application/ld+json",
        ):
            assert needle in out, needle

    def test_image_url_alias_reaches_og_image(self):
        out = inject_prerender(_document("t"), _context(image_url="https://cdn.example/card.png"))
        assert 'property="og:image" content="https://cdn.example/card.png"' in out
