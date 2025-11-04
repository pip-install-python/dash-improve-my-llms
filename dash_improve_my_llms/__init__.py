"""
Dash LLMS Plugin - Automatic llms.txt and page.json generation for Dash apps

This plugin automatically generates two types of metadata for each page:
1. llms.txt - Content-focused description for LLM understanding
2. page.json - Architecture-focused technical description

Usage:
    from dash_llms_plugin import add_llms_routes

    app = Dash(__name__, use_pages=True)
    add_llms_routes(app)
"""

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from dash import callback_context, dcc, hooks, html
from flask import Response, jsonify

# Global registry to track important components
_important_components = set()
_page_metadata = {}

# Global registry to track hidden pages/components
_hidden_pages = set()
_hidden_components = set()


class LLMSConfig:
    """Configuration for LLMS plugin"""

    def __init__(
        self,
        enabled: bool = True,
        auto_detect_pages: bool = True,
        include_css: bool = True,
        include_callbacks: bool = True,
        max_depth: int = 20,
        exclude_patterns: Optional[List[str]] = None,
    ):
        self.enabled = enabled
        self.auto_detect_pages = auto_detect_pages
        self.include_css = include_css
        self.include_callbacks = include_callbacks
        self.max_depth = max_depth
        self.exclude_patterns = exclude_patterns or []


def mark_important(component, component_id: Optional[str] = None):
    """
    Mark a component as important for LLM context.
    All children of this component will automatically be considered important.

    Args:
        component: Dash component to mark as important
        component_id: Optional ID to track this component

    Returns:
        The same component (for chaining)

    Example:
        html.Div([
            mark_important(
                html.Div([
                    html.H1("Important Section"),
                    dcc.Dropdown(...)
                ], id="main-content")
            )
        ])
    """
    if hasattr(component, "id") and component.id:
        _important_components.add(component.id)
    elif component_id:
        _important_components.add(component_id)

    return component


def is_important(component_id: str) -> bool:
    """Check if a component or its parent is marked as important"""
    return component_id in _important_components


def mark_hidden(page_path: str):
    """
    Mark a page as hidden from AI bots, LLMs, and search engines.

    Hidden pages will be:
    - Excluded from sitemap.xml
    - Blocked in robots.txt
    - Not accessible via /llms.txt or /page.json routes

    Args:
        page_path: Path of the page to hide (e.g., "/admin", "/private")

    Returns:
        None

    Example:
        # Hide admin pages from AI crawlers
        mark_hidden("/admin")
        mark_hidden("/settings")
        mark_hidden("/internal-tools")
    """
    _hidden_pages.add(page_path)


def is_hidden(page_path: str) -> bool:
    """
    Check if a page is marked as hidden from AI bots.

    Args:
        page_path: Path of the page to check

    Returns:
        True if the page is hidden, False otherwise
    """
    return page_path in _hidden_pages


def mark_component_hidden(component, component_id: Optional[str] = None):
    """
    Mark a component as hidden from AI extraction.

    This is useful for sensitive information that should not be
    included in llms.txt or page.json output.

    Args:
        component: Dash component to mark as hidden
        component_id: Optional ID to track this component

    Returns:
        The same component (for chaining)

    Example:
        html.Div([
            mark_component_hidden(
                html.Div([
                    html.P("Sensitive internal information"),
                    html.P("API keys, passwords, etc.")
                ], id="sensitive-data")
            )
        ])
    """
    if hasattr(component, "id") and component.id:
        _hidden_components.add(component.id)
    elif component_id:
        _hidden_components.add(component_id)

    return component


def is_component_hidden(component_id: str) -> bool:
    """Check if a component is marked as hidden"""
    return component_id in _hidden_components


def extract_text_content(
    component, is_important_section: bool = False, depth: int = 0, max_depth: int = 20
) -> List[str]:
    """
    Extract readable text content from a component tree.

    Args:
        component: Dash component to extract text from
        is_important_section: Whether this component is in an important section
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        List of text strings found in the component
    """
    if depth > max_depth:
        return []

    texts = []

    # Check if this component is marked as important
    if hasattr(component, "id") and component.id:
        is_important_section = is_important_section or is_important(component.id)

    # Extract direct text content
    if isinstance(component, str):
        text = component.strip()
        if text:
            prefix = "[IMPORTANT] " if is_important_section else ""
            texts.append(f"{prefix}{text}")
        return texts

    # Handle different component types
    component_name = (
        component.__class__.__name__ if hasattr(component, "__class__") else str(type(component))
    )

    # Extract from children
    if hasattr(component, "children"):
        children = component.children
        if children is not None:
            if isinstance(children, list):
                for child in children:
                    texts.extend(
                        extract_text_content(child, is_important_section, depth + 1, max_depth)
                    )
            else:
                texts.extend(
                    extract_text_content(children, is_important_section, depth + 1, max_depth)
                )

    # Extract from specific properties based on component type
    if component_name in ["H1", "H2", "H3", "H4", "H5", "H6"]:
        prefix = "[IMPORTANT] " if is_important_section else ""
        if hasattr(component, "children") and isinstance(component.children, str):
            texts.insert(0, f"{prefix}## {component.children}")

    # Extract labels, placeholders, titles
    for prop in ["label", "placeholder", "title", "value"]:
        if hasattr(component, prop):
            val = getattr(component, prop)
            if isinstance(val, str) and val.strip():
                prefix = "[IMPORTANT] " if is_important_section else ""
                texts.append(f"{prefix}{val}")

    return texts


