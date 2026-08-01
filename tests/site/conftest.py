"""Fixtures for the DOCS-SITE tests (app.py + pages/ + lib/), not the package.

These boot the real `app.py` — registration order, the index_string dedup
rule, and whether every register_page passed `image_url=` only exist in the
wiring, so a stripped-down test app would test the wrong thing.

WHY THIS DIRECTORY, AND WHY IT MUST SORT BEFORE tests/test_*.py
---------------------------------------------------------------
Importing app.py necessarily mutates the package's module-level `_state`
(register_network, mark_hidden, every register_page_metadata) and fills
`dash.page_registry`. The package unit tests OWN that state: several reset it
wholesale (`test_adapters._reset_package_state`, `test_metadata_merge
.clean_state`, `test_access`), which would strip the site's registered prose
out from under a session-scoped app fixture. pytest collects directories
before same-level files in name order, so `tests/site/` ("s") runs before
every `tests/test_*.py` ("t") — the site suite sees the app exactly as booted,
and the package suites are already written to reset whatever we leave behind.

SECRETLESS, AND ORDER MATTERS. The env block below runs at import time,
before anything loads app.py: the analytics ledger goes to a temp dir (so the
suite never appends its own hits to the checked-out visitor_analytics.json),
the bulletin URL is pinned empty (no outbound fetch from a test run), and
APP_BASE_URL is cleared so lib.constants resolves the real production origin
deterministically regardless of the developer's shell.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

# The package's CI matrix installs ONLY the package's deps (dash + the pinned
# version under test — that is what the matrix exists to prove) and must keep
# meaning exactly the 289-test package suite. The docs site needs its own
# requirements.txt on top; dash-mantine-components is the import that tells
# the two environments apart, so its absence skips this whole directory at
# collection time instead of failing nine matrix jobs at setup. The site
# suite is still ENFORCED — ci.yml's dedicated `site` job installs
# requirements.txt and runs `pytest tests/site` on every PR.
pytest.importorskip(
    "dash_mantine_components",
    reason="site suite needs the docs site's requirements.txt (dash-mantine-components)",
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

_TMP_STATE = tempfile.mkdtemp(prefix="llms-site-tests-")
os.environ["VISITOR_ANALYTICS_FILE"] = os.path.join(_TMP_STATE, "visitor_analytics.json")
os.environ["NETWORK_BULLETIN_URL"] = ""
os.environ.pop("APP_BASE_URL", None)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# What a real browser sends. `/<page>/llms.txt` negotiates on this header —
# it is what separates "a person opened the URL" from "an agent fetched it".
BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


@pytest.fixture(scope="session")
def site_app_module():
    """Import app.py as a module, from the repo root.

    Dash resolves the pages/ and assets/ folders relative to the module and
    the process CWD, so the CWD has to be the repo root regardless of where
    pytest was invoked from.
    """
    os.chdir(REPO_ROOT)
    spec = importlib.util.spec_from_file_location("site_app", REPO_ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["site_app"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def site_app(site_app_module):
    return site_app_module.app


class Response:
    __slots__ = ("status", "text")

    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self.text = text

    @property
    def ok(self) -> bool:
        return self.status == 200


class Client:
    """Werkzeug test client with the browser posture baked in.

    The decode is lenient (`errors="replace"`) so a test that merely checks a
    PNG icon or the favicon RESOLVES doesn't blow up on the file's first
    non-UTF-8 byte. Nothing here reads binary content — the one check that
    needs real PNG bytes (the local card render) opens the file directly.
    """

    def __init__(self, raw) -> None:
        self._raw = raw

    def get(self, path: str, user_agent: str = BROWSER_UA, accept: str = None) -> Response:
        headers = {"User-Agent": user_agent}
        if accept is not None:
            headers["Accept"] = accept
        r = self._raw.get(path, headers=headers)
        return Response(r.status_code, r.get_data().decode("utf-8", "replace"))


@pytest.fixture(scope="session")
def site_client(site_app):
    return Client(site_app.server.test_client())


@pytest.fixture(scope="session")
def site_page_paths(site_app_module):
    import dash

    return sorted(entry["path"] for entry in dash.page_registry.values())
