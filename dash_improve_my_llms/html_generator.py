"""
Static HTML generation for crawlers that don't run JavaScript.

In 2.0 this module is intentionally small: meta tags, OpenGraph,
Schema.org JSON-LD, navigation, and the LLMS_DOC prose rendered as
plain HTML so search engines see the same content a human would.

No component-tree rendering — that surface moved to Dash 4.3 MCP.
"""

from __future__ import annotations

import html as _stdlib_html
import json
from typing import Dict, List

from .markdown_renderer import markdown_to_text, render_markdown

# Kept as the historical name for this module's renderer. The implementation
# moved to markdown_renderer.py when it grew link, fence, image and table
# support; this alias keeps existing imports working.
_render_markdown_minimal = render_markdown


def _json_ld(data: Dict) -> str:
    """
    Serialize a dict for embedding in a <script type="application/ld+json">.

    `json.dumps` escapes quotes but not angle brackets, so a page whose name
    or description contained `</script><script>…` would break out of the
    block and execute. Page names and descriptions are author-supplied, and
    in a docs site they can come from Markdown frontmatter, so this is a real
    injection path rather than a theoretical one. Escaping to \\u-sequences
    keeps the JSON semantically identical while making the payload inert.
    """
    return (
        json.dumps(data, indent=2)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def generate_static_page_html(
    page_path: str,
    page_metadata: Dict,
    all_pages: List[Dict],
    app_config: Dict,
) -> str:
    """
    Render the static HTML response that crawlers see.

    Args:
        page_path: The path being requested (e.g. "/equipment").
        page_metadata: Dict with at least "name" and "description"; may
            include "llms_doc" (markdown prose for the page body).
        all_pages: All non-hidden pages — used to build navigation.
        app_config: {"name": str, "base_url": str}.

    Returns:
        Complete HTML document as a string.
    """
    title = _stdlib_html.escape(str(page_metadata.get("name") or "Page"))
    llms_doc = page_metadata.get("llms_doc")
    base_url = str(app_config.get("base_url", "")).rstrip("/")

    # A page whose author never wrote a description still deserves a real one.
    # Falling back to the first prose of its own body beats repeating a generic
    # app-level string across every URL, which reads as duplicate content.
    raw_description = page_metadata.get("description") or markdown_to_text(llms_doc, limit=155)
    description = _stdlib_html.escape(str(raw_description or ""))

    nav_items = []
    for page in all_pages:
        p_path = page.get("path", "/")
        p_name = _stdlib_html.escape(str(page.get("name", "Page")))
        cls = ' class="current"' if p_path == page_path else ""
        nav_items.append(f'<li{cls}><a href="{p_path}">{p_name}</a></li>')

    structured_data = {
        "@context": "https://schema.org",
        "@type": page_metadata.get("schema_type") or "WebPage",
        "name": page_metadata.get("name") or "Page",
        "url": f"{base_url}{page_path}",
        "description": raw_description or "",
        "isPartOf": {
            "@type": "WebSite",
            "name": app_config.get("name", "Dashboard"),
            "url": base_url or "/",
        },
    }

    if llms_doc:
        body_html = render_markdown(llms_doc)
    else:
        body_html = "<p>This page contains interactive content that requires JavaScript.</p>"

    llms_link = f"{page_path.rstrip('/')}/llms.txt" if page_path != "/" else "/llms.txt"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{description}">
    <meta name="robots" content="index, follow">

    <link rel="canonical" href="{base_url}{page_path}">
    <link rel="alternate" type="text/markdown" href="{llms_link}" title="LLM-friendly documentation">
    <link rel="sitemap" type="application/xml" href="/sitemap.xml">

    <meta property="og:type" content="website">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:url" content="{base_url}{page_path}">

    <title>{title}</title>

    <script type="application/ld+json">
{_json_ld(structured_data)}
    </script>

    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 800px; margin: 0 auto; padding: 24px; line-height: 1.6; }}
        header {{ border-bottom: 1px solid #e0e0e0; padding-bottom: 16px; margin-bottom: 24px; }}
        nav ul {{ list-style: none; padding: 0; display: flex; gap: 16px; flex-wrap: wrap; }}
        nav a {{ text-decoration: none; color: #0066cc; }}
        nav .current a {{ font-weight: bold; color: #000; }}
        blockquote {{ border-left: 3px solid #0066cc; padding-left: 12px; color: #555; }}
        code {{ background: #f5f5f5; padding: 2px 4px; border-radius: 3px; }}
        .ai-note {{ background: #f8f8f8; padding: 16px; border-left: 3px solid #0066cc;
                    margin-top: 32px; font-size: 0.95em; }}
        footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e0e0e0;
                  color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <header>
        <h1>{title}</h1>
        <p>{description}</p>
    </header>

    <nav aria-label="Main navigation">
        <ul>{"".join(nav_items)}</ul>
    </nav>

    <main>
        {body_html}

        <section class="ai-note">
            <p><strong>Note for AI agents:</strong> This is the static, prerendered view of an interactive Dash application served because we detected a non-JS user agent. Full prose docs:</p>
            <ul>
                <li><a href="{llms_link}">{llms_link}</a> — LLM-friendly documentation</li>
                <li><a href="/sitemap.xml">/sitemap.xml</a></li>
                <li><a href="/robots.txt">/robots.txt</a></li>
            </ul>
        </section>
    </main>

    <footer>
        <p>Interactive version requires JavaScript.</p>
        <p>Crawler-facing HTML generated by <a href="https://pypi.org/project/dash-improve-my-llms/" rel="nofollow noopener">dash-improve-my-llms</a>.</p>
    </footer>
</body>
</html>"""


def generate_index_template(app_config: Dict, pages: List[Dict]) -> str:
    """
    Optional helper: produce a Dash `app.index_string` template that
    includes AI-discovery meta tags and a noscript fallback for crawlers
    that DO execute the index page but not Dash's JS.

    The package does not call this itself — users who want it can assign
    the return value to `app.index_string`.
    """
    app_name = _stdlib_html.escape(str(app_config.get("name", "Dash Application")))
    app_description = _stdlib_html.escape(
        str(app_config.get("description", "Interactive dashboard application"))
    )
    base_url = app_config.get("base_url", "https://example.com")

    nav_structure = {
        "@context": "https://schema.org",
        "@type": "SiteNavigationElement",
        "name": "Main Navigation",
        "hasPart": [
            {
                "@type": "WebPage",
                "name": p.get("name", "Page"),
                "url": f"{base_url}{p.get('path', '/')}",
                "description": p.get("description", ""),
            }
            for p in pages
        ],
    }

    page_list_items = "".join(
        f'<li><a href="{p.get("path", "/")}">{_stdlib_html.escape(str(p.get("name", "Page")))}</a> '
        f'- {_stdlib_html.escape(str(p.get("description", "")))}</li>'
        for p in pages
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    {{%metas%}}

    <title>{{%title%}}</title>

    <link rel="alternate" type="text/markdown" href="/llms.txt" title="LLM-friendly documentation">
    <link rel="sitemap" type="application/xml" href="/sitemap.xml">

    <meta property="og:type" content="website">
    <meta property="og:title" content="{app_name}">
    <meta property="og:description" content="{app_description}">

    <script type="application/ld+json">
{{
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "{app_name}",
    "description": "{app_description}",
    "url": "{base_url}",
    "applicationCategory": "BusinessApplication",
    "operatingSystem": "Any"
}}
    </script>

    <script type="application/ld+json">
{_json_ld(nav_structure)}
    </script>

    {{%favicon%}}
    {{%css%}}
</head>
<body>
    <noscript>
        <div style="padding: 20px; max-width: 800px; margin: 0 auto; font-family: sans-serif;">
            <h1>{app_name}</h1>
            <p>{app_description}</p>
            <p><strong>This application requires JavaScript.</strong></p>
            <h2>Resources:</h2>
            <ul>
                <li><a href="/llms.txt">LLM-friendly documentation</a></li>
                <li><a href="/sitemap.xml">Sitemap</a></li>
                <li><a href="/robots.txt">Robots.txt</a></li>
            </ul>
            <h2>Pages:</h2>
            <ul>{page_list_items}</ul>
        </div>
    </noscript>

    {{%app_entry%}}

    <footer>
        {{%config%}}
        {{%scripts%}}
        {{%renderer%}}
    </footer>
</body>
</html>"""
