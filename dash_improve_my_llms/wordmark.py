"""
Wordmark rendering for the ``llms.txt`` viewer banner.

Two forms are supported. ASCII art, which a network can publish as-is, and a
**morse mark**: a prefix, a word encoded as morse code laid out as columns of
dots and dashes, and a suffix. ``2`` + morse(``plot``) + ``.ai`` renders
``2.--. .-.. --- -.ai`` as a graphic rather than as characters.

The renderer is deliberately generic — it takes the prefix, word and suffix as
data — because this package should not ship any particular network's branding.
Point it at your own strings and it draws your mark.

Output is a self-contained inline SVG: no external fonts, no image requests,
no script. That matters because it lands in a documentation page that has to
render correctly behind any CSP and with no network access.

Morse is a nice fit for a machine-readable-documentation site, and it earns
the animation: the symbols key on in sequence, left to right, like a signal
being transmitted, rather than moving decoratively for its own sake.
"""

from __future__ import annotations

import html as _stdlib_html
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["render_morse_wordmark", "WORDMARK_CSS", "MORSE"]

MORSE: Dict[str, str] = {
    "a": ".-",
    "b": "-...",
    "c": "-.-.",
    "d": "-..",
    "e": ".",
    "f": "..-.",
    "g": "--.",
    "h": "....",
    "i": "..",
    "j": ".---",
    "k": "-.-",
    "l": ".-..",
    "m": "--",
    "n": "-.",
    "o": "---",
    "p": ".--.",
    "q": "--.-",
    "r": ".-.",
    "s": "...",
    "t": "-",
    "u": "..-",
    "v": "...-",
    "w": ".--",
    "x": "-..-",
    "y": "-.--",
    "z": "--..",
    "0": "-----",
    "1": ".----",
    "2": "..---",
    "3": "...--",
    "4": "....-",
    "5": ".....",
    "6": "-....",
    "7": "--...",
    "8": "---..",
    "9": "----.",
}

# --- geometry (SVG user units) ---------------------------------------------
_H = 120.0  # viewBox height
_CY = _H / 2.0  # baseline centre for the text glyphs
_DOT_R = 6.5
_DASH_W = 13.0
_DASH_H = 26.0
_DASH_RX = 5.0  # not _DASH_W/2: a true stadium reads soft, this reads cut
_SYM_GAP = 7.0  # vertical gap between symbols inside one letter column
_COL_PITCH = 24.0  # horizontal distance between letter columns
_PAD = 8.0
_FONT = 92.0
_GAP = 16.0  # gap between the text groups and the morse block

# Every letter column *ends* here — columns sit on a shared baseline rather
# than being centred on _CY or hung from a common top.
#
# Centring is wrong the moment two letters have different symbol counts: a
# single-dash letter like T hovers in the middle of the mark with empty space
# above and below, reading as a stray element rather than part of the word.
# Top-hanging fixes that but leaves short columns floating clear of the
# bottom, which is the same problem upside down.
#
# A shared baseline is what makes the morse block sit with the text: the
# glyphs beside it rest on a baseline too, so short columns grow upward from
# the same line instead of dangling from an invisible ceiling.
#
# It is the *text's* baseline, not an arbitrary line. The glyphs are drawn
# with dominant-baseline="central" at _CY, so their cap height spans roughly
# _CY ± _CAP_HALF and they sit on _CY + _CAP_HALF. Deriving the value keeps
# the two aligned if the font size ever changes.
_CAP_HALF = _FONT * 0.35
_BASELINE = _CY + _CAP_HALF

# The tallest column can now extend above y=0, so the viewBox grows upward
# instead of clipping it (see render_morse_wordmark).
_VPAD = 8.0

# Where the upward flourish over a trailing `i` starts.
_ARROW_TOP = _CY - 46.0

# Rough advance widths as a fraction of font size, for the few glyphs used.
# Reserving space this way avoids depending on a font being present, which is
# the whole reason the text is drawn at a fixed size rather than measured.
_ADVANCE = {"2": 0.60, ".": 0.28, "a": 0.56, "i": 0.26, "l": 0.26}
_DEFAULT_ADVANCE = 0.60

# Leads with precise geometric grotesques. The single-storey `a` in Futura and
# Century Gothic is what the mark is drawn around, but they are placed after
# the tighter faces so the glyphs read crisp rather than soft where a sharper
# one is installed.
_FONT_STACK = (
    "'Futura PT', 'Avenir Next', Futura, 'Century Gothic', "
    "'Helvetica Neue', Inter, 'Segoe UI', Arial, sans-serif"
)


def _esc(value: Any) -> str:
    return _stdlib_html.escape(str(value or ""), quote=True)


def _text_width(text: str) -> float:
    return sum(_ADVANCE.get(ch.lower(), _DEFAULT_ADVANCE) for ch in text) * _FONT


def _symbols(word: str) -> List[str]:
    """Morse patterns for each encodable character, in order."""
    return [MORSE[ch] for ch in word.lower() if ch in MORSE]


