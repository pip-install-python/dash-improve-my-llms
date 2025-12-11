"""
TOON Generator for dash-improve-my-llms

Generates Token-Oriented Object Notation (TOON) output optimized for LLM consumption.
Achieves 30-60% token reduction compared to markdown llms.txt format.

TOON Specification: https://github.com/toon-format/spec (v3.0)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import re


@dataclass
class TOONConfig:
    """Configuration for TOON output generation."""

    # Core formatting
    indent: int = 2  # Spaces per indent level
    delimiter: str = ","  # Delimiter: "," | "\t" | "|"

    # Content control
    include_metadata: bool = True  # Include generator metadata
    include_content: bool = True  # Include text content arrays
    max_content_items: int = 20  # Limit content array size

    # Advanced
    strict_mode: bool = True  # Validate array lengths
    minify: bool = False  # Single-line primitives where possible


# Characters that require quoting in TOON strings
TOON_SPECIAL_CHARS = re.compile(r'[\[\]\{\}:,"\\\n\r\t|]')
TOON_RESERVED_WORDS = {"true", "false", "null"}
TOON_NUMERIC_PATTERN = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
TOON_NEEDS_QUOTE_START = re.compile(r"^[-\s]|^\s|\s$")


def needs_quoting(value: str, delimiter: str = ",") -> bool:
    """
    Determine if a string value needs to be quoted in TOON format.

    Args:
        value: The string value to check
        delimiter: The active delimiter

    Returns:
        True if the value needs to be quoted
    """
    if not value:
        return True  # Empty strings need quotes

    # Check for reserved words
    if value.lower() in TOON_RESERVED_WORDS:
        return True

    # Check for numeric patterns (would be parsed as numbers)
    if TOON_NUMERIC_PATTERN.match(value):
        return True

    # Check for special characters
    if TOON_SPECIAL_CHARS.search(value):
        return True

    # Check for delimiter
    if delimiter in value:
        return True

    # Check for leading/trailing whitespace or starting with hyphen
    if TOON_NEEDS_QUOTE_START.match(value):
        return True

    return False


def escape_toon_string(value: str) -> str:
    """
    Escape a string for TOON format.

    Only 5 escape sequences are valid:
    - \\\\ -> backslash
    - \\" -> double quote
    - \\n -> newline
    - \\r -> carriage return
    - \\t -> tab
    """
    result = value.replace("\\", "\\\\")
    result = result.replace('"', '\\"')
    result = result.replace("\n", "\\n")
    result = result.replace("\r", "\\r")
    result = result.replace("\t", "\\t")
    return result


def format_toon_value(value: Any, delimiter: str = ",") -> str:
    """
    Format a Python value as a TOON primitive.

    Args:
        value: The value to format
        delimiter: The active delimiter

    Returns:
        TOON-formatted string representation
    """
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        # Canonical decimal form: no exponents, no trailing zeros
        if value == int(value):
            return str(int(value))
        formatted = f"{value:.15g}"
        # Remove trailing zeros after decimal point
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted
    elif isinstance(value, str):
        if needs_quoting(value, delimiter):
            return f'"{escape_toon_string(value)}"'
        return value
    else:
        # Fallback: convert to string and quote if needed
        str_val = str(value)
        if needs_quoting(str_val, delimiter):
            return f'"{escape_toon_string(str_val)}"'
        return str_val


def is_uniform_array(arr: List[Any]) -> bool:
    """
    Check if an array contains uniform objects (same keys).

    Uniform arrays can be rendered in tabular format.
    """
    if not arr or not isinstance(arr, list):
        return False

    # All items must be dicts
    if not all(isinstance(item, dict) for item in arr):
        return False

    # All dicts must have the same keys
    if len(arr) == 0:
        return True

    first_keys = set(arr[0].keys())
    return all(set(item.keys()) == first_keys for item in arr)


def is_primitive_array(arr: List[Any]) -> bool:
    """Check if an array contains only primitive values (not dicts/lists)."""
    if not arr or not isinstance(arr, list):
        return False
    return all(
        isinstance(item, (str, int, float, bool, type(None))) for item in arr
    )


class TOONEncoder:
    """
    Encoder for Token-Oriented Object Notation (TOON) format.

    This is a built-in fallback encoder that implements core TOON features
    without requiring external dependencies.
    """

    def __init__(self, config: Optional[TOONConfig] = None):
        self.config = config or TOONConfig()
        self.indent_str = " " * self.config.indent
        self.delimiter = self.config.delimiter

    def encode(self, data: Any) -> str:
        """
        Encode Python data to TOON format.

        Args:
            data: Python object (dict, list, or primitive)

        Returns:
            TOON-formatted string
        """
        lines = []
        self._encode_value(data, lines, depth=0)
        return "\n".join(lines)

    def _encode_value(
        self,
        value: Any,
        lines: List[str],
        depth: int,
        key: Optional[str] = None,
    ):
        """Recursively encode a value."""
        indent = self.indent_str * depth

        if isinstance(value, dict):
            self._encode_object(value, lines, depth, key)
        elif isinstance(value, list):
            self._encode_array(value, lines, depth, key)
        else:
            # Primitive value
            formatted = format_toon_value(value, self.delimiter)
            if key is not None:
                lines.append(f"{indent}{key}: {formatted}")
            else:
                lines.append(f"{indent}{formatted}")

    def _encode_object(
        self,
        obj: Dict[str, Any],
        lines: List[str],
        depth: int,
        key: Optional[str] = None,
    ):
        """Encode a dictionary as a TOON object."""
        indent = self.indent_str * depth

        if key is not None:
            if not obj:
                # Empty object
                lines.append(f"{indent}{key}:")
                return
            lines.append(f"{indent}{key}:")
            depth += 1

        for k, v in obj.items():
            self._encode_value(v, lines, depth, key=k)

    def _encode_array(
        self,
        arr: List[Any],
        lines: List[str],
        depth: int,
        key: Optional[str] = None,
    ):
        """Encode a list as a TOON array."""
        indent = self.indent_str * depth
        n = len(arr)

        if not arr:
            # Empty array
            if key is not None:
                lines.append(f"{indent}{key}[0]:")
            else:
                lines.append(f"{indent}[0]:")
            return

        # Check if it's a uniform array of objects (tabular format)
        if is_uniform_array(arr):
            self._encode_tabular_array(arr, lines, depth, key)
        elif is_primitive_array(arr):
            self._encode_primitive_array(arr, lines, depth, key)
        else:
            # Mixed/non-uniform array - use list item format
            self._encode_mixed_array(arr, lines, depth, key)

    def _encode_primitive_array(
        self,
        arr: List[Any],
        lines: List[str],
        depth: int,
        key: Optional[str] = None,
    ):
        """Encode an array of primitives inline."""
        indent = self.indent_str * depth
        n = len(arr)

        values = [format_toon_value(v, self.delimiter) for v in arr]
        values_str = self.delimiter.join(values)

        if key is not None:
            lines.append(f"{indent}{key}[{n}]: {values_str}")
        else:
            lines.append(f"{indent}[{n}]: {values_str}")

    def _encode_tabular_array(
        self,
        arr: List[Dict[str, Any]],
        lines: List[str],
        depth: int,
        key: Optional[str] = None,
    ):
        """Encode a uniform array of objects in tabular format."""
        indent = self.indent_str * depth
        row_indent = self.indent_str * (depth + 1)
        n = len(arr)

        # Get field names from first object
        fields = list(arr[0].keys())
        fields_str = self.delimiter.join(fields)

        # Header
        if key is not None:
            lines.append(f"{indent}{key}[{n}]{{{fields_str}}}:")
        else:
            lines.append(f"{indent}[{n}]{{{fields_str}}}:")

        # Rows
        for obj in arr:
            row_values = [
                format_toon_value(obj.get(f), self.delimiter) for f in fields
            ]
            row_str = self.delimiter.join(row_values)
            lines.append(f"{row_indent}{row_str}")

    def _encode_mixed_array(
        self,
        arr: List[Any],
        lines: List[str],
        depth: int,
        key: Optional[str] = None,
    ):
        """Encode a mixed/non-uniform array using list item format."""
        indent = self.indent_str * depth
        item_indent = self.indent_str * (depth + 1)
        n = len(arr)

        if key is not None:
            lines.append(f"{indent}{key}[{n}]:")
        else:
            lines.append(f"{indent}[{n}]:")

        for item in arr:
            if isinstance(item, dict):
                # Object as list item
                if not item:
                    lines.append(f"{item_indent}-")
                else:
                    first_key = list(item.keys())[0]
                    first_val = item[first_key]

                    # First field on same line as "-"
                    if isinstance(first_val, (dict, list)):
                        lines.append(f"{item_indent}- {first_key}:")
                        self._encode_value(
                            first_val, lines, depth + 2, key=None
                        )
                    else:
                        formatted = format_toon_value(first_val, self.delimiter)
                        lines.append(f"{item_indent}- {first_key}: {formatted}")

                    # Remaining fields at depth + 1
                    for k in list(item.keys())[1:]:
                        self._encode_value(item[k], lines, depth + 1, key=k)
            elif isinstance(item, list):
                # Nested array
                lines.append(f"{item_indent}-")
                self._encode_array(item, lines, depth + 2)
            else:
                # Primitive
                formatted = format_toon_value(item, self.delimiter)
                lines.append(f"{item_indent}- {formatted}")


def toon_encode(data: Any, config: Optional[TOONConfig] = None) -> str:
    """
    Encode Python data to TOON format.

    This function attempts to use the python-toon package if available,
    falling back to the built-in encoder.

    Args:
        data: Python object to encode
        config: Optional TOON configuration

    Returns:
        TOON-formatted string
    """
    # Try to use external package first
    try:
        from toon import encode as external_encode

        if config:
            return external_encode(data, indent=config.indent)
        return external_encode(data)
    except ImportError:
        pass

    # Fallback to built-in encoder
    encoder = TOONEncoder(config)
    return encoder.encode(data)


def generate_llms_toon(
    page_path: str,
    layout_func,
    page_name: Optional[str] = None,
    app=None,
    config: Optional[TOONConfig] = None,
    page_data: Optional[Dict] = None,
) -> str:
    """
    Generate TOON-formatted llms content for a page.

    Args:
        page_path: URL path of the page
        layout_func: Function or component that returns the page layout
        page_name: Optional display name for the page
        app: Optional Dash app instance
        config: Optional TOON configuration
        page_data: Optional pre-generated page.json data

    Returns:
        TOON-formatted string optimized for LLM consumption
    """
    if config is None:
        config = TOONConfig()

    # Import here to avoid circular imports
    from . import generate_page_json, _page_metadata, extract_text_content

    # Get layout
    if callable(layout_func):
        try:
            layout = layout_func()
        except Exception:
            from dash import html
            layout = html.Div("Error loading layout")
    else:
        layout = layout_func

    # Generate page.json data if not provided
    if page_data is None:
        page_data = generate_page_json(page_path, layout_func, app)

    # Extract text content
    text_content = extract_text_content(layout)
    important_content = [t for t in text_content if t.startswith("[IMPORTANT]")]
    regular_content = [t for t in text_content if not t.startswith("[IMPORTANT]")]

    # Clean content
    important_clean = [
        t.replace("[IMPORTANT] ", "").strip()
        for t in important_content
        if not t.replace("[IMPORTANT] ", "").startswith("##")
    ][: config.max_content_items]

    regular_clean = [
        t.strip()
        for t in regular_content
        if len(t.strip()) > 1 and not t.startswith("##")
    ][: config.max_content_items]

    # Extract component info
    components = page_data.get("components", {})
    interactivity = page_data.get("interactivity", {})
    navigation = page_data.get("navigation", {})
    callbacks_data = page_data.get("callbacks", {})
    metadata = page_data.get("metadata", {})

    # Build TOON-optimized structure
    toon_data = {}

    # Page info
    title = page_name or page_path.strip("/").replace("-", " ").title() or "Home"
    description = page_data.get("description", "")
    if not description:
        description = _page_metadata.get(page_path, {}).get("description", "")

    toon_data["page"] = {
        "path": page_path,
        "name": title,
        "description": description,
    }

    # App context
    if app:
        try:
            import dash

            page_registry = dash.page_registry if hasattr(dash, "page_registry") else {}
            total_pages = len(page_registry)

            if total_pages > 0:
                related = []
                for p in page_registry.values():
                    if p.get("path") != page_path:
                        related.append({
                            "path": p.get("path", "/"),
                            "name": p.get("name", "Page"),
                        })

                if related:
                    toon_data["app"] = {
                        "totalPages": total_pages,
                        "relatedPages": related[:5],  # Limit to 5
                    }
        except Exception:
            pass

    # Purpose flags
    purposes = []
    if metadata.get("contains_forms"):
        purposes.append("data-input")
    if metadata.get("contains_visualizations"):
        purposes.append("visualization")
    if metadata.get("contains_navigation"):
        purposes.append("navigation")
    if interactivity.get("has_callbacks"):
        purposes.append("interactive")

    if purposes:
        toon_data["purpose"] = purposes

    # Interactive elements
    interactive_count = interactivity.get("interactive_components", 0)
    callback_count = interactivity.get("callback_count", 0)

    if interactive_count > 0 or callback_count > 0:
        interactive_data = {
            "componentCount": interactive_count,
            "callbackCount": callback_count,
        }

        # Format inputs as tabular array
        categories = components.get("categories", {})
        comp_ids = components.get("ids", {})

        if "inputs" in categories and categories["inputs"]:
            inputs_list = []
            for input_id in categories["inputs"][:10]:
                if input_id in comp_ids:
                    comp_info = comp_ids[input_id]
                    inputs_list.append({
                        "id": input_id,
                        "type": comp_info.get("type", "Unknown"),
                        "module": (comp_info.get("module") or "").split(".")[-1],
                    })
            if inputs_list:
                interactive_data["inputs"] = inputs_list

        # Format outputs
        if "outputs" in categories and categories["outputs"]:
            outputs_list = []
            for output_id in categories["outputs"][:10]:
                if output_id in comp_ids:
                    comp_info = comp_ids[output_id]
                    outputs_list.append({
                        "id": output_id,
                        "type": comp_info.get("type", "Unknown"),
                    })
            if outputs_list:
                interactive_data["outputs"] = outputs_list

        toon_data["interactive"] = interactive_data

    # Content
    if config.include_content and (important_clean or regular_clean):
        content_data = {}
        if important_clean:
            content_data["important"] = important_clean
        if regular_clean:
            content_data["additional"] = regular_clean
        toon_data["content"] = content_data

    # Navigation
    links = navigation.get("links", [])
    if links:
        internal = [
            {"text": l.get("text", l.get("href", "Link")), "href": l.get("href", "/")}
            for l in links
            if l.get("href", "").startswith("/")
        ][:10]
        external = [
            {"text": l.get("text", l.get("href", "Link")), "href": l.get("href", "")}
            for l in links
            if not l.get("href", "").startswith("/") and l.get("href")
        ][:5]

        if internal or external:
            nav_data = {}
            if internal:
                nav_data["internal"] = internal
            if external:
                nav_data["external"] = external
            toon_data["navigation"] = nav_data

    # Components summary
    comp_counts = components.get("counts", {})
    comp_types = components.get("types", {})

    if comp_counts:
        components_data = {
            "total": comp_counts.get("total", 0),
            "interactive": comp_counts.get("interactive", 0),
            "static": comp_counts.get("static", 0),
        }

        # Top component types as tabular array
        if comp_types:
            sorted_types = sorted(
                comp_types.items(), key=lambda x: x[1], reverse=True
            )[:10]
            type_list = [
                {"name": t, "count": c}
                for t, c in sorted_types
                if t != "text"
            ]
            if type_list:
                components_data["types"] = type_list

        toon_data["components"] = components_data

    # Callbacks
    callback_list = callbacks_data.get("list", [])
    if callback_list:
        callbacks_formatted = []
        for cb in callback_list[:10]:
            cb_data = {"output": cb.get("output", "unknown")}
            inputs = cb.get("inputs", [])
            if inputs:
                cb_data["inputs"] = inputs
            state = cb.get("state", [])
            if state:
                cb_data["state"] = state
            callbacks_formatted.append(cb_data)
        toon_data["callbacks"] = callbacks_formatted

    # Technical details
    toon_data["technical"] = {
        "maxDepth": metadata.get("max_depth", 0),
        "hasImportantSections": metadata.get("has_important_sections", False),
        "containsForms": metadata.get("contains_forms", False),
        "containsVisualizations": metadata.get("contains_visualizations", False),
    }

    # Links to other formats
    toon_data["links"] = {
        "llmsTxt": f"{page_path}/llms.txt" if page_path != "/" else "/llms.txt",
        "pageJson": f"{page_path}/page.json" if page_path != "/" else "/page.json",
        "architecture": "/architecture.txt",
    }

    # Metadata
    if config.include_metadata:
        toon_data["meta"] = {
            "generator": "dash-improve-my-llms",
            "version": "1.0.0",
            "format": "toon/3.0",
        }

    # Encode to TOON
    return toon_encode(toon_data, config)


def generate_architecture_toon(app, config: Optional[TOONConfig] = None) -> str:
    """
    Generate TOON-formatted architecture overview for the entire application.

    Args:
        app: Dash application instance
        config: Optional TOON configuration

    Returns:
        TOON-formatted string with application architecture
    """
    import sys

    if config is None:
        config = TOONConfig()

    # Import here to avoid circular imports
    from . import (
        _page_metadata,
        extract_component_architecture,
        count_component_types,
        count_total_components,
    )

    import dash

    toon_data = {}

    # Environment
    env_data = {"pythonVersion": sys.version.split()[0]}

    try:
        env_data["dashVersion"] = dash.__version__
    except Exception:
        pass

    # Dependencies
    deps = []
    try:
        import dash_mantine_components

        deps.append({
            "name": "dash-mantine-components",
            "version": dash_mantine_components.__version__,
        })
    except Exception:
        pass

    try:
        import plotly

        deps.append({"name": "plotly", "version": plotly.__version__})
    except Exception:
        pass

    try:
        import pandas

        deps.append({"name": "pandas", "version": pandas.__version__})
    except Exception:
        pass

    if deps:
        env_data["dependencies"] = deps

    toon_data["environment"] = env_data

    # Application info
    app_data = {
        "name": app.title if hasattr(app, "title") else "Dash App",
        "server": app.server.name if hasattr(app.server, "name") else "Flask",
    }

    page_registry = dash.page_registry if hasattr(dash, "page_registry") else {}
    app_data["multiPage"] = bool(page_registry)
    app_data["pageCount"] = len(page_registry)

    toon_data["application"] = app_data

    # Pages
    if page_registry:
        pages_list = []
        total_components = 0
        total_interactive = 0
        all_types = {}

        for page in page_registry.values():
            page_path = page.get("path", "/")
            page_info = {
                "path": page_path,
                "name": page.get("name", "Unknown"),
                "module": page.get("module", ""),
            }

            # Get component stats
            layout_func = page.get("layout")
            if layout_func:
                try:
                    layout = layout_func() if callable(layout_func) else layout_func
                    arch = extract_component_architecture(layout, max_depth=3)
                    types = count_component_types(arch)
                    total = count_total_components(arch)

                    interactive = sum(
                        types.get(t, 0)
                        for t in [
                            "Input", "TextInput", "Select", "Dropdown",
                            "Button", "Checkbox", "Radio", "Slider",
                        ]
                    )

                    page_info["components"] = total
                    page_info["interactive"] = interactive

                    total_components += total
                    total_interactive += interactive

                    for t, c in types.items():
                        all_types[t] = all_types.get(t, 0) + c
                except Exception:
                    pass

            pages_list.append(page_info)

        toon_data["pages"] = pages_list

        # Statistics
        toon_data["statistics"] = {
            "totalPages": len(page_registry),
            "totalComponents": total_components,
            "interactiveComponents": total_interactive,
            "uniqueTypes": len(all_types),
        }

        # Top component types
        if all_types:
            sorted_types = sorted(
                all_types.items(), key=lambda x: x[1], reverse=True
            )[:10]
            toon_data["topComponents"] = [
                {"name": t, "count": c} for t, c in sorted_types
            ]

    # Routes
    toon_data["routes"] = {
        "documentation": [
            "/llms.txt",
            "/llms.toon",
            "/page.json",
            "/architecture.txt",
            "/architecture.toon",
        ],
        "seo": ["/robots.txt", "/sitemap.xml"],
    }

    # Metadata
    if config.include_metadata:
        toon_data["meta"] = {
            "generator": "dash-improve-my-llms",
            "version": "1.0.0",
            "format": "toon/3.0",
        }

    return toon_encode(toon_data, config)


__all__ = [
    "TOONConfig",
    "TOONEncoder",
    "toon_encode",
    "generate_llms_toon",
    "generate_architecture_toon",
    "needs_quoting",
    "format_toon_value",
]