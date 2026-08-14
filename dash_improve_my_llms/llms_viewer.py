"""
The human-facing view of an ``llms.txt`` document.

``/<page>/llms.txt`` is a machine-readable document, and it has to stay one:
its whole value is that an agent fetches it and gets clean Markdown with no
chrome to pay tokens for. But the same URL gets pasted into browsers by
people, and a wall of raw Markdown tells them nothing about what they are
looking at or what network it belongs to.

So the route content-negotiates. Anything that isn't clearly a browser — an
agent, a crawler, curl, a link unfurler — receives the Markdown byte for
byte. A browser receives this: the same Markdown rendered, behind a banner
carrying the network identity and, when a bulletin endpoint is configured,
centrally-published tips and announcements.

This is not cloaking. The document is identical in both cases; only the
presentation differs, the way a raw file view and a rendered file view
differ on any code host. The banner exists **only** in the HTML variant, so
it costs an agent exactly zero bytes — which is the point, and the reason it
isn't simply prepended to the Markdown for everyone.
"""

from __future__ import annotations

import html as _stdlib_html
from typing import Any, Dict, List, Optional

from .markdown_renderer import render_markdown
from .wordmark import WORDMARK_CSS, render_wordmark_spec

__all__ = ["render_llms_viewer"]


def _esc(value: Any) -> str:
    return _stdlib_html.escape(str(value or ""), quote=True)


def _render_wordmark(spec: Any, fallback_text: str) -> str:
    """
    Draw the network's mark, falling back to its name in styled text.

    The spec is data — a morse mark, ASCII art, or nothing — supplied either
    locally via ``describe_network(wordmark=...)`` or remotely in the bulletin
    payload. It is not baked into this package, because an open-source library
    should not ship one network's branding, and keeping it configurable means
    changing a wordmark never requires a release of this library.
    """
    rendered = render_wordmark_spec(spec, fallback_text)
    if rendered:
        return rendered

    return f'<div class="dv-wordmark dv-wordmark-text">{_esc(fallback_text)}</div>'


def _render_items(items: List[Dict[str, str]], empty: str) -> str:
    if not items:
        return f'<p class="dv-empty">{_esc(empty)}</p>'

    rows = []
    for index, item in enumerate(items):
        title = _esc(item.get("title"))
        body = _esc(item.get("body"))
        url = item.get("url") or ""
        date = _esc(item.get("date"))

        label = f'<a href="{_esc(url)}" rel="noopener">{title}</a>' if url else title
        meta = f'<span class="dv-date">{date}</span>' if date else ""
        text = f'<span class="dv-item-body">{body}</span>' if body else ""

        # Staggered animation delay, inline because it is per-item data.
        rows.append(
            f'<li style="--dv-i:{index}">'
            f'<span class="dv-bullet">▸</span>'
            f'<span class="dv-item-text"><strong>{label}</strong>{meta}{text}</span>'
            f"</li>"
        )
    return f'<ul class="dv-items">{"".join(rows)}</ul>'


def _viewer_identity():
    """The current reader, when the application supplies one. Never raises."""
    try:
        from .access import viewer_identity

        return viewer_identity()
    except Exception:  # noqa: BLE001 - chrome must never break the document
        return None


def _render_identity(identity) -> str:
    """One line naming the signed-in reader, or nothing at all."""
    if not identity:
        return ""
    name = _esc(str(identity.get("name") or ""))
    if not name:
        return ""
    bits = [f'<span class="dv-user">{name}</span>']
    plan = _esc(str(identity.get("plan") or ""))
    if plan:
        bits.append(f'<span class="dv-plan">{plan}</span>')
    since = _esc(str(identity.get("since") or ""))
    if since:
        bits.append(f'<span class="dv-since">session since {since}</span>')
    return f'<div class="dv-signed-in">signed in as {" · ".join(bits)}</div>'


