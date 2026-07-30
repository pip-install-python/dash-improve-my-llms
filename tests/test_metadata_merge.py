"""
Regression tests for prose surviving all the way to the rendered page.

Every test here traces back to a live incident: 12 of 14 crawlable pages on
a production site were serving

    <main><p>This page contains interactive content that requires
    JavaScript.</p></main>

on URLs whose prose was demonstrably registered and demonstrably served
correctly at /<page>/llms.txt. Two independent faults combined to erase it,
and each has a test below.
"""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

import dash_improve_my_llms as pkg
from dash_improve_my_llms._paths import normalize_path
from dash_improve_my_llms.handlers import _resolve_llms_doc, resolve_page_context


@pytest.fixture(autouse=True)
def clean_state():
    """Each test gets a pristine registry — module state is process-global."""
    pkg._state.page_metadata.clear()
    pkg._state.hidden_pages.clear()
    yield
    pkg._state.page_metadata.clear()
    pkg._state.hidden_pages.clear()


# ---------------------------------------------------------------------------
# Fault 1: register_page_metadata assigned instead of merging.
# ---------------------------------------------------------------------------


def test_later_registration_does_not_erase_llms_doc():
    """The exact shape of the production bug.

    A page module registers prose at import time; app startup then loops
    over dash.page_registry to backfill titles/descriptions. That second,
    prose-free call must not blank out the first.
    """
    pkg.register_page_metadata("/docs/intro", llms_doc="# Intro\n\nReal prose.")

    pkg.register_page_metadata("/docs/intro", name="Site | Intro", description="An introduction.")

    entry = pkg._state.page_metadata["/docs/intro"]
    assert entry["llms_doc"] == "# Intro\n\nReal prose."
    assert entry["name"] == "Site | Intro"
    assert entry["description"] == "An introduction."


def test_none_never_overwrites_an_existing_value():
    pkg.register_page_metadata("/p", name="Original", description="Original desc")
    pkg.register_page_metadata("/p", name=None, description=None)

    entry = pkg._state.page_metadata["/p"]
    assert entry["name"] == "Original"
    assert entry["description"] == "Original desc"


def test_explicit_empty_string_clears_a_field():
    """Merging must still leave a way to deliberately blank something."""
    pkg.register_page_metadata("/p", llms_doc="# Old")
    pkg.register_page_metadata("/p", llms_doc="")

    assert pkg._state.page_metadata["/p"]["llms_doc"] == ""


def test_kwargs_merge_and_accumulate():
    pkg.register_page_metadata("/p", og_image="/a.png")
    pkg.register_page_metadata("/p", schema_type="Article")

    entry = pkg._state.page_metadata["/p"]
    assert entry["og_image"] == "/a.png"
    assert entry["schema_type"] == "Article"


# ---------------------------------------------------------------------------
# Fault 2: the module-level LLMS_DOC fallback required registry["module"]
# to be an importable module name. Pages registered from a loop pass a
# display name there instead, so the lookup silently found nothing.
# ---------------------------------------------------------------------------


def test_llms_doc_found_via_layout_module_when_module_field_is_a_display_name():
    """dash.register_page("Activity · Cockpit", "/x", ...) — `module` is prose."""
    mod = ModuleType("fake_page_module")
    mod.LLMS_DOC = "# From the module\n\nProse."

    def layout():
        return None

    layout.__module__ = "fake_page_module"
    sys.modules["fake_page_module"] = mod
    try:
        entry = {
            "module": "Activity · Cockpit",  # NOT importable
            "path": "/activity",
            "name": "Activity · Cockpit",
            "layout": layout,
        }
        assert _resolve_llms_doc("/activity", {}, entry) == "# From the module\n\nProse."
    finally:
        del sys.modules["fake_page_module"]


def test_llms_doc_can_ride_along_on_the_registry_entry():
    entry = {"module": "whatever", "path": "/x", "llms_doc": "# Inline\n\nProse."}
    assert _resolve_llms_doc("/x", {}, entry) == "# Inline\n\nProse."


def test_registered_metadata_still_wins_over_module_attribute():
    mod = ModuleType("fake_page_module2")
    mod.LLMS_DOC = "# Module version"
    sys.modules["fake_page_module2"] = mod
    try:
        entry = {"module": "fake_page_module2", "path": "/x"}
        meta = {"/x": {"llms_doc": "# Registered version"}}
        assert _resolve_llms_doc("/x", meta, entry) == "# Registered version"
    finally:
        del sys.modules["fake_page_module2"]


# ---------------------------------------------------------------------------
# Path normalization — registration and lookup must agree.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", "/"),
        ("/", "/"),
        ("docs", "/docs"),
        ("/docs/", "/docs"),
        ("docs/intro/", "/docs/intro"),
        ("/docs?q=1", "/docs"),
        ("/docs#anchor", "/docs"),
        ("https://example.com/docs/", "/docs"),
    ],
)
def test_normalize_path(raw, expected):
    assert normalize_path(raw) == expected


def test_registration_and_lookup_agree_on_trailing_slash():
    pkg.register_page_metadata("/docs/intro/", llms_doc="# Prose")
    assert _resolve_llms_doc("/docs/intro", pkg._state.page_metadata, None) == "# Prose"


def test_mark_hidden_normalizes():
    pkg.mark_hidden("/admin/")
    assert pkg.is_hidden("/admin")
    assert pkg.is_hidden("/admin/")
    assert "/admin" in pkg._state.hidden_pages


# ---------------------------------------------------------------------------
# End to end: prose reaches the rendered context, not just the registry.
# ---------------------------------------------------------------------------


def test_resolve_page_context_carries_prose_after_a_metadata_refresh(monkeypatch, fake_app):
    import dash

    monkeypatch.setattr(
        dash,
        "page_registry",
        {
            "p.intro": {"module": "p.intro", "path": "/docs/intro", "name": "Intro"},
            "p.secret": {"module": "p.secret", "path": "/admin", "name": "Admin"},
        },
        raising=False,
    )

    pkg.register_page_metadata("/docs/intro", llms_doc="# Intro\n\nBody text.")
    pkg.register_page_metadata("/docs/intro", name="Site | Intro")
    pkg.mark_hidden("/admin")

    context = resolve_page_context(
        app=fake_app,
        page_path="/docs/intro",
        page_metadata=pkg._state.page_metadata,
        hidden_paths=pkg._state.hidden_pages,
    )

    assert context is not None
    assert context["page_metadata"]["llms_doc"] == "# Intro\n\nBody text."
    assert context["page_metadata"]["name"] == "Site | Intro"
    # Hidden pages stay out of the sibling nav.
    assert [p["path"] for p in context["all_pages"]] == ["/docs/intro"]