def extract_component_architecture(
    component, depth: int = 0, max_depth: int = 20, parent_important: bool = False
) -> Dict:
    """
    Extract architectural information about components.

    Args:
        component: Dash component to analyze
        depth: Current recursion depth
        max_depth: Maximum recursion depth
        parent_important: Whether parent was marked important

    Returns:
        Dictionary describing component architecture
    """
    # Fix off-by-one error: use >= instead of >
    if depth >= max_depth:
        return {"error": "max_depth_exceeded"}

    if isinstance(component, str):
        # Fix: Include importance flag for text nodes
        return {
            "type": "text",
            "content": component[:100],
            "important": parent_important,
        }

    info = {}
    component_name = (
        component.__class__.__name__ if hasattr(component, "__class__") else str(type(component))
    )
    info["type"] = component_name
    info["module"] = component.__module__ if hasattr(component, "__module__") else None

    # Check if marked important
    is_important_comp = parent_important
    if hasattr(component, "id") and component.id:
        info["id"] = component.id
        is_important_comp = is_important_comp or is_important(component.id)

    info["important"] = is_important_comp

    # Extract key properties
    props = {}
    if hasattr(component, "__dict__"):
        for key, value in component.__dict__.items():
            if key.startswith("_"):
                continue
            if key in ["children"]:
                continue
            if isinstance(value, (str, int, float, bool, type(None))):
                props[key] = value
            elif isinstance(value, dict):
                props[key] = {
                    k: v
                    for k, v in value.items()
                    if isinstance(v, (str, int, float, bool, type(None)))
                }
            elif isinstance(value, list) and len(value) < 10:
                props[key] = [
                    v for v in value if isinstance(v, (str, int, float, bool, type(None)))
                ]

    if props:
        info["props"] = props

    # Process children
    if hasattr(component, "children") and component.children is not None:
        children = component.children
        if isinstance(children, list):
            info["children"] = [
                extract_component_architecture(child, depth + 1, max_depth, is_important_comp)
                for child in children
            ]
            info["children_count"] = len(children)
        else:
            info["children"] = [
                extract_component_architecture(children, depth + 1, max_depth, is_important_comp)
            ]
            info["children_count"] = 1

    return info


