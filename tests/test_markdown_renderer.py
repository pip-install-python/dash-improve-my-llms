"""
Tests for the crawler-facing Markdown renderer.

The link and fence cases are the load-bearing ones. Before this renderer
existed, `[text](/page)` rendered as literal bracket-paren text, so every
cross-reference an author wrote inside prose was invisible to crawlers and
the internal link graph silently collapsed.
"""

from __future__ import annotations

import pytest

from dash_improve_my_llms.markdown_renderer import markdown_to_text, render_markdown


class TestLinks:
    """The construct that carries the internal link graph."""

    def test_relative_link_becomes_an_anchor(self):
        out = render_markdown("See [the guide](/docs/guide) for more.")
        assert '<a href="/docs/guide">the guide</a>' in out

    def test_absolute_link(self):
        out = render_markdown("[Plotly](https://plotly.com)")
        assert '<a href="https://plotly.com">Plotly</a>' in out

    def test_link_with_title(self):
        out = render_markdown('[x](/y "A title")')
        assert '<a href="/y" title="A title">x</a>' in out

    def test_bare_url_is_autolinked(self):
        out = render_markdown("Docs at https://example.com/llms.txt here.")
        assert '<a href="https://example.com/llms.txt">' in out

    def test_link_inside_a_list_item(self):
        out = render_markdown("- [One](/one)\n- [Two](/two)")
        assert '<li><a href="/one">One</a></li>' in out
        assert '<li><a href="/two">Two</a></li>' in out

    @pytest.mark.parametrize(
        "scheme", ["javascript:alert(1)", "data:text/html,<script>", "vbscript:x"]
    )
    def test_dangerous_schemes_are_stripped_keeping_the_label(self, scheme):
        out = render_markdown(f"[click]({scheme})")
        assert "<a" not in out
        assert "click" in out
        assert "javascript:" not in out.lower()
        assert "vbscript:" not in out.lower()


class TestFencedCode:
    def test_fence_becomes_pre_code(self):
        out = render_markdown("```python\nx = 1\ny = 2\n```")
        assert '<pre><code class="language-python">' in out
        assert "x = 1\ny = 2" in out
        assert "</code></pre>" in out

    def test_fence_without_language(self):
        out = render_markdown("```\nplain\n```")
        assert "<pre><code>" in out

    def test_code_contents_are_escaped(self):
        out = render_markdown("```html\n<script>alert(1)</script>\n```")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_markdown_inside_a_fence_is_not_interpreted(self):
        """A source file full of `# comments` must not become headings."""
        out = render_markdown("```python\n# not a heading\n**not bold**\n```")
        assert "<h1>" not in out
        assert "<strong>" not in out
        assert "# not a heading" in out

    def test_fence_does_not_swallow_following_prose(self):
        out = render_markdown("```\ncode\n```\n\nAfter the fence.")
        assert "<p>After the fence.</p>" in out


class TestBlocks:
    def test_horizontal_rule(self):
        """`---` used to render as a literal <p>---</p> in the body."""
        out = render_markdown("Before\n\n---\n\nAfter")
        assert "<hr>" in out
        assert "<p>---</p>" not in out

    def test_ordered_list(self):
        out = render_markdown("1. first\n2. second")
        assert "<ol>" in out
        assert "<li>first</li>" in out
        assert "</ol>" in out

    def test_switching_list_type_closes_the_previous_list(self):
        out = render_markdown("- a\n\n1. b")
        assert out.count("<ul>") == 1
        assert out.count("</ul>") == 1
        assert out.count("<ol>") == 1

    def test_pipe_table(self):
        out = render_markdown("| Name | Role |\n|------|------|\n| Ada | Eng |\n| Bo | Design |")
        assert "<table>" in out
        assert "<th>Name</th>" in out
        assert "<td>Ada</td>" in out
        assert "</table>" in out

    def test_image_with_alt_text(self):
        out = render_markdown("![A logo](/assets/logo.png)")
        assert '<img src="/assets/logo.png" alt="A logo">' in out

    def test_multiline_blockquote_stays_one_block(self):
        out = render_markdown("> line one\n> line two")
        assert out.count("<blockquote>") == 1
        assert out.count("</blockquote>") == 1


class TestDirectives:
    """rST-style directives are pipeline instructions, not prose."""

    @pytest.mark.parametrize(
        "directive", [".. toc::", ".. llms_copy::Custom Directives", ".. kwargs::X"]
    )
    def test_directives_are_stripped(self, directive):
        out = render_markdown(f"Intro text.\n\n{directive}\n\nMore text.")
        assert ".." not in out
        assert "toc::" not in out
        assert "<p>Intro text.</p>" in out
        assert "<p>More text.</p>" in out

    def test_directives_can_be_kept(self):
        out = render_markdown(".. toc::", strip_directives=False)
        assert "toc::" in out


class TestInline:
    def test_bold_italic_and_strikethrough(self):
        out = render_markdown("**b** and *i* and ~~s~~")
        assert "<strong>b</strong>" in out
        assert "<em>i</em>" in out
        assert "<del>s</del>" in out

    def test_markup_inside_a_code_span_is_literal(self):
        out = render_markdown("use `**not bold**` here")
        assert "<code>**not bold**</code>" in out
        assert "<strong>" not in out

    def test_underscores_in_identifiers_do_not_become_emphasis(self):
        out = render_markdown("call some_function_name now")
        assert "<em>" not in out
        assert "some_function_name" in out

    def test_html_is_escaped(self):
        out = render_markdown("a <script>alert(1)</script> hazard")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out


class TestMarkdownToText:
    def test_strips_markup_for_meta_descriptions(self):
        text = markdown_to_text("# Title\n\nSome **bold** [link](/x) prose.")
        assert text == "Some bold link prose."

    def test_skips_fences_and_directives(self):
        text = markdown_to_text("Intro.\n\n.. toc::\n\n```\ncode\n```\n\nOutro.")
        assert "code" not in text
        assert "toc" not in text
        assert text == "Intro. Outro."

    def test_truncates_on_a_word_boundary(self):
        text = markdown_to_text("alpha beta gamma delta epsilon", limit=16)
        assert text.endswith("…")
        assert len(text) <= 17
        assert "gam" not in text.replace("gamma", "")

    def test_empty(self):
        assert markdown_to_text("") == ""
        assert markdown_to_text(None) == ""


def test_empty_and_none():
    assert render_markdown("") == ""
    assert render_markdown(None) == ""
    assert render_markdown("   \n  ") == ""