def _render_banner(
    *,
    page_name: str,
    app_name: str,
    site_llms_url: str,
    bulletin: Optional[Dict[str, Any]],
    network_name: str,
    network_url: str,
    network_llms_url: str,
    wordmark_spec: Any = None,
) -> str:
    """The full-width terminal-style header block."""
    info = (bulletin or {}).get("network") or {}

    name = info.get("name") or network_name or app_name
    tagline = info.get("tagline") or ""
    hub_url = info.get("url") or network_url
    hub_llms = info.get("llms_txt") or network_llms_url
    # A bulletin-published mark wins: it lets the hub restyle the whole
    # network without a redeploy of every satellite.
    wordmark = _render_wordmark(info.get("wordmark") or wordmark_spec, name)

    tips = _render_items(
        (bulletin or {}).get("tips") or [],
        "Append /llms.txt to any page URL on this site to read it as Markdown.",
    )
    whats_new = _render_items((bulletin or {}).get("whats_new") or [], "No announcements.")

    title_bar = _esc(name) if name else "Machine-readable documentation"

    hub_links = []
    if hub_llms:
        hub_links.append(f'<a href="{_esc(hub_llms)}" rel="noopener">network index</a>')
    if site_llms_url:
        hub_links.append(f'<a href="{_esc(site_llms_url)}">site index</a>')
    if hub_url:
        hub_links.append(f'<a href="{_esc(hub_url)}" rel="noopener">{_esc(hub_url)}</a>')
    links_html = " · ".join(hub_links)

    # Who is reading this, when the application supplies it. HTML only — the
    # Markdown variant of this same URL is what agents and crawlers receive,
    # and it never carries a name. Sites without authentication configure no
    # provider and render nothing here.
    signed_in = _render_identity(_viewer_identity())

    return f"""<div class="dv-banner" role="complementary" aria-label="Network information">
  <div class="dv-banner-title"><span>{title_bar}</span></div>
  <div class="dv-banner-grid">
    <div class="dv-identity">
      {wordmark}
      <div class="dv-identity-meta">
        <div class="dv-app">{_esc(app_name)}<span class="dv-cursor"></span></div>
        <div class="dv-page">{_esc(page_name)}</div>
        {f'<div class="dv-tagline">{_esc(tagline)}</div>' if tagline else ""}
        {signed_in}
        {f'<div class="dv-links">{links_html}</div>' if links_html else ""}
      </div>
    </div>
    <div class="dv-panels">
      <section class="dv-panel">
        <h2>Tips for getting started</h2>
        {tips}
      </section>
      <section class="dv-panel">
        <h2>What's new</h2>
        {whats_new}
      </section>
    </div>
  </div>
</div>"""


