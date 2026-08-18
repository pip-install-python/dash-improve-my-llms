"""The /admin gate, and the PII floor it backstops.

WHY THIS EXISTS
---------------
``mark_hidden("/admin")`` delists the page — no sitemap entry, a robots.txt
Disallow line, 404 for crawlers and for /admin/llms.txt. It has never been
access control, and robots.txt actively PUBLISHES the path. That was an
acceptable trade while the dashboard rendered throwaway demo rows; it stopped
being one when this host joined the x402 dataset and its ledger moved to a
persistent disk holding real visitor records.

WHY THE TESTS NAVIGATE INSTEAD OF FETCHING
------------------------------------------
A GET of /admin returns the Dash app shell and no dashboard whatsoever — so a
test that only asserts "Total Visits" is absent from that response passes
against a completely ungated page. With Dash Pages the layout arrives from the
pages-router callback: a POST to /_dash-update-component carrying the pathname,
which is the same code path for the direct load and for a dcc.Link navigation.
These tests drive that POST, because it is the request that actually renders
the ledger.
"""

from __future__ import annotations

import json

import pytest

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

TOKEN = "test-admin-token-123"

# Rendered only when the dashboard body runs. Each is unreachable from the
# locked placeholder, which is built from constants.
DASHBOARD_MARKERS = ("Total Visits", "Bot Activity", "Privacy Control Demo")

# Planted in the ledger by `ledger_row`, and distinctive enough that finding
# them in a response can only mean the ledger was read.
PROBE_PATH = "/pii-floor-probe"
PROBE_UA = "GPTBot/1.0 (+pii-floor-probe)"
PROBE_IP = "203.0.113.77"
PROBE_LOCATION = "Reykjavik, Iceland"


@pytest.fixture
def gate_client(site_app):
    """A FRESH client per test.

    Werkzeug's cookie jar lives on the client, and a successful unlock sets a
    cookie. A session-scoped client would carry that cookie into the next test
    and turn every "locked" assertion into a tautology.

    The opening GET doubles as the direct-load check and as what registers the
    pages router (Dash installs the routing callback on the first request).
    """
    client = site_app.server.test_client()
    client.get("/admin", headers={"User-Agent": BROWSER_UA})
    return client


def navigate(client, search: str = "", pathname: str = "/admin") -> str:
    """Render a page the way a browser does: the pages-router callback.

    Mirrors dash.Dash.enable_pages — inputs are the _pages_location pathname
    and search, outputs are the page content and the stored title.
    """
    payload = {
        "output": ".._pages_content.children..._pages_store.data..",
        "outputs": [
            {"id": "_pages_content", "property": "children"},
            {"id": "_pages_store", "property": "data"},
        ],
        "inputs": [
            {"id": "_pages_location", "property": "pathname", "value": pathname},
            {"id": "_pages_location", "property": "search", "value": search},
        ],
        "changedPropIds": ["_pages_location.pathname"],
    }
    response = client.post(
        "/_dash-update-component",
        json=payload,
        headers={"User-Agent": BROWSER_UA},
    )
    assert response.status_code == 200, f"pages router returned {response.status_code}"

    # Dash escapes "/" as \u002f in its JSON responses (XSS hardening), so a
    # plain substring check for a PATH silently passes against a page that
    # renders it — this suite's first draft "proved" the probe row was absent
    # while it was on screen. Round-tripping through json restores the real
    # characters before anything is asserted about them.
    return json.dumps(response.get_json())


def assert_locked(body: str) -> None:
    assert "Authentication required" in body, "the locked placeholder did not render"
    for marker in DASHBOARD_MARKERS:
        assert marker not in body, f"{marker!r} leaked through the gate"
    assert PROBE_PATH not in body and PROBE_UA not in body, "ledger rows leaked through the gate"


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_the_direct_load_never_carries_the_dashboard(gate_client):
    """The shell is not the page, but pin it anyway: a future server-side
    render of page content would have to face this assertion first."""
    body = gate_client.get("/admin", headers={"User-Agent": BROWSER_UA}).get_data().decode()
    for marker in DASHBOARD_MARKERS:
        assert marker not in body


def test_unset_env_var_locks_unconditionally(monkeypatch, gate_client):
    """Production fails closed. A deployment that forgets the secret gets a
    door, not a dashboard."""
    monkeypatch.delenv("ADMIN_DASH_TOKEN", raising=False)
    assert_locked(navigate(gate_client))
    assert_locked(navigate(gate_client, "?token=anything"))


def test_no_token_presented_is_locked(monkeypatch, gate_client):
    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    assert_locked(navigate(gate_client))


def test_a_wrong_token_is_locked(monkeypatch, gate_client):
    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    assert_locked(navigate(gate_client, "?token=" + TOKEN + "x"))
    assert_locked(navigate(gate_client, "?token="))


def test_the_right_token_renders_the_dashboard(monkeypatch, gate_client):
    """The guard the locked tests need: locking everything also passes them."""
    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    body = navigate(gate_client, "?token=" + TOKEN)
    for marker in DASHBOARD_MARKERS:
        assert marker in body, f"{marker!r} missing — the dashboard did not render"


