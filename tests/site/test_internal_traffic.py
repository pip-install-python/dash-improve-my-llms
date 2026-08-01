"""The internal-traffic contract, site side.

2plot network machinery — hub sweeps, smoke batteries, sibling satellites —
identifies itself with the `2plot-internal` UA token, and every tracker on
the network drops those hits AT WRITE TIME, before bot classification.
Otherwise the hub's hourly /healthz sweep alone would dwarf the real traffic
in the /admin demo dashboard.

Also pinned here: the app's ONE short id on every hub surface is `llms` (the
subdomain slug), which is how the hub's network board attributes bulletin
fetches to this site.
"""

from __future__ import annotations

import re

from _helpers import REPO_ROOT
from lib.constants import INTERNAL_UA, INTERNAL_UA_TOKEN, internal_ua

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _total(site_app_module) -> int:
    return site_app_module.load_analytics()["stats"]["total"]


def test_the_internal_ua_is_dropped_at_write_time(site_app_module, site_client):
    """Not classified as a bot, not classified at all — never written."""
    before = _total(site_app_module)
    response = site_client.get("/", user_agent=internal_ua("site-tests"))
    assert response.ok
    assert _total(site_app_module) == before, "a 2plot-internal request reached the visitor ledger"


def test_any_ua_carrying_the_token_is_dropped(site_app_module, site_client):
    """The rule is the TOKEN, not the exact string — a caller suffix or a
    future version bump must not re-admit internal traffic."""
    before = _total(site_app_module)
    site_client.get("/analytics", user_agent=f"curl/8.0 {INTERNAL_UA_TOKEN} sweep")
    assert _total(site_app_module) == before


def test_healthz_is_never_a_visit(site_app_module, site_client):
    """Render probes it on a schedule; so does the hub's hourly sweep."""
    before = _total(site_app_module)
    response = site_client.get("/healthz", user_agent=BROWSER_UA)
    assert response.ok
    assert '"ok"' in response.text or "true" in response.text
    assert _total(site_app_module) == before, "/healthz reached the ledger"


def test_real_traffic_is_still_recorded(site_app_module, site_client):
    """The guard the two tests above need: dropping everything also passes
    them, so prove an ordinary browser hit still lands in the ledger."""
    before = _total(site_app_module)
    site_client.get("/", user_agent=BROWSER_UA)
    assert _total(site_app_module) == before + 1


def test_the_internal_ua_constants_hold_the_contract():
    assert INTERNAL_UA_TOKEN == "2plot-internal"
    assert INTERNAL_UA_TOKEN in INTERNAL_UA
    assert internal_ua("x").startswith(INTERNAL_UA)
    assert INTERNAL_UA_TOKEN in internal_ua()


def test_the_bulletin_app_id_is_the_directory_key():
    """`llms` is this site's key in the hub's directory; the hub's satellite
    table attributes bulletin fetches by it. One short id, everywhere."""
    source = (REPO_ROOT / "app.py").read_text()
    match = re.search(r'app_id="([^"]+)"', source)
    assert match, "configure_bulletin no longer passes an app_id"
    assert match.group(1) == "llms"