def generate_llms_txt(
    page_path: str, layout_func, page_name: Optional[str] = None, app=None
) -> str:
    """
    Generate comprehensive llms.txt content for a page.
    Uses architecture.txt and page.json data to provide complete context.

    Args:
        page_path: URL path of the page
        layout_func: Function or component that returns the page layout
        page_name: Optional display name for the page
        app: Optional Dash app instance for extracting app context

    Returns:
        llms.txt formatted string with comprehensive context
    """
    # Get the layout
    if callable(layout_func):
        try:
            layout = layout_func()
        except Exception as e:
            layout = html.Div(f"Error loading layout: {str(e)}")
    else:
        layout = layout_func

    # Generate page.json data for context
    page_data = generate_page_json(page_path, layout_func, app)

    # Extract text content
    text_content = extract_text_content(layout)

    # Build comprehensive llms.txt
    output = []

    # ===== HEADER =====
    title = page_name or page_path.strip("/").replace("-", " ").title() or "Home"
    output.append(f"# {title}\n\n")

    # Description
    description = page_data.get("description", f"This page is accessible at {page_path}")
    output.append(f"> {description}\n\n")

    output.append("---\n\n")

    # ===== APPLICATION CONTEXT =====
    output.append("## Application Context\n\n")

    # Get app-level context if available
    if app:
        try:
            import dash

            page_registry = dash.page_registry if hasattr(dash, "page_registry") else {}
            total_pages = len(page_registry)

            output.append(
                f"This page is part of a multi-page Dash application with {total_pages} total pages.\n\n"
            )

            # List other pages for context
            if total_pages > 1:
                other_pages = [p for p in page_registry.values() if p.get("path") != page_path]
                if other_pages:
                    output.append("**Related Pages:**\n")
                    for p in other_pages[:5]:  # Limit to 5 to avoid too much content
                        p_name = p.get("name", "Unknown")
                        p_path = p.get("path", "/")
                        output.append(f"- {p_name} (`{p_path}`)\n")
                    output.append("\n")
        except:
            pass
    else:
        output.append(f"This is a page within a Dash application.\n\n")

    # ===== PAGE PURPOSE =====
    output.append("## Page Purpose\n\n")

    # Analyze page metadata to describe purpose
    metadata = page_data.get("metadata", {})
    components = page_data.get("components", {})

    purposes = []
    if metadata.get("contains_forms"):
        purposes.append("**Data Input**: Contains form elements for user data entry")
    if metadata.get("contains_visualizations"):
        purposes.append("**Data Visualization**: Displays charts, graphs, or tables")
    if metadata.get("contains_navigation"):
        purposes.append("**Navigation**: Provides links to other sections of the application")
    if page_data.get("interactivity", {}).get("has_callbacks"):
        purposes.append("**Interactive**: Responds to user interactions with dynamic updates")

    if purposes:
        for purpose in purposes:
            output.append(f"- {purpose}\n")
        output.append("\n")
    else:
        output.append("This page displays static content.\n\n")

    # ===== INTERACTIVE ELEMENTS =====
    interactivity = page_data.get("interactivity", {})
    if interactivity.get("has_callbacks") or interactivity.get("interactive_components", 0) > 0:
        output.append("## Interactive Elements\n\n")

        interactive_count = interactivity.get("interactive_components", 0)
        callback_count = interactivity.get("callback_count", 0)

        output.append(f"This page contains **{interactive_count} interactive components** ")
        output.append(f"with **{callback_count} callback(s)** that respond to user actions.\n\n")

        # Describe input/output flow
        categories = components.get("categories", {})

        if "inputs" in categories and categories["inputs"]:
            output.append("**User Inputs:**\n")
            comp_ids = components.get("ids", {})
            for input_id in categories["inputs"][:10]:  # Limit to 10
                if input_id in comp_ids:
                    comp_info = comp_ids[input_id]
                    comp_type = comp_info.get("type", "Component")
                    output.append(f"- {comp_type}")
                    if input_id:
                        output.append(f" (ID: `{input_id}`)")
                    props = comp_info.get("props", {})
                    if "placeholder" in props:
                        output.append(f" - {props['placeholder']}")
                    output.append("\n")
            output.append("\n")

        if "outputs" in categories and categories["outputs"]:
            output.append("**Data Outputs:**\n")
            comp_ids = components.get("ids", {})
            for output_id in categories["outputs"][:10]:
                if output_id in comp_ids:
                    comp_info = comp_ids[output_id]
                    comp_type = comp_info.get("type", "Component")
                    output.append(f"- {comp_type}")
                    if output_id:
                        output.append(f" (ID: `{output_id}`)")
                    output.append("\n")
            output.append("\n")

    # ===== KEY CONTENT =====
    output.append("## Key Content\n\n")

    # Separate important and regular content
    important_content = [t for t in text_content if t.startswith("[IMPORTANT]")]
    regular_content = [t for t in text_content if not t.startswith("[IMPORTANT]")]

    if important_content:
        output.append("**Primary Information (marked as important):**\n")
        for text in important_content[:30]:  # Increased limit for important content
            clean_text = text.replace("[IMPORTANT] ", "").strip()
            if clean_text and not clean_text.startswith("##"):
                output.append(f"- {clean_text}\n")
        output.append("\n")

    if regular_content:
        output.append("**Additional Content:**\n")
        displayed_content = []
        for text in regular_content:
            clean_text = text.strip()
            if clean_text and len(clean_text) > 1 and not clean_text.startswith("##"):
                displayed_content.append(clean_text)
                if len(displayed_content) >= 25:  # Limit to prevent overwhelming output
                    break

        for text in displayed_content:
            output.append(f"- {text}\n")

        if len(regular_content) > len(displayed_content):
            output.append(
                f"\n*... and {len(regular_content) - len(displayed_content)} more items*\n"
            )

        output.append("\n")

    # ===== NAVIGATION & LINKS =====
    navigation = page_data.get("navigation", {})
    links = navigation.get("links", [])

    # Initialize link lists before using them (fix for variable scope)
    internal_links = []
    external_links = []

    if links:
        output.append("## Navigation\n\n")

        internal_links = [l for l in links if l.get("href", "").startswith("/")]
        external_links = [
            l for l in links if not l.get("href", "").startswith("/") and l.get("href")
        ]

        if internal_links:
            output.append("**Internal Links:**\n")
            for link in internal_links[:10]:
                link_text = link.get("text", link.get("href", "Link"))
                link_href = link.get("href", "")
                output.append(f"- {link_text} → `{link_href}`\n")
            output.append("\n")

        if external_links:
            output.append("**External Links:**\n")
            for link in external_links[:5]:
                link_text = link.get("text", link.get("href", "Link"))
                link_href = link.get("href", "")
                output.append(f"- {link_text} → `{link_href}`\n")
            output.append("\n")

    # ===== COMPONENT BREAKDOWN =====
    output.append("## Component Breakdown\n\n")

    comp_counts = components.get("counts", {})
    total_comps = comp_counts.get("total", 0)
    interactive_comps = comp_counts.get("interactive", 0)
    static_comps = comp_counts.get("static", 0)

    output.append(f"**Total Components**: {total_comps}\n")
    output.append(f"- Interactive: {interactive_comps}\n")
    output.append(f"- Static/Display: {static_comps}\n\n")

    # Component type distribution
    comp_types = components.get("types", {})
    if comp_types:
        output.append("**Component Types:**\n")
        sorted_types = sorted(comp_types.items(), key=lambda x: x[1], reverse=True)[:15]
        for comp_type, count in sorted_types:
            if comp_type != "text":  # Skip text nodes for clarity
                output.append(f"- {comp_type}: {count}\n")
        output.append("\n")

    # ===== DATA FLOW & CALLBACKS =====
    if "callbacks" in page_data:
        callbacks = page_data["callbacks"]
        callback_list = callbacks.get("list", [])

        if callback_list:
            output.append("## Data Flow & Callbacks\n\n")
            output.append(
                f"This page has **{len(callback_list)} callback(s)** that handle user interactions:\n\n"
            )

            for i, cb in enumerate(callback_list[:10], 1):  # Limit to 10 callbacks
                output.append(f"**Callback {i}:**\n")
                output.append(f"- Updates: `{cb.get('output', 'Unknown')}`\n")

                inputs = cb.get("inputs", [])
                if inputs:
                    output.append(f"- Triggered by: {', '.join(f'`{inp}`' for inp in inputs)}\n")

                state = cb.get("state", [])
                if state:
                    output.append(f"- Uses state from: {', '.join(f'`{st}`' for st in state)}\n")

                output.append("\n")

            if len(callback_list) > 10:
                output.append(f"*... and {len(callback_list) - 10} more callback(s)*\n\n")

    # ===== PAGE METADATA =====
    output.append("## Technical Details\n\n")
    output.append(f"- **Path**: `{page_path}`\n")
    output.append(f"- **Max Component Depth**: {metadata.get('max_depth', 0)}\n")
    output.append(
        f"- **Has Important Sections**: {'Yes' if metadata.get('has_important_sections') else 'No'}\n"
    )
    output.append(f"- **Full Architecture**: Available at `{page_path}/page.json`\n")
    output.append(f"- **Global App Architecture**: Available at `/architecture.txt`\n\n")

    # ===== SUMMARY =====
    output.append("---\n\n")
    output.append("## Summary\n\n")

    # Generate a narrative summary
    summary_parts = []

    summary_parts.append(f"The **{title}** page")

    if description and description != f"This page is accessible at {page_path}":
        summary_parts.append(f"{description.lower() if description[0].isupper() else description}.")
    else:
        summary_parts.append(f"is accessible at `{page_path}`.")

    if interactive_comps > 0:
        summary_parts.append(
            f"It contains {interactive_comps} interactive component(s) that allow "
            f"users to input data and trigger {callback_count} callback(s)."
        )

    if metadata.get("contains_visualizations"):
        summary_parts.append("The page displays visualizations to present data to users.")

    if len(internal_links) > 0:
        summary_parts.append(
            f"Users can navigate to {len(internal_links)} other page(s) from here."
        )

    output.append(" ".join(summary_parts))
    output.append("\n\n")

    output.append("---\n\n")
    output.append("*Generated with https://pip-install-python.com | dash-improve-my-llms hook*\n")
    output.append("Pip Install Python LLC | https://plotly.pro\n")

    return "".join(output)


