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
from typing import Any, Dict, List

from .markdown_renderer import markdown_to_text, render_markdown
from .seo import get_seo, icon_link_tags

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


# Site titles are conventionally written "<name> — <tagline>" ("pkg | what it
# does", "Site: the pitch"). The tagline belongs on the home page, not appended
# to all 27 inner-page titles — Google truncates around 60 characters, and a
# suffix that eats 45 of them buys nothing. Take the name and leave the pitch.
_TITLE_SEPARATORS = (" — ", " – ", " | ", " · ", " :: ", ": ")


def _short_site_name(site_name: str) -> str:
    for separator in _TITLE_SEPARATORS:
        head, found, _ = site_name.partition(separator)
        if found and head.strip():
            return head.strip()
    return site_name.strip()


def resolve_page_title(page_path: str, page_metadata: Dict, site_name: str) -> str:
    """The document title for a page, resolved once for every surface.

    An explicit ``title`` wins; otherwise the site's short name is appended,
    except on the home page (where the site name IS the title) and where the
    page name already carries it. Both the crawler document and the universal
    prerender resolve through here — two implementations is how the fleet
    shipped one title to browsers and a different one to Google.
    """
    explicit = str(page_metadata.get("title") or "").strip()
    if explicit:
        return explicit
    name = str(page_metadata.get("name") or "Page")
    if any(separator in name for separator in _TITLE_SEPARATORS):
        # A name carrying a title separator ("pkg | Page") is already a
        # composed title — the author did the branding, and a suffix would
        # double it ("pkg | Page · pkg").
        return name
    short_site = _short_site_name(site_name)
    if short_site and page_path != "/" and short_site.lower() not in name.lower():
        return f"{name} · {short_site}"
    return name


def _breadcrumb_list(page_path: str, name: str, base_url: str, site_name: str) -> Dict:
    """A BreadcrumbList for a non-home page, or {} when there is no trail.

    Built from the URL path rather than a registry, because the path is the
    only structure guaranteed to exist on every host.
    """
    if page_path == "/" or not site_name:
        return {}

    items = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": site_name,
            "item": base_url or "/",
        }
    ]
    segments = [s for s in page_path.strip("/").split("/") if s]
    trail = ""
    for index, segment in enumerate(segments, start=2):
        trail = f"{trail}/{segment}"
        label = name if index == len(segments) + 1 else segment.replace("-", " ").title()
        items.append(
            {
                "@type": "ListItem",
                "position": index,
                "name": label,
                "item": f"{base_url}{trail}",
            }
        )

    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }


def _social_tags(*, social_image: str, seo: Any, head_title: str, description: str) -> str:
    """og:image + the twitter:* set, or "" when no card is declared.

    Twitter reads `name=`, not `property=` — declaring these with `property`
    makes them invisible to it, which is a common and silent mistake.
    """
    if not social_image:
        return ""

    esc = _stdlib_html.escape
    image = esc(social_image, quote=True)
    # `head_title` and `description` arrive ALREADY escaped — escaping them
    # again ships "Draw &amp;amp; Edit" as the alt text. Only the raw config
    # value needs escaping here.
    alt = esc(seo.social_image_alt, quote=True) if seo.social_image_alt else head_title

    lines = [
        f'    <meta property="og:image" content="{image}">',
        f'    <meta property="og:image:secure_url" content="{image}">',
        f'    <meta property="og:image:alt" content="{alt}">',
    ]
    if seo.social_image_width and seo.social_image_height:
        lines.append(
            f'    <meta property="og:image:width" content="{esc(seo.social_image_width, quote=True)}">'
        )
        lines.append(
            f'    <meta property="og:image:height" content="{esc(seo.social_image_height, quote=True)}">'
        )
    lines.append("")
    lines.append(f'    <meta name="twitter:card" content="{esc(seo.twitter_card, quote=True)}">')
    if seo.twitter_site:
        lines.append(
            f'    <meta name="twitter:site" content="{esc(seo.twitter_site, quote=True)}">'
        )
    lines.append(f'    <meta name="twitter:title" content="{head_title}">')
    lines.append(f'    <meta name="twitter:description" content="{description}">')
    lines.append(f'    <meta name="twitter:image" content="{image}">')
    lines.append(f'    <meta name="twitter:image:alt" content="{alt}">')
    return "\n".join(lines)


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
    name = str(page_metadata.get("name") or "Page")
    llms_doc = page_metadata.get("llms_doc")
    base_url = str(app_config.get("base_url", "")).rstrip("/")
    site_name = str(app_config.get("name") or "")

    # The <title> a crawler sees used to be the bare page name, while the
    # browser got the application's own prefixed title — so a docs page shipped
    # as "dash-leaflet2 | Attribution" to a human and "Attribution" to Google,
    # which then rendered a result indistinguishable from every other page on
    # the web with that heading. An explicit `title` wins; otherwise the site
    # name is appended, except on the home page (where it IS the title) and
    # where the page name already carries it.
    heading_title = resolve_page_title(page_path, page_metadata, site_name)

    title = _stdlib_html.escape(name)
    head_title = _stdlib_html.escape(heading_title)

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

    seo = get_seo()

    # Per-page card wins over the site default. `og_image` has been an
    # advertised `register_page_metadata` kwarg since 2.0 — documented as
    # "passed through to html_generator" — and was read by nothing until now.
    social_image = str(
        page_metadata.get("og_image") or page_metadata.get("image_url") or seo.social_image or ""
    ).strip()

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
    if seo.publisher:
        structured_data["publisher"] = {
            "@type": "Organization",
            "name": seo.publisher,
        }
    if seo.same_as:
        # The other properties that are the same entity — sibling domains,
        # the GitHub repo, the PyPI project. For a family of domains this is
        # how they say "we are one thing" rather than N unrelated sites.
        structured_data["sameAs"] = list(seo.same_as)
    if social_image:
        structured_data["image"] = social_image

    # Breadcrumbs, but only where there is a trail to describe: emitting a
    # one-item BreadcrumbList for the home page is noise, and Google ignores
    # it anyway.
    breadcrumb = _breadcrumb_list(page_path, name, base_url, site_name)

    if llms_doc:
        body_html = render_markdown(llms_doc)
    else:
        body_html = "<p>This page contains interactive content that requires JavaScript.</p>"

    llms_link = f"{page_path.rstrip('/')}/llms.txt" if page_path != "/" else "/llms.txt"

    # Each of these renders to "" when nothing is configured, and each carries
    # its OWN leading newline when it does not — so an unconfigured head keeps
    # exactly the blank lines 2.4.0 had.
    _icons = icon_link_tags()
    icon_links = f"\n{_icons}" if _icons else ""

    _social = _social_tags(
        social_image=social_image,
        seo=seo,
        head_title=head_title,
        description=description,
    )
    social_tags = f"\n{_social}" if _social else ""

    site_name_esc = _stdlib_html.escape(site_name or app_config.get("name", ""))

    breadcrumb_block = (
        f'\n\n    <script type="application/ld+json">\n' f"{_json_ld(breadcrumb)}\n    </script>"
        if breadcrumb
        else ""
    )

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
{icon_links}
    <meta property="og:type" content="website">
    <meta property="og:title" content="{head_title}">
    <meta property="og:description" content="{description}">
    <meta property="og:url" content="{base_url}{page_path}">
    <meta property="og:site_name" content="{site_name_esc}">
{social_tags}
    <title>{head_title}</title>

    <script type="application/ld+json">
{_json_ld(structured_data)}
    </script>{breadcrumb_block}

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
