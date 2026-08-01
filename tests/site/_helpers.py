"""Shared HTML-inspection helpers for the site tests.

Named with a leading underscore so pytest never collects it, and imported by
name (the tests/site directory is on sys.path when its tests run) so it can
never collide with the package suite's tests/conftest.py.
"""

from __future__ import annotations

import re
from pathlib import Path

# Exported from here rather than from conftest: two conftest.py files exist
# (tests/ and tests/site/), and `from conftest import ...` in a test module
# would resolve to whichever one hit sys.modules first.
REPO_ROOT = Path(__file__).resolve().parents[2]


def visible(html: str) -> str:
    """The document with HTML comments removed.

    A regex cannot tell a commented-out example tag from a live one — the
    boilerplate's version of these tests once reported a manifest link that
    was, in fact, commented out.
    """
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def meta(html: str, value: str) -> list:
    """Every `content` for a property/name — a list, so duplicates show up.

    Tags carrying `data-dimll-prerender` are excluded: dash-improve-my-llms
    injects its own marked description/OpenGraph block on the prerender path,
    and counting those would make these tests fail on package behaviour. What
    is being tested here is duplication between the app's index_string and
    the tags Dash generates from register_page.
    """
    pattern = (
        rf'<meta[^>]*(?:property|name)="{re.escape(value)}"[^>]*content="([^"]*)"'
        rf'|<meta[^>]*content="([^"]*)"[^>]*(?:property|name)="{re.escape(value)}"'
    )
    body = re.sub(r"<meta[^>]*data-dimll-prerender[^>]*>", "", visible(html))
    return ["".join(m) for m in re.findall(pattern, body)]