def extract_component_ids(arch: Dict, component_ids: Optional[Dict] = None) -> Dict[str, Dict]:
    """Extract all component IDs and their information"""
    if component_ids is None:
        component_ids = {}

    def extract_recursive(node, parent_id=None):
        if isinstance(node, dict):
            comp_id = node.get("id")
            comp_type = node.get("type")

            if comp_id:
                component_ids[comp_id] = {
                    "type": comp_type,
                    "module": node.get("module"),
                    "important": node.get("important", False),
                    "parent": parent_id,
                    "props": node.get("props", {}),
                }

            # Process children
            if "children" in node and isinstance(node["children"], list):
                for child in node["children"]:
                    extract_recursive(child, comp_id)

    extract_recursive(arch)
    return component_ids


def categorize_components(arch: Dict) -> Dict[str, List[str]]:
    """Categorize components by their purpose"""
    categories = {
        "inputs": [],
        "outputs": [],
        "containers": [],
        "display": [],
        "navigation": [],
        "interactive": [],
    }

    input_types = {
        "Input",
        "TextInput",
        "Textarea",
        "Select",
        "Dropdown",
        "RadioItems",
        "Checklist",
        "Slider",
        "RangeSlider",
        "DatePicker",
    }
    output_types = {"Graph", "Table", "DataTable"}
    container_types = {"Div", "Container", "Stack", "Group", "Grid", "Paper", "Card"}
    nav_types = {"Link", "NavLink", "Tabs", "Tab"}
    interactive_types = {"Button", "Switch", "Checkbox", "Radio"}

    def categorize_recursive(node):
        if isinstance(node, dict):
            comp_type = node.get("type")
            comp_id = node.get("id")

            if comp_type in input_types:
                categories["inputs"].append(comp_id or f"{comp_type}-{id(node)}")
            if comp_type in output_types:
                categories["outputs"].append(comp_id or f"{comp_type}-{id(node)}")
            if comp_type in container_types:
                categories["containers"].append(comp_id or f"{comp_type}-{id(node)}")
            if comp_type in nav_types:
                categories["navigation"].append(comp_id or f"{comp_type}-{id(node)}")
            if comp_type in interactive_types or comp_type in input_types:
                categories["interactive"].append(comp_id or f"{comp_type}-{id(node)}")
            if comp_type not in (
                input_types | output_types | container_types | nav_types | interactive_types
            ):
                categories["display"].append(comp_id or f"{comp_type}-{id(node)}")

            if "children" in node and isinstance(node["children"], list):
                for child in node["children"]:
                    categorize_recursive(child)

    categorize_recursive(arch)
    return {k: v for k, v in categories.items() if v}  # Only include non-empty categories


def extract_page_links(arch: Dict) -> List[Dict[str, str]]:
    """Extract all links to other pages"""
    links = []

    def extract_recursive(node):
        if isinstance(node, dict):
            comp_type = node.get("type")

            if comp_type in ["Link", "NavLink", "A"]:
                props = node.get("props", {})
                href = props.get("href", "")
                if href:
                    link_info = {"href": href, "type": comp_type}

                    # Try to extract link text
                    children = node.get("children", [])
                    if children and isinstance(children, list):
                        for child in children:
                            if isinstance(child, dict) and child.get("type") == "text":
                                link_info["text"] = child.get("content", "")
                                break

                    links.append(link_info)

            if "children" in node and isinstance(node["children"], list):
                for child in node["children"]:
                    extract_recursive(child)

    extract_recursive(arch)
    return links


