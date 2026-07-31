"""
A dependency-free Markdown-to-HTML renderer for the crawler-facing body.

This is deliberately not a full CommonMark implementation. It covers the
constructs that actually appear in an ``LLMS_DOC`` and renders everything
else as escaped text, because the output is consumed by search engines and
language models rather than by a browser doing precise layout.

Two constructs matter more than the rest and were missing from the original
"just enough" converter:

* **Links.** ``[text](/other-page)`` used to render as the literal characters
  ``[text](/other-page)``. Every cross-reference an author wrote inside their
  prose was therefore invisible to crawlers, and the internal link graph
  collapsed to whatever the generated nav happened to contain.
* **Fenced code.** ``.. source::`` directives expand to fenced blocks holding
  whole source files. Without fence handling each line became its own
  paragraph, so a page's body turned into hundreds of nonsense ``<p>`` tags —
  which reads to a classifier as low-quality boilerplate.

Security note: all text is escaped before any tag is emitted, and link
targets are filtered to a safe scheme allowlist, so hostile Markdown in a
page's prose cannot inject script into the crawler HTML.
"""

from __future__ import annotations

import html as _stdlib_html
import re
from typing import List, Optional

__all__ = ["render_markdown", "markdown_to_text", "strip_directive_lines"]


# rST-style directives (`.. toc::`, `.. llms_copy::Name`, `.. kwargs::`) come
# from markdown2dash-style page pipelines. They are instructions to a renderer,
# not prose, and used to leak into the crawler HTML as visible body text.
_DIRECTIVE_RE = re.compile(r"^\.\.\s+\w[\w-]*::.*$")

# A directive's option fields (`:code: false`, `:height: 300`) sit on the
# lines immediately below it. They only mean something after a directive,
# which is the only place they are consumed.
_DIRECTIVE_OPTION_RE = re.compile(r"^\s*:[\w-]+:.*$")

_FENCE_RE = re.compile(r"^(```+|~~~+)\s*([\w+-]*)\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")

# Inline patterns, applied to already-escaped text.
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ITALIC_RE = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<![\w_])_([^_\n]+)_(?![\w_])")
_STRIKE_RE = re.compile(r"~~([^~]+)~~")
_AUTOLINK_RE = re.compile(r"(?<![\"'=>])\b(https?://[^\s<>\"')\]]+)")

# Anything not on this list (javascript:, data:, vbscript:, ...) is dropped.
_SAFE_SCHEMES = ("http://", "https://", "mailto:", "tel:", "ftp://")

_PLACEHOLDER = "\x00{}\x00"


def _safe_url(url: str) -> Optional[str]:
    """Return the URL if it is safe to emit as an href/src, else None."""
    candidate = url.strip()
    if not candidate:
        return None

    # Relative and root-relative URLs are always fine — they can't change origin.
    if candidate.startswith(("/", "#", "./", "../")):
        return candidate

    lowered = candidate.lower()
    if lowered.startswith(_SAFE_SCHEMES):
        return candidate

    # A bare "example.com/page" or "page.html" — no scheme, so no scheme risk.
    if ":" not in candidate.split("/", 1)[0]:
        return candidate

    return None


def _render_inline(text: str) -> str:
    """Escape, then apply inline Markdown to a single line of text."""
    text = _stdlib_html.escape(text)

    # Code spans are extracted first and reinserted last so that inline
    # markup inside them (`**` in a code sample) is shown, not interpreted.
    spans: List[str] = []

    def _stash_code(match: "re.Match[str]") -> str:
        spans.append(f"<code>{match.group(1)}</code>")
        return _PLACEHOLDER.format(len(spans) - 1)

    text = _CODE_SPAN_RE.sub(_stash_code, text)

    def _image(match: "re.Match[str]") -> str:
        alt, src, title = match.group(1), match.group(2), match.group(3)
        safe = _safe_url(src)
        if safe is None:
            return alt
        title_attr = f' title="{title}"' if title else ""
        return f'<img src="{safe}" alt="{alt}"{title_attr}>'

    def _link(match: "re.Match[str]") -> str:
        label, href, title = match.group(1), match.group(2), match.group(3)
        safe = _safe_url(href)
        if safe is None:
            return label
        title_attr = f' title="{title}"' if title else ""
        return f'<a href="{safe}"{title_attr}>{label}</a>'

    text = _IMAGE_RE.sub(_image, text)
    text = _LINK_RE.sub(_link, text)

    text = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text)
    text = _ITALIC_RE.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text)
    text = _STRIKE_RE.sub(r"<del>\1</del>", text)

    text = _AUTOLINK_RE.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', text)

    for index, span in enumerate(spans):
        text = text.replace(_PLACEHOLDER.format(index), span)

    return text