def test_an_unrelated_query_argument_does_not_error(monkeypatch, gate_client):
    """Before the gate, `layout()` took no arguments and Dash calls it with
    the query string — so any ?utm_source= on /admin was a 500."""
    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    assert_locked(navigate(gate_client, "?utm_source=newsletter"))
    body = navigate(gate_client, "?token=" + TOKEN + "&utm_source=newsletter")
    assert "Total Visits" in body


def test_the_cookie_keeps_a_browser_unlocked(monkeypatch, gate_client):
    """Nice-to-have, but it is what makes the page usable: without it, every
    dcc.Link navigation back to /admin would need the token re-pasted."""
    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    navigate(gate_client, "?token=" + TOKEN)

    body = navigate(gate_client)
    assert "Total Visits" in body, "the gate cookie did not survive the navigation"


def test_the_cookie_never_holds_the_token(monkeypatch, gate_client):
    from lib.admin_gate import COOKIE_NAME

    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    navigate(gate_client, "?token=" + TOKEN)

    jar = "; ".join(f"{c.key}={c.value}" for c in gate_client._cookies.values())
    assert COOKIE_NAME in jar, "no gate cookie was set"
    assert TOKEN not in jar, "the raw secret was stored in the browser"


def test_rotating_the_secret_invalidates_the_cookie(monkeypatch, gate_client):
    """The cookie is derived from the secret, so rotation is the revocation
    mechanism — and unsetting it entirely re-locks even a held cookie."""
    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    navigate(gate_client, "?token=" + TOKEN)
    assert "Total Visits" in navigate(gate_client)

    monkeypatch.setenv("ADMIN_DASH_TOKEN", "a-different-secret")
    assert_locked(navigate(gate_client))

    monkeypatch.delenv("ADMIN_DASH_TOKEN", raising=False)
    assert_locked(navigate(gate_client))


def test_is_unlocked_refuses_anything_that_is_not_a_string(monkeypatch):
    """`?token=a&token=b` reaches layout() as a list. Fail closed on shapes
    we did not anticipate rather than coercing them."""
    from lib.admin_gate import is_unlocked

    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    assert is_unlocked(token=TOKEN) is True
    assert is_unlocked(token=[TOKEN, "x"]) is False
    assert is_unlocked(token=None) is False
    assert is_unlocked(token="") is False
    assert is_unlocked() is False

    monkeypatch.setenv("ADMIN_DASH_TOKEN", "   ")
    assert is_unlocked(token="   ") is False, "a whitespace-only secret is not a secret"


# ---------------------------------------------------------------------------
# The PII floor — independent of the gate
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger_row(site_app_module):
    """Plant one bot hit carrying ip_address and location in the ledger.

    Written straight to the tracker's file: track_visit() would classify and
    geolocate, and this fixture needs to control exactly which fields exist.
    The tracker's buffer is flushed first so nothing pending overwrites it.
    """
    from lib.analytics_tracker import tracker
    from datetime import datetime

    tracker.flush()
    path = tracker.data_file
    data = json.loads(path.read_text()) if path.exists() else {"visits": [], "stats": {}}
    data.setdefault("visits", []).append(
        {
            "timestamp": datetime.now().isoformat(),
            "path": PROBE_PATH,
            "user_agent": PROBE_UA,
            "device_type": "bot",
            "bot_type": "training",
            "ip_address": PROBE_IP,
            "location": PROBE_LOCATION,
        }
    )
    path.write_text(json.dumps(data, indent=2))
    return data


def test_the_dashboard_renders_ledger_rows_without_their_pii(monkeypatch, gate_client, ledger_row):
    """The rule, stated as a test: ip_address and location are collected for
    the satellite rollup and never reach the DOM. The probe path proves the
    row WAS rendered, so the absence of the IP is not absence of the row."""
    monkeypatch.setenv("ADMIN_DASH_TOKEN", TOKEN)
    body = navigate(gate_client, "?token=" + TOKEN)

    assert PROBE_PATH in body, "the planted row never reached the dashboard"
    assert PROBE_IP not in body, "an ip_address was rendered"
    assert PROBE_LOCATION not in body, "a location was rendered"
    assert "ip_address" not in body and '"location"' not in body


def test_no_page_renders_ledger_pii(site_page_paths, site_client, ledger_row):
    """Every page, not just /admin — the floor is site-wide."""
    for path in site_page_paths:
        response = site_client.get(path)
        assert PROBE_IP not in response.text, f"{path} rendered an ip_address"
        assert PROBE_LOCATION not in response.text, f"{path} rendered a location"


def test_admin_is_still_delisted(site_client, site_app_module):
    """The gate supplements mark_hidden(); it does not replace it."""
    robots = site_client.get("/robots.txt")
    assert "Disallow: /admin" in robots.text

    sitemap = site_client.get("/sitemap.xml")
    assert "/admin" not in sitemap.text

    from dash_improve_my_llms import is_hidden

    assert is_hidden("/admin") is True
