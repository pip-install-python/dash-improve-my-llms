"""Fail-closed token gate for the site's /admin dashboard.

SITE CODE ONLY — this belongs to the docs site (app.py + pages/), not to the
dash_improve_my_llms package.

WHY A SECOND CONTROL EXISTS AT ALL
----------------------------------
``mark_hidden("/admin")`` is a DISCOVERABILITY control, and the package is
explicit about it: the path leaves /sitemap.xml, gains a Disallow line in
/robots.txt, 404s for crawlers and for /admin/llms.txt, and never registers
as an MCP resource. None of that is access control — every one of those
surfaces is about who is TOLD the page exists. A browser that types the URL
still gets the whole dashboard, and robots.txt's Disallow line publishes the
path to anyone who reads it.

That was fine while /admin rendered throwaway demo rows. It stopped being
fine when this host joined the x402 dataset: the ledger now lives on a
persistent disk (TRAFFIC_ANALYTICS_FILE -> /var/data) and holds real visitor
records — including ``ip_address`` and ``location``, which the tracker
collects for the hourly rollup. The page renders neither field (see the PII
floor on ``create_bot_visits_table``), but ``load_analytics()`` pulls the FULL
ledger into layout code, so the distance between "delisted" and "leaked" was
one careless component. This gate closes the page; the PII floor stays a hard
rule regardless of the gate.

WHY NOT THE PACKAGE'S ACCESS MACHINERY
--------------------------------------
``configure_access()`` (docs/ACCESS.md) governs the surfaces the PACKAGE
serves for a path — /<page>/llms.txt, crawler HTML, prerender, sitemap
listing. It does not, and by design cannot, gate the interactive Dash page:
docs/ACCESS.md calls the app's own layout "the only surface the app
controls". For /admin those package surfaces are already 404 via
mark_hidden(), so the one gap left is precisely the layout — which is what
this module gates.

WHY THE CHECK LIVES INSIDE layout(), NOT IN A before_request HOOK
-----------------------------------------------------------------
With Dash Pages the page layout is not rendered by the GET of /admin. That
request returns the app shell; the layout arrives from the pages router
callback, a POST to /_dash-update-component whose URL says nothing about
/admin (verified: that POST returns the full dashboard HTML, "Total Visits"
included). A path-based Flask hook would guard the shell and wave the
dashboard through. dash.Dash calls the page layout as
``layout(**query_parameters)``, so the token reaches the ONE function that
every render path goes through — direct load and client-side navigation
alike.

THE RULES
---------
- ``ADMIN_DASH_TOKEN`` unset or empty => locked, unconditionally. Production
  fails closed; local development sets it in .env.
- Comparison is ``hmac.compare_digest`` on bytes.
- The env var is read at CALL time, never captured at import, so rotating the
  secret takes effect on the next render rather than the next deploy.
- The cookie stores a DERIVED value, never the token itself. Rotating
  ADMIN_DASH_TOKEN therefore invalidates every outstanding cookie for free.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Optional

#: Environment variable holding the shared secret. Render sets it with
#: ``sync: false`` (dashboard-set, like CROSS_APP_WEBHOOK_SECRET).
ENV_VAR = "ADMIN_DASH_TOKEN"

#: Query-string argument Dash hands to ``layout()`` as a keyword argument.
QUERY_ARG = "token"

#: Name of the cookie that keeps a browser unlocked after the first visit,
#: so navigating away and back does not require re-pasting ?token=.
COOKIE_NAME = "admin_dash_gate"

#: Cookie lifetime. Short enough that a shared machine forgets, long enough
#: to read a dashboard without re-authenticating every few minutes.
COOKIE_MAX_AGE = 12 * 60 * 60

_COOKIE_CONTEXT = b"admin-dash-gate/v1"


def _expected_token() -> str:
    """The configured secret, or "" when the gate is unconfigured (locked)."""
    return (os.environ.get(ENV_VAR) or "").strip()


def _matches(presented: Any, expected: str) -> bool:
    """Constant-time compare, tolerant of whatever a query string produced.

    A repeated ``?token=a&token=b`` reaches layout() as a LIST, and anything
    that is not a plain non-empty string is refused rather than coerced —
    fail closed on input we did not anticipate.
    """
    if not expected or not isinstance(presented, str) or not presented:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def cookie_value(expected: Optional[str] = None) -> str:
    """The cookie that proves a token was presented, derived from the token.

    Keyed by the secret itself, so the value is worthless against any other
    deployment and dies the moment the secret rotates.
    """
    secret = _expected_token() if expected is None else expected
    return hmac.new(secret.encode("utf-8"), _COOKIE_CONTEXT, hashlib.sha256).hexdigest()


def _cookie_presented() -> bool:
    """True when the current request carries a valid gate cookie.

    Called from inside the pages-router POST, which has a Flask request
    context. Outside one (tests calling layout() directly, a non-Flask
    backend) there is no cookie and the answer is a plain False.
    """
    expected = _expected_token()
    if not expected:
        return False
    try:
        from flask import has_request_context, request
    except ImportError:  # pragma: no cover - flask is the site's backend
        return False
    if not has_request_context():
        return False
    presented = request.cookies.get(COOKIE_NAME)
    return _matches(presented, cookie_value(expected))


def _remember(expected: str) -> None:
    """Set the gate cookie on the response carrying this render.

    The pages-router POST is same-origin XHR, so the browser stores a cookie
    set on its response exactly as it would on a document response. Failure
    here is never fatal: the page still renders, the reader just keeps
    presenting ?token=.
    """
    try:
        from flask import after_this_request, has_request_context, request
    except ImportError:  # pragma: no cover - flask is the site's backend
        return
    if not has_request_context():
        return

    is_secure = request.is_secure or request.headers.get("X-Forwarded-Proto") == "https"

    @after_this_request
    def _set_cookie(response):
        response.set_cookie(
            COOKIE_NAME,
            cookie_value(expected),
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            secure=is_secure,
            path="/",
        )
        return response


def is_unlocked(**kwargs: Any) -> bool:
    """Decide whether this render may show the dashboard.

    Pass the layout's keyword arguments straight through — Dash puts the
    query string there. Order: a presented ``?token=`` first (and it
    refreshes the cookie), then an existing cookie.
    """
    expected = _expected_token()
    if not expected:
        return False

    if _matches(kwargs.get(QUERY_ARG), expected):
        _remember(expected)
        return True

    return _cookie_presented()