def _column_height(pattern: str) -> float:
    heights = [(_DOT_R * 2 if s == "." else _DASH_H) for s in pattern]
    return sum(heights) + _SYM_GAP * (len(heights) - 1)


def _render_column(pattern: str, x_center: float, index_offset: int) -> Tuple[str, int]:
    """One letter as a vertical run of dots and dashes, sitting on _BASELINE."""
    y = _BASELINE - _column_height(pattern)
    parts: List[str] = []
    index = index_offset

    for symbol in pattern:
        # Every symbol carries its sequence index so the CSS can stagger the
        # keying animation across the whole mark, not just within a letter.
        if symbol == ".":
            cy = y + _DOT_R
            parts.append(
                f'<circle class="mk-sym mk-dot" style="--mk-i:{index}" '
                f'cx="{x_center:.1f}" cy="{cy:.1f}" r="{_DOT_R}"/>'
            )
            y += _DOT_R * 2
        else:
            parts.append(
                f'<rect class="mk-sym mk-dash" style="--mk-i:{index}" '
                f'x="{x_center - _DASH_W / 2:.1f}" y="{y:.1f}" '
                f'width="{_DASH_W}" height="{_DASH_H}" rx="{_DASH_RX:.1f}"/>'
            )
            y += _DASH_H
        y += _SYM_GAP
        index += 1

    return "".join(parts), index


def _render_arrow(x_center: float) -> str:
    """
    The upward flourish that replaces a trailing ``i``'s dot.

    Drawn as a path rather than typeset, because no font provides a dotless i
    with an arrow above it and relying on one would make the mark depend on
    what happens to be installed.
    """
    top = _ARROW_TOP
    stem_top = _CY - 18.0
    stem_bottom = _CY + 30.0
    half = 5.5
    head = 13.0

    arrow = (
        f"M {x_center:.1f} {top:.1f} "
        f"L {x_center + head:.1f} {top + head + 2:.1f} "
        f"L {x_center + half:.1f} {top + head + 2:.1f} "
        f"L {x_center + half:.1f} {stem_top - 4:.1f} "
        f"L {x_center - half:.1f} {stem_top - 4:.1f} "
        f"L {x_center - half:.1f} {top + head + 2:.1f} "
        f"L {x_center - head:.1f} {top + head + 2:.1f} Z"
    )

    stem = (
        f'<rect class="mk-metal" x="{x_center - half:.1f}" y="{stem_top:.1f}" '
        f'width="{half * 2:.1f}" height="{stem_bottom - stem_top:.1f}" rx="{half:.1f}"/>'
    )
    return f'<path class="mk-metal mk-arrow" d="{arrow}"/>{stem}'


def render_morse_wordmark(
    word: str,
    prefix: str = "",
    suffix: str = "",
    label: Optional[str] = None,
    arrow: Optional[bool] = None,
) -> str:
    """
    Render ``prefix`` + morse(``word``) + ``suffix`` as inline SVG.

    Args:
        word: Encoded as morse and drawn as columns of dots and dashes.
        prefix: Drawn as text to the left (e.g. ``"2"``).
        suffix: Drawn as text to the right (e.g. ``".ai"``).
        label: Accessible name. Defaults to ``prefix + word + suffix``.
        arrow: Replace a trailing ``i`` in the suffix with an upward arrow.
            Defaults to True when the suffix ends in ``i``.

    Returns an ``<svg>`` element. Returns ``""`` if nothing is encodable, so
    callers can fall back to a text wordmark.
    """
    patterns = _symbols(word)
    if not patterns and not (prefix or suffix):
        return ""

    if arrow is None:
        arrow = suffix.lower().endswith("i")

    suffix_text = suffix[:-1] if (arrow and suffix) else suffix
    accessible = label or f"{prefix}{word}{suffix}"

    parts: List[str] = []
    x = _PAD

    if prefix:
        parts.append(
            f'<text class="mk-metal mk-text" x="{x:.1f}" y="{_CY:.1f}" '
            f'dominant-baseline="central">{_esc(prefix)}</text>'
        )
        x += _text_width(prefix) + _GAP

    index = 0
    for pattern in patterns:
        column, index = _render_column(pattern, x + _DASH_W / 2, index)
        parts.append(column)
        x += _COL_PITCH
    if patterns:
        x += _GAP - (_COL_PITCH - _DASH_W)

    if suffix_text:
        parts.append(
            f'<text class="mk-metal mk-text" x="{x:.1f}" y="{_CY:.1f}" '
            f'dominant-baseline="central">{_esc(suffix_text)}</text>'
        )
        x += _text_width(suffix_text)

    if arrow and suffix:
        x += 9.0
        parts.append(_render_arrow(x))
        x += 13.0

    width = x + _PAD

    # Vertical bounds are measured from what was actually drawn rather than
    # fixed, because a tall letter column now rises above y=0 once the block
    # sits on the text baseline. A negative viewBox min-y grows the canvas
    # upward; hardcoding a height would silently crop the first symbol of the
    # longest letter instead.
    tops = [_BASELINE - _column_height(pattern) for pattern in patterns]
    tops.append(_CY - _CAP_HALF)  # cap line of the text glyphs
    if arrow and suffix:
        tops.append(_ARROW_TOP)

    min_y = min(tops) - _VPAD
    height = (_BASELINE + _VPAD) - min_y

    return (
        f'<svg class="mk-wordmark" viewBox="0 {min_y:.0f} {width:.0f} {height:.0f}" '
        f'role="img" aria-label="{_esc(accessible)}" '
        f'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMinYMid meet">'
        f"<title>{_esc(accessible)}</title>"
        f"<defs>"
        # Metallic fill: highlight, mid, shadow, then a second highlight, which
        # is what reads as a bevelled edge without needing a real 3D filter.
        f'<linearGradient id="mkMetal" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#ffffff"/>'
        f'<stop offset="34%" stop-color="#eef3f8"/>'
        f'<stop offset="35%" stop-color="#b9c7d4"/>'
        f'<stop offset="56%" stop-color="#8496a6"/>'
        f'<stop offset="57%" stop-color="#dae3ea"/>'
        f'<stop offset="82%" stop-color="#aebecb"/>'
        f'<stop offset="100%" stop-color="#7d8f9e"/>'
        f"</linearGradient>"
        f'<linearGradient id="mkAccent" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#e0559a"/>'
        f'<stop offset="100%" stop-color="#a8437f"/>'
        f"</linearGradient>"
        f'<filter id="mkShadow" x="-12%" y="-12%" width="126%" height="130%">'
        f'<feDropShadow dx="0" dy="1.4" stdDeviation="1.0" '
        f'flood-color="#0b1220" flood-opacity="0.42"/>'
        f"</filter>"
        f"</defs>"
        f'<g filter="url(#mkShadow)" font-family="{_FONT_STACK}" '
        f'font-size="{_FONT:.0f}" font-weight="600" letter-spacing="-2">'
        + "".join(parts)
        + "</g></svg>"
    )


