"""
One canonical path form, shared by every module.

Registration (``register_page_metadata``, ``mark_hidden``) and lookup (the
bot middleware, the prerender hook, ``/llms.txt``) used to normalize paths
slightly differently. A page registered as ``"docs/intro"`` or hidden as
``"/admin/"`` then silently failed to match the ``"/docs/intro"`` /
``"/admin"`` the request carried, and the mismatch surfaced as missing prose
or as an internal page that was never actually hidden.

Everything funnels through :func:`normalize_path` so those can't drift.
"""

from __future__ import annotations


def normalize_path(path: str) -> str:
    """
    Canonicalize a page path.

    Guarantees a leading slash and no trailing slash (except for the root
    itself), so ``""``, ``"/"``, ``"docs"``, ``"/docs"`` and ``"/docs/"``
    all agree on one key.

    >>> normalize_path("")
    '/'
    >>> normalize_path("docs/intro/")
    '/docs/intro'
    """
    if not path:
        return "/"

    path = str(path).strip()
    if not path:
        return "/"

    # Tolerate a full URL being passed by mistake — keep only the path part.
    if "://" in path:
        remainder = path.split("://", 1)[1]
        path = "/" + remainder.split("/", 1)[1] if "/" in remainder else "/"

    if not path.startswith("/"):
        path = "/" + path

    # Drop query/fragment noise; a page key is a path and nothing else.
    for sep in ("?", "#"):
        if sep in path:
            path = path.split(sep, 1)[0]

    if len(path) > 1:
        path = path.rstrip("/") or "/"

    return path