def generate_page_json(page_path: str, layout_func, app=None) -> Dict:
    """
    Generate comprehensive page.json content for a page.
    Includes architecture, callbacks, interactivity, and data flow information.

    Args:
        page_path: URL path of the page
        layout_func: Function or component that returns the page layout
        app: Optional Dash app instance for callback extraction

    Returns:
        Dictionary with comprehensive page architecture information
    """
    # Get the layout
    if callable(layout_func):
        try:
            layout = layout_func()
        except Exception as e:
            layout = html.Div(f"Error loading layout: {str(e)}")
    else:
        layout = layout_func

    # Extract architecture
    architecture = extract_component_architecture(layout)

    # Extract component IDs
    component_ids = extract_component_ids(architecture)

    # Categorize components
    component_categories = categorize_components(architecture)

    # Extract page links
    page_links = extract_page_links(architecture)

    # Extract callbacks related to this page
    callbacks_info = []
    callback_graph = {}

    if app and hasattr(app, "callback_map"):
        try:
            for output_id, callback_data in app.callback_map.items():
                # Check if any component in this callback belongs to this page
                # This is a simple heuristic - in production you might want more sophisticated matching
                if isinstance(callback_data, dict):
                    callback_info = {
                        "output": str(output_id),
                        "inputs": [],
                        "state": [],
                    }

                    # Try to extract inputs and state
                    if "inputs" in callback_data:
                        inputs = callback_data["inputs"]
                        if isinstance(inputs, list):
                            callback_info["inputs"] = [str(inp) for inp in inputs]
                        else:
                            callback_info["inputs"] = [str(inputs)]

                    if "state" in callback_data:
                        state = callback_data["state"]
                        if isinstance(state, list):
                            callback_info["state"] = [str(st) for st in state]
                        else:
                            callback_info["state"] = [str(state)]

                    callbacks_info.append(callback_info)

                    # Build callback graph
                    output_str = str(output_id)
                    if output_str not in callback_graph:
                        callback_graph[output_str] = {"triggers": [], "updates": []}

                    for inp in callback_info["inputs"]:
                        callback_graph[output_str]["triggers"].append(inp)

        except Exception:
            # If callback extraction fails, continue without it
            pass

    # Count component types
    comp_types = count_component_types(architecture)

    # Count interactive vs static components
    interactive_types = {
        "Input",
        "TextInput",
        "Select",
        "Dropdown",
        "Button",
        "Checkbox",
        "Radio",
        "Slider",
        "Switch",
        "Textarea",
        "DatePicker",
    }
    interactive_count = sum(comp_types.get(t, 0) for t in interactive_types)
    static_count = count_total_components(architecture) - interactive_count

    # Build comprehensive page.json
    page_info = {
        "path": page_path,
        "name": _page_metadata.get(page_path, {}).get("name", page_path),
        "description": _page_metadata.get(page_path, {}).get("description", ""),
        "architecture": architecture,
        "components": {
            "ids": component_ids,
            "categories": component_categories,
            "types": comp_types,
            "counts": {
                "total": count_total_components(architecture),
                "interactive": interactive_count,
                "static": static_count,
                "unique_types": len(comp_types),
            },
        },
        "interactivity": {
            "has_callbacks": len(callbacks_info) > 0,
            "callback_count": len(callbacks_info),
            "interactive_components": interactive_count,
            "inputs": component_categories.get("inputs", []),
            "outputs": component_categories.get("outputs", []),
        },
        "navigation": {
            "links": page_links,
            "outbound_count": len([l for l in page_links if l.get("href", "").startswith("/")]),
            "external_count": len([l for l in page_links if not l.get("href", "").startswith("/")]),
        },
        "metadata": {
            "has_important_sections": has_important_sections(architecture),
            "max_depth": calculate_depth(architecture),
            "contains_forms": any(
                t in comp_types for t in ["Input", "TextInput", "Select", "Dropdown"]
            ),
            "contains_visualizations": any(
                t in comp_types for t in ["Graph", "Table", "DataTable"]
            ),
            "contains_navigation": len(page_links) > 0,
            "component_types": comp_types,  # Add component types to metadata
        },
    }

    # Add callbacks if found
    if callbacks_info:
        page_info["callbacks"] = {"list": callbacks_info, "graph": callback_graph}

    return page_info


def count_component_types(arch: Dict) -> Dict[str, int]:
    """Count occurrences of each component type"""
    counts = defaultdict(int)

    def count_recursive(node):
        if isinstance(node, dict) and "type" in node:
            counts[node["type"]] += 1
            if "children" in node and isinstance(node["children"], list):
                for child in node["children"]:
                    count_recursive(child)

    count_recursive(arch)
    return dict(counts)


def count_total_components(arch: Dict) -> int:
    """Count total number of components"""
    count = 0

    def count_recursive(node):
        nonlocal count
        if isinstance(node, dict):
            count += 1
            if "children" in node and isinstance(node["children"], list):
                for child in node["children"]:
                    count_recursive(child)

    count_recursive(arch)
    return count


def has_important_sections(arch: Dict) -> bool:
    """Check if architecture has any important sections"""

    def check_recursive(node):
        if isinstance(node, dict):
            if node.get("important", False):
                return True
            if "children" in node and isinstance(node["children"], list):
                return any(check_recursive(child) for child in node["children"])
        return False

    return check_recursive(arch)


def calculate_depth(arch: Dict, current_depth: int = 0) -> int:
    """Calculate maximum depth of component tree"""
    if not isinstance(arch, dict):
        return current_depth

    if "children" in arch and isinstance(arch["children"], list):
        if not arch["children"]:
            return current_depth
        return max(calculate_depth(child, current_depth + 1) for child in arch["children"])

    return current_depth


def register_page_metadata(path: str, name: str = None, description: str = None, **kwargs):
    """
    Register metadata for a page.

    Args:
        path: Page path
        name: Display name
        description: Page description
        **kwargs: Additional metadata
    """
    _page_metadata[path] = {"name": name, "description": description, **kwargs}


