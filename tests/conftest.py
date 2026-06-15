"""
Shared pytest fixtures for the 2.0 test suite.

These fixtures keep individual test files focused on their assertions
without each one having to spin up a Dash app or fake out the
page_registry.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

import pytest


@pytest.fixture
def fake_app() -> SimpleNamespace:
    """A minimal stand-in for a Dash app instance.

    Carries the attributes the 2.0 handlers actually read:
    `_robots_config`, `_base_url`, `title`. Tests can mutate these
    freely.
    """
    return SimpleNamespace(
        title="Test App",
        _base_url="https://example.com",
        _robots_config=None,
    )


@pytest.fixture
def empty_state() -> SimpleNamespace:
    """A fresh `_state`-shaped object for handlers that take one."""
    return SimpleNamespace(
        page_metadata={},
        hidden_pages=set(),
    )


@pytest.fixture
def page_metadata_sample() -> Dict[str, Dict[str, Any]]:
    """A representative page_metadata mapping used across tests."""
    return {
        "/": {
            "name": "Home",
            "description": "Landing page",
            "llms_doc": "# Home\n\nThis is the landing page.",
        },
        "/about": {
            "name": "About",
            "description": "About this app",
            # No llms_doc — exercises the stub-fallback path
        },
        "/admin": {
            "name": "Admin",
            "description": "Hidden admin",
            "llms_doc": "# Admin\n\nShould not appear.",
        },
    }


@pytest.fixture
def fake_page_registry(monkeypatch, page_metadata_sample) -> Dict[str, Dict[str, Any]]:
    """Patch `dash.page_registry` with a small fake set of pages.

    Yields the registry so tests can inspect it. Uses `monkeypatch` so
    the change is reverted at test teardown.
    """
    import dash

    registry = {
        "fake.home": {
            "module": "fake.home",
            "path": "/",
            "name": "Home",
            "relative_path": "/",
        },
        "fake.about": {
            "module": "fake.about",
            "path": "/about",
            "name": "About",
            "relative_path": "/about",
        },
        "fake.admin": {
            "module": "fake.admin",
            "path": "/admin",
            "name": "Admin",
            "relative_path": "/admin",
        },
    }
    monkeypatch.setattr(dash, "page_registry", registry, raising=False)
    return registry