_STYLE = """
:root {
  --dv-bg: #ffffff; --dv-fg: #1b1f24; --dv-muted: #5c6773;
  --dv-line: #d8dee4; --dv-panel: #f6f8fa; --dv-accent: #7b5cff;
  --dv-accent-2: #00b4d8; --dv-code: #f2f4f7;
}
@media (prefers-color-scheme: dark) {
  :root {
    --dv-bg: #0d1117; --dv-fg: #e6edf3; --dv-muted: #8b949e;
    --dv-line: #2a3139; --dv-panel: #12181f; --dv-accent: #9d7cff;
    --dv-accent-2: #3ad1f0; --dv-code: #161b22;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0 1rem 4rem;
  background: var(--dv-bg); color: var(--dv-fg);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
.dv-wrap { max-width: 62rem; margin: 0 auto; }

/* ---- banner ---- */
.dv-banner {
  position: relative; margin: 1.75rem 0 2rem; padding: 1.25rem 1.25rem 1.1rem;
  border: 1px solid var(--dv-line); border-radius: 10px;
  background: var(--dv-panel); overflow: hidden;
}
.dv-banner::before {
  content: ""; position: absolute; inset: 0 0 auto 0; height: 2px;
  background: linear-gradient(90deg, var(--dv-accent), var(--dv-accent-2), var(--dv-accent));
  background-size: 200% 100%; animation: dv-sweep 6s linear infinite;
}
.dv-banner-title {
  position: absolute; top: -0.68rem; left: 1rem; padding: 0 0.5rem;
  background: var(--dv-panel); color: var(--dv-muted);
  font: 600 0.72rem/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  letter-spacing: 0.12em; text-transform: uppercase;
}
.dv-banner-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); gap: 1.5rem; }
@media (max-width: 46rem) { .dv-banner-grid { grid-template-columns: 1fr; gap: 1.1rem; } }

.dv-identity { display: flex; flex-direction: column; gap: 0.7rem; min-width: 0; }
.dv-wordmark {
  margin: 0; font: 700 0.58rem/1.05 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space: pre; overflow-x: auto;
  background: linear-gradient(100deg, var(--dv-accent) 10%, var(--dv-accent-2) 45%, var(--dv-accent) 80%);
  background-size: 220% 100%;
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; color: transparent;
  animation: dv-sweep 7s linear infinite;
}
.dv-wordmark-text {
  font-size: 1.85rem; line-height: 1.1; white-space: normal;
  letter-spacing: -0.02em;
}
.dv-identity-meta { font: 0.82rem/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.dv-app { font-weight: 700; font-size: 0.95rem; }
.dv-page { color: var(--dv-muted); }
.dv-signed-in { margin-top: 0.45rem; color: var(--dv-muted); font-size: 0.76rem; }
.dv-user { color: var(--dv-fg); font-weight: 600; }
.dv-plan, .dv-since { color: var(--dv-muted); }
.dv-tagline { margin-top: 0.35rem; color: var(--dv-muted); }
.dv-links { margin-top: 0.5rem; font-size: 0.76rem; }
.dv-links a { color: var(--dv-accent); text-decoration: none; }
.dv-links a:hover { text-decoration: underline; }
.dv-cursor {
  display: inline-block; width: 0.5rem; height: 0.95rem; margin-left: 0.3rem;
  vertical-align: -0.1rem; background: var(--dv-accent-2);
  animation: dv-blink 1.1s step-end infinite;
}

.dv-panels { display: grid; gap: 1rem; min-width: 0; }
.dv-panel h2 {
  margin: 0 0 0.45rem; font: 600 0.72rem/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  letter-spacing: 0.1em; text-transform: uppercase; color: var(--dv-muted);
}
.dv-items { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
.dv-items li {
  display: flex; gap: 0.5rem; font-size: 0.85rem; line-height: 1.5;
  opacity: 0; animation: dv-rise 0.45s ease-out forwards;
  animation-delay: calc(var(--dv-i, 0) * 70ms + 120ms);
}
.dv-bullet { color: var(--dv-accent); flex: none; }
.dv-item-text { min-width: 0; }
.dv-item-text strong { font-weight: 600; }
.dv-item-text a { color: inherit; text-decoration: none; border-bottom: 1px solid var(--dv-accent); }
.dv-item-body { display: block; color: var(--dv-muted); font-size: 0.82rem; }
.dv-date { margin-left: 0.5rem; color: var(--dv-muted); font-size: 0.72rem; }
.dv-empty { margin: 0; color: var(--dv-muted); font-size: 0.82rem; }

@keyframes dv-sweep { to { background-position: 200% 0; } }
@keyframes dv-blink { 50% { opacity: 0; } }
@keyframes dv-rise { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  .dv-banner::before, .dv-wordmark, .dv-cursor, .dv-items li { animation: none; }
  .dv-items li { opacity: 1; }
  .dv-wordmark { -webkit-text-fill-color: currentColor; color: var(--dv-accent); }
}

/* ---- the document ---- */
.dv-raw {
  display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center;
  margin: 0 0 1.5rem; padding: 0.6rem 0.8rem;
  border: 1px dashed var(--dv-line); border-radius: 8px;
  font: 0.78rem/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--dv-muted);
}
.dv-raw a { color: var(--dv-accent); }
.dv-doc { overflow-wrap: break-word; }
.dv-doc h1 { font-size: 1.9rem; line-height: 1.2; margin: 1.6rem 0 0.6rem; }
.dv-doc h2 { font-size: 1.35rem; margin: 2rem 0 0.5rem; padding-bottom: 0.25rem; border-bottom: 1px solid var(--dv-line); }
.dv-doc h3 { font-size: 1.1rem; margin: 1.6rem 0 0.4rem; }
.dv-doc h4, .dv-doc h5, .dv-doc h6 { font-size: 0.98rem; margin: 1.3rem 0 0.35rem; }
.dv-doc a { color: var(--dv-accent); }
.dv-doc blockquote {
  margin: 1rem 0; padding: 0.1rem 0 0.1rem 1rem;
  border-left: 3px solid var(--dv-accent); color: var(--dv-muted);
}
.dv-doc code {
  padding: 0.12em 0.36em; border-radius: 4px; background: var(--dv-code);
  font: 0.88em ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.dv-doc pre {
  margin: 1rem 0; padding: 0.9rem 1rem; overflow-x: auto;
  background: var(--dv-code); border: 1px solid var(--dv-line); border-radius: 8px;
}
.dv-doc pre code { padding: 0; background: none; font-size: 0.82rem; line-height: 1.55; }
.dv-doc img { max-width: 100%; height: auto; }
.dv-doc hr { margin: 2rem 0; border: 0; border-top: 1px solid var(--dv-line); }
.dv-doc table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; display: block; overflow-x: auto; }
.dv-doc th, .dv-doc td { padding: 0.45rem 0.7rem; border: 1px solid var(--dv-line); text-align: left; }
.dv-doc th { background: var(--dv-panel); }
.dv-foot { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--dv-line); color: var(--dv-muted); font-size: 0.8rem; }
.dv-foot a { color: var(--dv-accent); }
"""


