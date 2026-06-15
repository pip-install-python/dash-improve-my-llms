"""
Test suite for dash-llms-plugin

Run with: pytest test_plugin.py -v
"""

import json

import dash
import pytest
from dash import Dash, dcc, html, register_page


def test_import():
    """Test that the plugin can be imported"""
    from dash_improve_my_llms import (
        LLMSConfig,
        add_llms_routes,
        mark_important,
        register_page_metadata,
    )

    assert add_llms_routes is not None
    assert mark_important is not None
    assert register_page_metadata is not None
    assert LLMSConfig is not None


def test_mark_important():
    """Test marking components as important"""
    from dash_improve_my_llms import is_important, mark_important

    # Mark a component
    component = html.Div([html.H1("Important Header")], id="test-section")

    marked = mark_important(component)

    # Should return the same component
    assert marked == component

    # Should be tracked as important
    assert is_important("test-section")


def test_text_extraction():
    """Test extracting text from components"""
    from dash_improve_my_llms import extract_text_content, mark_important

    # Create a layout with nested components
    layout = html.Div(
        [
            html.H1("Main Title"),
            html.P("Some paragraph text"),
            mark_important(
                html.Div(
                    [
                        html.H2("Important Section"),
                        html.P("Critical information"),
                    ],
                    id="important",
                )
            ),
        ]
    )

    texts = extract_text_content(layout)

    # Should extract all text
    assert len(texts) > 0
    assert any("Main Title" in t for t in texts)
    assert any("Important Section" in t for t in texts)

    # Important sections should be marked
    important_texts = [t for t in texts if t.startswith("[IMPORTANT]")]
    assert len(important_texts) > 0


def test_architecture_extraction():
    """Test extracting component architecture"""
    from dash_improve_my_llms import extract_component_architecture, mark_important

    layout = html.Div(
        [
            html.H1("Title"),
            mark_important(dcc.Dropdown(id="dropdown", options=["A", "B"])),
        ],
        id="root",
    )

    arch = extract_component_architecture(layout)

    # Should have basic structure
    assert arch["type"] == "Div"
    assert arch["id"] == "root"
    assert "children" in arch
    assert arch["children_count"] == 2


def test_llms_txt_generation():
    """Test generating llms.txt content"""
    from dash_improve_my_llms import generate_llms_txt

    def layout():
        return html.Div(
            [
                html.H1("Test Page"),
                html.P("Test content"),
            ]
        )

    result = generate_llms_txt("/test", layout, "Test Page")

    # Should contain required sections
    assert "# Test Page" in result
    assert "## Key Content" in result  # Fixed: Updated section name
    assert "## Application Context" in result  # Fixed: Updated section name
    assert "/test" in result


def test_page_json_generation():
    """Test generating page.json content"""
    from dash_improve_my_llms import generate_page_json

    def layout():
        return html.Div(
            [
                html.H1("Test Page"),
                dcc.Input(id="input1"),
            ],
            id="root",
        )

    result = generate_page_json("/test", layout)

    # Should be valid JSON structure
    assert isinstance(result, dict)
    assert result["path"] == "/test"
    assert "architecture" in result
    assert "metadata" in result

    # Metadata should have counts
    metadata = result["metadata"]
    assert "component_types" in metadata
    # Fixed: total_components is in components.counts, not metadata
    assert "total" in result["components"]["counts"]


def test_component_counting():
    """Test component counting utilities"""
    from dash_improve_my_llms import count_component_types, count_total_components

    arch = {
        "type": "Div",
        "children": [
            {"type": "H1"},
            {"type": "P"},
            {"type": "Div", "children": [{"type": "Input"}]},
        ],
    }

    types = count_component_types(arch)
    assert types["Div"] == 2
    assert types["H1"] == 1
    assert types["Input"] == 1

    total = count_total_components(arch)
    assert total == 5


def test_config():
    """Test LLMSConfig"""
    from dash_improve_my_llms import LLMSConfig

    config = LLMSConfig(enabled=True, max_depth=10, include_css=False)

    assert config.enabled is True
    assert config.max_depth == 10
    assert config.include_css is False


def test_metadata_registration():
    """Test registering page metadata"""
    from dash_improve_my_llms import _page_metadata, register_page_metadata

    register_page_metadata(path="/test", name="Test Page", description="A test page")

    assert "/test" in _page_metadata
    assert _page_metadata["/test"]["name"] == "Test Page"
    assert _page_metadata["/test"]["description"] == "A test page"


def test_nested_importance():
    """Test that importance cascades to children"""
    from dash_improve_my_llms import extract_component_architecture, mark_important

    layout = mark_important(
        html.Div([html.H1("Parent"), html.Div([html.P("Nested child")])], id="parent")
    )

    arch = extract_component_architecture(layout)

    # Parent should be important
    assert arch["important"] is True

    # Children should inherit importance
    def check_children_important(node):
        if isinstance(node, dict):
            if "children" in node:
                for child in node["children"]:
                    if isinstance(child, dict):
                        assert child.get("important", False), "Child should inherit importance"
                        check_children_important(child)

    check_children_important(arch)


def test_depth_calculation():
    """Test calculating component tree depth"""
    from dash_improve_my_llms import calculate_depth

    # Flat structure
    flat = {"type": "Div", "children": [{"type": "P"}]}
    assert calculate_depth(flat) == 1

    # Nested structure
    nested = {
        "type": "Div",
        "children": [{"type": "Div", "children": [{"type": "Div", "children": [{"type": "P"}]}]}],
    }
    assert calculate_depth(nested) == 3


def test_max_depth_limit():
    """Test that extraction respects max_depth"""
    from dash_improve_my_llms import calculate_depth, extract_component_architecture

    # Create a very deep structure
    def create_deep(depth):
        if depth == 0:
            return html.P("Bottom")
        return html.Div([create_deep(depth - 1)])

    deep_layout = create_deep(30)

    # With max_depth=5, should stop early
    arch = extract_component_architecture(deep_layout, max_depth=5)

    # Should not go deeper than 5
    actual_depth = calculate_depth(arch)
    assert actual_depth <= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