def generate_architecture_txt(app) -> str:
    """
    Generate comprehensive ASCII art representation of the entire application architecture.
    Includes dependencies, callbacks, pages, routes, and statistics.

    Returns:
        ASCII art string showing complete app structure
    """
    import os
    import sys
    from pathlib import Path

    import dash

    output = []
    output.append("=" * 80)
    output.append("DASH APPLICATION ARCHITECTURE".center(80))
    output.append("=" * 80)
    output.append("")

    # Environment & Dependencies
    output.append("┌─ ENVIRONMENT")
    output.append("│")
    output.append(f"├─── Python Version: {sys.version.split()[0]}")

    # Get Dash version
    try:
        output.append(f"├─── Dash Version: {dash.__version__}")
    except:
        output.append(f"├─── Dash Version: Unknown")

    # Get key dependencies
    dependencies = []
    try:
        import dash_mantine_components

        dependencies.append(f"dash-mantine-components=={dash_mantine_components.__version__}")
    except:
        pass

    try:
        import plotly

        dependencies.append(f"plotly=={plotly.__version__}")
    except:
        pass

    try:
        import pandas

        dependencies.append(f"pandas=={pandas.__version__}")
    except:
        pass

    if dependencies:
        output.append(f"├─── Key Dependencies:")
        for i, dep in enumerate(dependencies):
            is_last = i == len(dependencies) - 1
            prefix = "└───" if is_last else "├───"
            output.append(f"│    {prefix} {dep}")
    else:
        output.append(f"├─── Key Dependencies: None detected")

    output.append("│")

    # App info
    output.append("├─ APPLICATION")
    output.append("│")
    output.append(f"├─── Name: {app.title if hasattr(app, 'title') else 'Dash App'}")
    output.append(f"├─── Server: {app.server.name if hasattr(app.server, 'name') else 'Flask'}")

    # Detect if using pages
    page_registry = dash.page_registry if hasattr(dash, "page_registry") else {}
    output.append(f"├─── Multi-Page: {'Yes' if page_registry else 'No'}")
    output.append(
        f"├─── Suppress Callback Exceptions: {app.config.get('suppress_callback_exceptions', False)}"
    )
    output.append("│")

    # Callbacks info
    output.append("├─ CALLBACKS")
    output.append("│")
    callback_count = 0
    callback_map = defaultdict(list)

    # Try to get callback information
    try:
        if hasattr(app, "callback_map"):
            callback_count = len(app.callback_map)
            # Group callbacks by page module
            for output_id, callback_info in app.callback_map.items():
                # Extract module from callback function if possible
                if hasattr(callback_info, "get") and "callback" in callback_info:
                    callback_func = callback_info.get("callback")
                    if hasattr(callback_func, "__module__"):
                        module = callback_func.__module__
                        callback_map[module].append(output_id)
    except:
        pass

    output.append(f"├─── Total Callbacks: {callback_count}")

    if callback_map:
        output.append(f"├─── By Module:")
        modules = list(callback_map.items())
        for i, (module, outputs) in enumerate(modules):
            is_last = i == len(modules) - 1
            prefix = "└───" if is_last else "├───"
            output.append(f"│    {prefix} {module}: {len(outputs)} callback(s)")

    output.append("│")

    # Pages structure
    if page_registry:
        output.append("├─ PAGES")
        pages = list(page_registry.values())

        for i, page in enumerate(pages):
            is_last_page = i == len(pages) - 1
            prefix = "└──" if is_last_page else "├──"

            page_name = page.get("name", "Unknown")
            page_path = page.get("path", "/")
            page_module = page.get("module", "N/A")

            output.append(f"│  {prefix} {page_name}")
            output.append(f"│      ├─ Path: {page_path}")
            output.append(f"│      ├─ Module: {page_module}")

            # Check if page has metadata
            if page_path in _page_metadata:
                metadata = _page_metadata[page_path]
                output.append(f"│      ├─ Description: {metadata.get('description', 'N/A')}")

            # Get layout info
            layout_func = page.get("layout")
            if layout_func:
                if callable(layout_func):
                    try:
                        layout = layout_func()
                        arch = extract_component_architecture(layout, max_depth=3)
                        comp_types = count_component_types(arch)
                        total = count_total_components(arch)

                        # Count interactive components
                        interactive = sum(
                            comp_types.get(t, 0)
                            for t in [
                                "Input",
                                "TextInput",
                                "Select",
                                "Dropdown",
                                "Button",
                                "Checkbox",
                                "Radio",
                                "Slider",
                            ]
                        )

                        output.append(f"│      ├─ Components: {total}")
                        output.append(f"│      ├─ Interactive: {interactive}")

                        # Count callbacks for this page
                        page_callbacks = len(callback_map.get(page_module, []))
                        output.append(f"│      ├─ Callbacks: {page_callbacks}")
                        output.append(f"│      └─ Types: {', '.join(list(comp_types.keys())[:5])}")
                    except Exception as e:
                        output.append(f"│      └─ Layout: Dynamic (error: {str(e)[:30]})")
                else:
                    output.append(f"│      └─ Layout: Static")

            output.append(f"│")

    # Routes
    output.append("├─ ROUTES")
    output.append("│  ├── Documentation Routes:")
    output.append("│  │   ├── /llms.txt (current page context)")
    output.append("│  │   ├── /page.json (current page architecture)")
    output.append("│  │   ├── /architecture.txt (global architecture)")
    output.append("│  │   └── /<page_path>/llms.txt (specific page)")

    # List all page routes
    if page_registry:
        output.append("│  ├── Page Routes:")
        page_routes = sorted(
            [(p.get("path", "/"), p.get("name", "Unknown")) for p in page_registry.values()]
        )
        for i, (path, name) in enumerate(page_routes):
            is_last = i == len(page_routes) - 1
            prefix = "└───" if is_last else "├───"
            output.append(f"│  │   {prefix} {path} ({name})")

    output.append("│")

    # Component Statistics
    output.append("├─ STATISTICS")
    total_pages = len(page_registry)
    output.append(f"│  ├── Total Pages: {total_pages}")
    output.append(f"│  ├── Total Callbacks: {callback_count}")

    if page_registry:
        total_components = 0
        total_interactive = 0
        all_types = defaultdict(int)

        for page in page_registry.values():
            layout_func = page.get("layout")
            if layout_func:
                try:
                    layout = layout_func() if callable(layout_func) else layout_func
                    arch = extract_component_architecture(layout, max_depth=3)
                    total_components += count_total_components(arch)
                    types = count_component_types(arch)
                    for t, count in types.items():
                        all_types[t] += count

                    # Count interactive components
                    total_interactive += sum(
                        types.get(t, 0)
                        for t in [
                            "Input",
                            "TextInput",
                            "Select",
                            "Dropdown",
                            "Button",
                            "Checkbox",
                            "Radio",
                            "Slider",
                        ]
                    )
                except:
                    pass

        output.append(f"│  ├── Total Components: {total_components}")
        output.append(f"│  ├── Interactive Components: {total_interactive}")
        output.append(f"│  └── Unique Component Types: {len(all_types)}")

        # Show top 10 component types
        if all_types:
            output.append("│")
            output.append("├─ TOP COMPONENTS")
            sorted_types = sorted(all_types.items(), key=lambda x: x[1], reverse=True)[:10]
            for i, (comp_type, count) in enumerate(sorted_types):
                is_last = i == len(sorted_types) - 1
                prefix = "└──" if is_last else "├──"
                output.append(f"│  {prefix} {comp_type}: {count}")

    output.append("│")
    output.append("└─ END")
    output.append("")
    output.append("=" * 80)
    output.append("*Generated with https://pip-install-python.com | dash-improve-my-llms hook*\n")
    output.append("Pip Install Python LLC | https://plotly.pro\n")
    output.append("=" * 80)

    return "\n".join(output)


