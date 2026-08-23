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


# ---------------------------------------------------------------------------
# 2.6.1 — the prerender is VISIBLE to non-JS consumers
# ---------------------------------------------------------------------------


def _visible_text(html_doc: str) -> str:
    """Text extraction the way visibility-respecting tools do it.

    An outside SEO audit (2026-08-22) read every 2plot host through exactly
    this lens and found only "Loading...": the prerender div shipped with a
    literal `hidden` attribute, so every extractor that respects visibility
    skipped the prose. This helper IS that lens — subtrees under an element
    carrying `hidden` contribute nothing — so these tests fail the moment
    anyone puts the attribute back.
    """
    from html.parser import HTMLParser

    class Extractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.depth = 0  # >0 while inside a hidden subtree
            self.parts: list[str] = []
            self._skip_tag_depth: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.depth += 1
                self._skip_tag_depth.append(tag)
            elif any(name == "hidden" for name, _ in attrs):
                self.depth += 1
                self._skip_tag_depth.append(tag)

        def handle_endtag(self, tag):
            if self._skip_tag_depth and self._skip_tag_depth[-1] == tag:
                self._skip_tag_depth.pop()
                self.depth -= 1

        def handle_data(self, data):
            if self.depth == 0 and data.strip():
                self.parts.append(data.strip())

    ex = Extractor()
    ex.feed(html_doc)
    return " ".join(ex.parts)


class TestPrerenderVisibility:
    def test_prose_survives_a_visibility_respecting_text_extraction(self):
        """The whole 2.6.1 fix, stated as the audit would measure it: a
        non-JS consumer that honours `hidden` must read the page's own name
        and description, not just the Dash loader."""
        out = inject_prerender(_document("Test App — a demo"), _context())
        text = _visible_text(out)
        assert "The Guide" in text
        assert "How to use it." in text

    def test_the_div_itself_carries_no_hidden_attribute(self):
        """The regression pin. `hidden` on the div is what made six
        production hosts read as N identical thin pages each."""
        out = inject_prerender(_document("Test App — a demo"), _context())
        import re

        div = re.search(r'<div id="dimll-prerender"[^>]*>', out)
        assert div, "prerender div missing entirely"
        assert "hidden" not in div.group(0)

    def test_a_synchronous_marked_script_hides_the_div_for_js_browsers(self):
        """The flash guard `hidden` used to provide now lives in an inline
        script IMMEDIATELY after the div (synchronous, so it runs before
        first paint of subsequent content), and the script carries the
        prerender marker so node-stripping logic matches the pair."""
        out = inject_prerender(_document("Test App — a demo"), _context())
        assert (
            '</div><script data-dimll-prerender="1">'
            'document.getElementById("dimll-prerender").hidden=true;'
            "</script>" in out
        )

    def test_the_hide_script_sits_inside_react_entry_point(self):
        """React's mount replaces the whole #react-entry-point subtree, so
        the script must live inside it to be wiped along with the div —
        nothing prerender-flavoured survives hydration."""
        out = inject_prerender(_document("Test App — a demo"), _context())
        entry = out.split('id="react-entry-point"', 1)[1]
        body_after_entry = entry.split("</body>", 1)[0]
        assert "dimll-prerender" in body_after_entry
        # and nothing prerender-marked after the entry point's close
        import re

        tail = out.rsplit("</script>", 1)[1]
        assert "dimll-prerender" not in tail

    def test_the_old_hidden_shape_would_fail_the_extraction(self):
        """Prove the lens actually discriminates: hand the extractor the
        pre-2.6.1 shape and it must see nothing but the loader — otherwise
        test_prose_survives... passes vacuously."""
        legacy = _document("Test App — a demo").replace(
            '<div id="react-entry-point">',
            '<div id="react-entry-point">'
            '<div id="dimll-prerender" data-dimll-prerender="1" hidden>'
            "<main><h1>The Guide</h1><p>How to use it.</p></main></div>",
        )
        text = _visible_text(legacy)
        assert "The Guide" not in text
        assert "Loading..." in text


class TestIdempotencyProbe:
    """2.7.0 hardening: the already-injected check matches the injected
    node's opening tag, never the bare marker string. The bare-substring
    version silently disabled the ENTIRE prerender on two production
    hosts whose index.html merely MENTIONED the marker in a comment."""

    def test_marker_string_in_a_comment_still_gets_injected(self):
        head = "<!-- our tests strip data-dimll-prerender tagged nodes -->"
        out = inject_prerender(_document("Test App — a demo", head), _context())
        assert '<div id="dimll-prerender"' in out, "a comment disabled the prerender"
        assert "The Guide" in out

    def test_marker_in_visible_prose_still_gets_injected(self):
        """Same rule for a docs page ABOUT the package that names the
        attribute in its own body text."""
        doc = _document("Test App — a demo").replace(
            "Loading...", "Loading... data-dimll-prerender is our marker"
        )
        out = inject_prerender(doc, _context())
        assert '<div id="dimll-prerender"' in out

    def test_an_actually_injected_document_is_not_double_injected(self):
        once = inject_prerender(_document("Test App — a demo"), _context())
        twice = inject_prerender(once, _context())
        assert twice == once
        assert twice.count('<div id="dimll-prerender"') == 1


class TestH1AndFooterDedup:
    """Soak/SEO-audit fixes #5 and #6 (2026-08-23)."""

    def test_body_with_its_own_h1_gets_no_header_h1(self):
        """Every host measured two identical h1s: the injected header's
        plus the doc body's own opening markdown H1."""
        out = inject_prerender(
            _document("Test App — a demo"),
            _context(llms_doc="# The Guide\n\nHow to use it."),
        )
        block = out.split('id="dimll-prerender"', 1)[1].split("</div>", 1)[0]
        assert block.count("<h1") == 1, "duplicate h1s are back"
        assert "<main><h1" in block.replace("\n", "")
        # the description paragraph survives in the header
        assert "<header><p>" in block

    def test_body_without_an_h1_keeps_the_header_h1(self):
        """A page with prose that starts mid-thought (or none at all)
        still needs exactly one h1 — the header's."""
        out = inject_prerender(
            _document("Test App — a demo"),
            _context(llms_doc="Just a paragraph, no heading."),
        )
        block = out.split('id="dimll-prerender"', 1)[1].split("</div>", 1)[0]
        assert block.count("<h1") == 1
        assert "<header><h1>" in block

    def test_no_doc_at_all_keeps_the_header_h1(self):
        ctx = _context()
        ctx["page_metadata"] = {k: v for k, v in ctx["page_metadata"].items()}
        out = inject_prerender(_document("Test App — a demo"), ctx)
        block = out.split('id="dimll-prerender"', 1)[1].split("</div>", 1)[0]
        assert block.count("<h1") == 1

    def test_home_footer_does_not_repeat_the_root_llms_link(self):
        ctx = _context(llms_doc="# Home\n\nWelcome.")
        ctx["page_path"] = "/"
        out = inject_prerender(_document("Test App — a demo"), ctx)
        footer = out.split("<footer>", 1)[1].split("</footer>", 1)[0]
        assert footer.count('href="/llms.txt"') == 1, "the doubled home llms link is back"

    def test_inner_page_footer_keeps_both_links(self):
        out = inject_prerender(_document("Test App — a demo"), _context(llms_doc="# G\n\nText."))
        footer = out.split("<footer>", 1)[1].split("</footer>", 1)[0]
        assert "/guide/llms.txt" in footer
        assert footer.count('href="/llms.txt"') == 1