class _Renderer:
    """Line-oriented block renderer. One instance per render_markdown call."""

    def __init__(self, strip_directives: bool) -> None:
        self.out: List[str] = []
        self.paragraph: List[str] = []
        self.list_stack: List[str] = []
        self.quote_open = False
        self.strip_directives = strip_directives

    # -- block state -------------------------------------------------------

    def flush_paragraph(self) -> None:
        if self.paragraph:
            joined = " ".join(line.strip() for line in self.paragraph if line.strip())
            if joined:
                self.out.append(f"<p>{_render_inline(joined)}</p>")
            self.paragraph.clear()

    def close_lists(self) -> None:
        while self.list_stack:
            self.out.append(f"</{self.list_stack.pop()}>")

    def close_quote(self) -> None:
        if self.quote_open:
            self.out.append("</blockquote>")
            self.quote_open = False

    def close_all(self) -> None:
        self.flush_paragraph()
        self.close_lists()
        self.close_quote()

    def open_list(self, tag: str) -> None:
        if self.list_stack and self.list_stack[-1] != tag:
            self.out.append(f"</{self.list_stack.pop()}>")
        if not self.list_stack:
            self.out.append(f"<{tag}>")
            self.list_stack.append(tag)

    # -- main loop ---------------------------------------------------------

    def render(self, text: str) -> str:
        lines = text.strip().splitlines()
        index = 0

        while index < len(lines):
            line = lines[index].rstrip()

            fence = _FENCE_RE.match(line.strip())
            if fence:
                index = self._consume_fence(lines, index, fence)
                continue

            if self.strip_directives and _DIRECTIVE_RE.match(line.strip()):
                index += 1
                # Swallow the directive's `:option:` lines too — on their
                # own they are as meaningless as the directive itself.
                while index < len(lines) and _DIRECTIVE_OPTION_RE.match(lines[index]):
                    index += 1
                continue

            if not line.strip():
                self.flush_paragraph()
                self.close_lists()
                self.close_quote()
                index += 1
                continue

            if _HR_RE.match(line) and not self.paragraph:
                self.close_all()
                self.out.append("<hr>")
                index += 1
                continue

            heading = _HEADING_RE.match(line)
            if heading:
                self.close_all()
                level = len(heading.group(1))
                self.out.append(f"<h{level}>{_render_inline(heading.group(2).strip())}</h{level}>")
                index += 1
                continue

            if self._looks_like_table(lines, index):
                index = self._consume_table(lines, index)
                continue

            quote = _BLOCKQUOTE_RE.match(line)
            if quote:
                self.flush_paragraph()
                self.close_lists()
                if not self.quote_open:
                    self.out.append("<blockquote>")
                    self.quote_open = True
                content = quote.group(1).strip()
                if content:
                    self.out.append(f"<p>{_render_inline(content)}</p>")
                index += 1
                continue

            self.close_quote()

            unordered = _UL_RE.match(line)
            ordered = _OL_RE.match(line) if not unordered else None
            if unordered or ordered:
                self.flush_paragraph()
                self.open_list("ul" if unordered else "ol")
                item = (unordered or ordered).group(1)
                self.out.append(f"<li>{_render_inline(item)}</li>")
                index += 1
                continue

            self.close_lists()
            self.paragraph.append(line)
            index += 1

        self.close_all()
        return "\n".join(self.out)

    # -- fenced code -------------------------------------------------------

    def _consume_fence(self, lines: List[str], index: int, fence: "re.Match[str]") -> int:
        self.close_all()
        marker, language = fence.group(1)[0] * 3, fence.group(2)
        body: List[str] = []
        index += 1

        while index < len(lines):
            candidate = lines[index].strip()
            if candidate.startswith(marker) and _FENCE_RE.match(candidate):
                index += 1
                break
            body.append(lines[index])
            index += 1

        code = _stdlib_html.escape("\n".join(body))
        class_attr = f' class="language-{language}"' if language else ""
        self.out.append(f"<pre><code{class_attr}>{code}</code></pre>")
        return index

    # -- pipe tables -------------------------------------------------------

    @staticmethod
    def _looks_like_table(lines: List[str], index: int) -> bool:
        if "|" not in lines[index]:
            return False
        return index + 1 < len(lines) and bool(_TABLE_DIVIDER_RE.match(lines[index + 1].strip()))

    @staticmethod
    def _split_row(line: str) -> List[str]:
        stripped = line.strip().strip("|")
        return [cell.strip() for cell in stripped.split("|")]

    def _consume_table(self, lines: List[str], index: int) -> int:
        self.close_all()
        headers = self._split_row(lines[index])
        index += 2  # header row + divider

        rows: List[List[str]] = []
        while index < len(lines) and "|" in lines[index] and lines[index].strip():
            rows.append(self._split_row(lines[index]))
            index += 1

        head = "".join(f"<th>{_render_inline(cell)}</th>" for cell in headers)
        parts = [f"<table><thead><tr>{head}</tr></thead><tbody>"]
        for row in rows:
            cells = "".join(f"<td>{_render_inline(cell)}</td>" for cell in row)
            parts.append(f"<tr>{cells}</tr>")
        parts.append("</tbody></table>")
        self.out.append("".join(parts))
        return index