def add_llms_routes(app, config: Optional[LLMSConfig] = None):
    """
    Add LLMS routes to a Dash app.

    This function should be called after creating your Dash app to add
    automatic llms.txt and page.json generation.

    Args:
        app: Dash app instance
        config: Optional LLMSConfig for customization

    Example:
        app = Dash(__name__, use_pages=True)
        add_llms_routes(app)
    """
    if config is None:
        config = LLMSConfig()

    if not config.enabled:
        return

    # Store config on app
    app._llms_config = config

    # Add bot response middleware
    @app.server.before_request
    def handle_bot_requests():
        """
        Middleware to serve different content based on bot type and RobotsConfig.

        Behavior:
        - Training bots (when block_ai_training=True): Return 403 Forbidden
        - Search/Traditional bots: Return static HTML with structured data
        - Regular browsers: Continue with normal Dash app
        """
        from flask import request, Response
        from .bot_detection import is_any_bot, get_bot_type
        from .html_generator import generate_static_page_html

        # Skip for asset requests and Dash internal paths
        if any(ext in request.path for ext in ['.css', '.js', '.png', '.jpg', '.ico', '_dash', '_reload-hash']):
            return None

        # Skip for documentation routes (let them handle bots themselves)
        if request.path.endswith(('/llms.txt', '/page.json', '/architecture.txt', '/robots.txt', '/sitemap.xml')):
            return None

        user_agent = request.headers.get('User-Agent', '')

        # Check if this is a bot
        if is_any_bot(user_agent):
            bot_type = get_bot_type(user_agent)
            robots_config = getattr(app, '_robots_config', None)

            # Block AI training bots if configured
            if bot_type == 'training' and robots_config and robots_config.block_ai_training:
                return Response(
                    "403 Forbidden - AI training bots are not allowed to access this content.\n"
                    "This site blocks AI training bots to prevent unauthorized use of content for model training.\n"
                    f"Bot detected: {user_agent[:100]}\n"
                    "For more information, see /robots.txt",
                    status=403,
                    mimetype='text/plain'
                )

            # Serve llms.txt content to search and traditional bots
            # This solves the "AI crawlers cannot execute JavaScript" problem
            if bot_type in ['search', 'traditional']:
                try:
                    # Get the page path
                    page_path = request.path if request.path != '/' else '/'

                    # Check if page is hidden
                    if is_hidden(page_path):
                        return Response("404 Not Found - Page not available", status=404, mimetype='text/plain')

                    # Try to find the page in dash.page_registry
                    import dash
                    page_registry = dash.page_registry if hasattr(dash, "page_registry") else {}

                    # Find matching page
                    page = None
                    for p in page_registry.values():
                        p_path = p.get("path", "")
                        if p_path == page_path:
                            page = p
                            break

                    if page:
                        layout_func = page.get("layout")
                        page_name = page.get("name", page_path)

                        if layout_func:
                            # Generate llms.txt content for bots (bot-friendly markdown)
                            # This is what bots should see instead of JavaScript
                            llms_content = generate_llms_txt(page_path, layout_func, page_name, app)

                            # Return as HTML with proper formatting for better bot rendering
                            html_wrapper = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_name}</title>
    <meta name="robots" content="index, follow">
    <link rel="alternate" type="text/plain" href="{page_path}/llms.txt">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            color: #333;
        }}
        pre {{
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .bot-notice {{
            background: #f0f7ff;
            border-left: 4px solid #0066cc;
            padding: 15px;
            margin-bottom: 30px;
        }}
    </style>
</head>
<body>
    <div class="bot-notice">
        <strong>🤖 Bot-Optimized Content</strong><br>
        You're viewing a bot-friendly version of this page.<br>
        Also available: <a href="{page_path}/llms.txt">llms.txt</a> |
        <a href="{page_path}/page.json">page.json</a> |
        <a href="/architecture.txt">architecture.txt</a> |
        <a href="/sitemap.xml">sitemap.xml</a>
    </div>
    <pre>{llms_content}</pre>
</body>
</html>"""
                            return Response(html_wrapper, mimetype='text/html')
                except Exception as e:
                    # If llms.txt generation fails, log and continue with normal app
                    import traceback
                    print(f"Error generating llms.txt for bot: {e}")
                    print(traceback.format_exc())
                    # Fall through to normal Dash app

        # Continue with normal Dash app for regular browsers
        return None

    # Use Flask's app.server to add routes directly
    # This ensures proper route matching with wildcards

    @app.server.route("/<path:page_path>/llms.txt")
    @app.server.route("/llms.txt")
    def serve_llms_txt(page_path=""):
        """Serve comprehensive llms.txt for a specific page"""
        from flask import request

        # Construct the page path
        if not page_path:
            page_path = "/"
        elif not page_path.startswith("/"):
            page_path = "/" + page_path

        # Block access to hidden pages
        if is_hidden(page_path):
            return Response("Page not available", status=404)

        # Try to find the page in dash.page_registry
        try:
            import dash

            page_registry = dash.page_registry

            # Find matching page
            page = None
            for p in page_registry.values():
                p_path = p.get("path", "")
                if p_path == page_path or p.get("relative_path") == page_path:
                    page = p
                    break

            if page:
                layout_func = page.get("layout")
                page_name = page.get("name", page_path)

                if layout_func:
                    # Pass app instance for comprehensive context
                    llms_content = generate_llms_txt(page_path, layout_func, page_name, app)
                    return Response(llms_content, mimetype="text/plain")
        except Exception as e:
            import traceback

            error_msg = f"Error generating llms.txt: {str(e)}\n{traceback.format_exc()}"
            return Response(error_msg, status=500)

        return Response(f"llms.txt not available for {page_path}", status=404)

    @app.server.route("/<path:page_path>/page.json")
    @app.server.route("/page.json")
    def serve_page_json(page_path=""):
        """Serve page.json for a specific page"""
        from flask import request

        # Construct the page path
        if not page_path:
            page_path = "/"
        elif not page_path.startswith("/"):
            page_path = "/" + page_path

        # Block access to hidden pages
        if is_hidden(page_path):
            return jsonify({"error": "Page not available"}), 404

        # Try to find the page
        try:
            import dash

            page_registry = dash.page_registry

            # Find matching page
            page = None
            for p in page_registry.values():
                p_path = p.get("path", "")
                if p_path == page_path or p.get("relative_path") == page_path:
                    page = p
                    break

            if page:
                layout_func = page.get("layout")

                if layout_func:
                    page_json = generate_page_json(page_path, layout_func)
                    return jsonify(page_json)
        except Exception as e:
            import traceback

            error_msg = {
                "error": f"Error generating page.json: {str(e)}",
                "traceback": traceback.format_exc(),
            }
            return jsonify(error_msg), 500

        return jsonify({"error": f"page.json not available for {page_path}"}), 404

    @app.server.route("/architecture.txt")
    def serve_architecture_txt():
        """Serve architecture.txt showing entire app structure"""
        try:
            architecture_content = generate_architecture_txt(app)
            return Response(architecture_content, mimetype="text/plain")
        except Exception as e:
            import traceback

            error_msg = f"Error generating architecture.txt: {str(e)}\n{traceback.format_exc()}"
            return Response(error_msg, status=500)

    @app.server.route("/robots.txt")
    def serve_robots_txt():
        """Serve robots.txt with configurable bot policies"""
        from .robots_generator import RobotsConfig, generate_robots_txt

        try:
            # Get config from app or use defaults
            robots_config = getattr(app, "_robots_config", RobotsConfig())
            base_url = getattr(app, "_base_url", "https://example.com")

            robots_content = generate_robots_txt(
                config=robots_config,
                sitemap_url=f"{base_url}/sitemap.xml",
                base_url=base_url,
            )
            return Response(robots_content, mimetype="text/plain")
        except Exception as e:
            import traceback

            error_msg = f"Error generating robots.txt: {str(e)}\n{traceback.format_exc()}"
            return Response(error_msg, status=500)

    @app.server.route("/sitemap.xml")
    def serve_sitemap():
        """Serve sitemap.xml from registered pages"""
        from .sitemap_generator import generate_sitemap_xml

        try:
            import dash

            page_registry = dash.page_registry if hasattr(dash, "page_registry") else {}

            # Build pages list from registry
            pages = []
            for p in page_registry.values():
                page_path = p.get("path", "/")
                # Skip hidden pages
                if not is_hidden(page_path):
                    page_info = {
                        "path": page_path,
                        "name": p.get("name", "Page"),
                        "description": _page_metadata.get(page_path, {}).get("description", ""),
                        "hidden": False,
                    }
                    pages.append(page_info)

            base_url = getattr(app, "_base_url", "https://example.com")

            sitemap_content = generate_sitemap_xml(
                pages=pages, base_url=base_url, hidden_paths=list(_hidden_pages)
            )
            return Response(sitemap_content, mimetype="application/xml")
        except Exception as e:
            import traceback

            error_msg = f"Error generating sitemap.xml: {str(e)}\n{traceback.format_exc()}"
            return Response(error_msg, status=500)


# For backward compatibility and direct usage
def setup_llms_plugin(
    app, enabled: bool = True, include_css: bool = True, include_callbacks: bool = True
):
    """
    Legacy function for setting up the LLMS plugin.

    Prefer using add_llms_routes() instead.
    """
    config = LLMSConfig(
        enabled=enabled, include_css=include_css, include_callbacks=include_callbacks
    )
    add_llms_routes(app, config)


# Import RobotsConfig for external use
from .robots_generator import RobotsConfig

__all__ = [
    "add_llms_routes",
    "mark_important",
    "is_important",
    "mark_hidden",
    "is_hidden",
    "mark_component_hidden",
    "is_component_hidden",
    "register_page_metadata",
    "LLMSConfig",
    "RobotsConfig",
    "setup_llms_plugin",
]