# CSS for the markup above. Lives here so the geometry and its styling stay
# in one place; the viewer includes it in its own stylesheet.
WORDMARK_CSS = """
.mk-wordmark { display: block; width: 100%; max-width: 20rem; height: auto; overflow: visible; }
.mk-metal { fill: url(#mkMetal); stroke: #46586a; stroke-width: 0.9; stroke-opacity: 0.85; stroke-linejoin: miter; }
.mk-text { paint-order: stroke fill; }
.mk-dash { fill: url(#mkMetal); stroke: #46586a; stroke-width: 0.9; stroke-opacity: 0.8; }
.mk-dot { fill: url(#mkAccent); stroke: #6d2653; stroke-width: 0.9; stroke-opacity: 0.75; }
/* Every third dot picks up the muted violet from the mark, so a long run of
   dots doesn't read as one flat block of colour. */
.mk-dot:nth-of-type(3n) { fill: #8d84ad; stroke: #5b5378; }

/* The keying sweep: symbols brighten in transmission order, left to right,
   then the cycle rests. --mk-i is the symbol's index across the whole mark. */
.mk-sym { animation: mk-key 4.2s ease-in-out infinite; animation-delay: calc(var(--mk-i, 0) * 90ms); }
.mk-arrow { animation: mk-lift 3.4s ease-in-out infinite; transform-box: fill-box; transform-origin: center bottom; }

@keyframes mk-key {
  0%, 100% { opacity: 0.62; }
  6% { opacity: 1; }
  26% { opacity: 0.62; }
}
@keyframes mk-lift {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3.5px); }
}

@media (prefers-reduced-motion: reduce) {
  .mk-sym, .mk-arrow { animation: none; opacity: 1; }
}
@media (prefers-color-scheme: dark) {
  .mk-metal, .mk-dash { stroke: #b7c4d1; stroke-opacity: 0.55; }
}
"""


def render_wordmark_spec(spec: Any, fallback_text: str) -> str:
    """
    Render whichever wordmark form ``spec`` describes.

    Accepts a ``{"morse": ..., "prefix": ..., "suffix": ...}`` mapping, a list
    of ASCII-art lines, or None. Returns ``""`` when there is nothing to draw,
    letting the caller fall back to styled text.
    """
    if isinstance(spec, dict):
        word = str(spec.get("morse") or spec.get("word") or "")
        if word:
            return render_morse_wordmark(
                word=word,
                prefix=str(spec.get("prefix") or ""),
                suffix=str(spec.get("suffix") or ""),
                label=spec.get("label") or fallback_text,
                arrow=spec.get("arrow"),
            )
        ascii_art = spec.get("ascii")
        if isinstance(ascii_art, list):
            return _render_ascii(ascii_art, fallback_text)
        return ""

    if isinstance(spec, list):
        return _render_ascii(spec, fallback_text)

    return ""


def _render_ascii(lines: List[str], fallback_text: str) -> str:
    art = "\n".join(_esc(line) for line in lines if isinstance(line, str))
    if not art.strip():
        return ""
    return f'<pre class="dv-wordmark" aria-label="{_esc(fallback_text)}">{art}</pre>'