def render_llms_viewer(
    *,
    markdown_body: str,
    page_name: str,
    app_name: str,
    raw_url: str,
    source_note: str = "",
    site_llms_url: str = "/llms.txt",
    network_name: str = "",
    network_url: str = "",
    network_llms_url: str = "",
    bulletin: Optional[Dict[str, Any]] = None,
    wordmark: Any = None,
) -> str:
    """
    Wrap an ``llms.txt`` body in the browser-facing view.

    ``markdown_body`` is rendered as-is; the caller has already assembled it,
    so what a reader sees here is exactly what an agent receives from the
    same URL.

    ``source_note`` is the one caller-overridable sentence in the chrome,
    because exactly one document breaks that equivalence: a browser asking
    for /llms-full.txt gets a summary card instead of the corpus, and the
    default sentence would then describe the card as what agents receive.
    """
    source_note = source_note or "agents fetching this URL receive the Markdown below, unwrapped."
    banner = _render_banner(
        page_name=page_name,
        app_name=app_name,
        site_llms_url=site_llms_url,
        bulletin=bulletin,
        network_name=network_name,
        network_url=network_url,
        network_llms_url=network_llms_url,
        wordmark_spec=wordmark,
    )

    document = render_markdown(markdown_body, strip_directives=False)
    title = f"{page_name} · llms.txt" if page_name else "llms.txt"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<!-- This rendered view is for people. Agents and crawlers receive the
     identical document as text/markdown from this same URL; the banner
     exists only here so it costs them nothing. -->
<meta name="robots" content="noindex, follow">
<link rel="alternate" type="text/markdown" href="{_esc(raw_url)}?raw=1" title="Raw Markdown">
<style>{_STYLE}{WORDMARK_CSS}</style>
</head>
<body>
<div class="dv-wrap">
{banner}
<div class="dv-raw">
  <span>Machine-readable source:</span>
  <a href="{_esc(raw_url)}?raw=1">{_esc(raw_url)}</a>
  <span>— {_esc(source_note)}</span>
</div>
<article class="dv-doc">
{document}
</article>
<footer class="dv-foot">
  <a href="{_esc(site_llms_url)}">Site index</a>
  {f' · <a href="{_esc(network_llms_url)}" rel="noopener">Network index</a>' if network_llms_url else ""}
   · <a href="/sitemap.xml">Sitemap</a>
   · <a href="/robots.txt">robots.txt</a>
  <p>Rendered by <a href="https://pypi.org/project/dash-improve-my-llms/" rel="noopener">dash-improve-my-llms</a>.</p>
</footer>
</div>
</body>
</html>"""