def strip_directive_lines(text: str) -> str:
    """Drop rST-style directive lines and their ``:option:`` continuations.

    The Markdown surfaces serve prose byte-for-byte, so renderer-only
    instructions (``.. exec::page.module``, ``.. toc::``) have to be removed
    on that path as well — an agent gains nothing from them, and an
    ``.. exec::`` line sitting above a fenced block reads as though the
    fence were the directive's payload. Content inside code fences is
    preserved untouched, so a page *documenting* these directives still
    shows its examples.
    """
    lines = text.splitlines()
    out: List[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()

        fence = _FENCE_RE.match(stripped)
        if fence:
            marker, opening_len = fence.group(1)[0], len(fence.group(1))
            out.append(lines[index])
            index += 1
            while index < len(lines):
                out.append(lines[index])
                close = _FENCE_RE.match(lines[index].strip())
                index += 1
                if (
                    close
                    and close.group(1)[0] == marker
                    and len(close.group(1)) >= opening_len
                    and not close.group(2)
                ):
                    break
            continue

        if _DIRECTIVE_RE.match(stripped):
            index += 1
            while index < len(lines) and _DIRECTIVE_OPTION_RE.match(lines[index]):
                index += 1
            continue

        out.append(lines[index])
        index += 1

    result = "\n".join(out)
    if text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def render_markdown(text: Optional[str], *, strip_directives: bool = True) -> str:
    """
    Render an ``LLMS_DOC`` string to crawler-facing HTML.

    Args:
        text: Markdown source. ``None`` or empty returns ``""``.
        strip_directives: Drop rST-style ``.. name::`` lines. These are
            page-pipeline instructions rather than content, and rendering
            them puts literal ``.. toc::`` text in the indexed body.
    """
    if not text or not text.strip():
        return ""
    return _Renderer(strip_directives=strip_directives).render(text)


def markdown_to_text(text: Optional[str], *, limit: Optional[int] = None) -> str:
    """
    Flatten Markdown to plain prose — used for meta descriptions.

    Drops headings, fences, directives and inline markup, then collapses
    whitespace. Truncates on a word boundary when ``limit`` is given.
    """
    if not text:
        return ""

    lines: List[str] = []
    in_fence = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
            continue
        if in_fence or _DIRECTIVE_RE.match(stripped):
            continue
        if not stripped or _HR_RE.match(stripped) or _HEADING_RE.match(stripped):
            continue
        lines.append(stripped)

    joined = " ".join(lines)
    joined = _IMAGE_RE.sub("", joined)
    joined = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", joined)
    joined = re.sub(r"[*_`~>|]+", "", joined)
    joined = re.sub(r"\s+", " ", joined).strip()

    if limit and len(joined) > limit:
        joined = joined[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "…"

    return joined
