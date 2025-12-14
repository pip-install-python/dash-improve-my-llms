"""
TOON Generator for dash-improve-my-llms

Generates Token-Oriented Object Notation (TOON) output optimized for LLM consumption.
Achieves 30-60% token reduction compared to markdown llms.txt format.

TOON Specification: https://github.com/toon-format/spec (v3.0)

Key Design Principle:
  TOON should be a LOSSLESS SEMANTIC COMPRESSION of llms.txt content.
  An AI reading llms.toon should gain the same understanding as llms.txt,
  just with fewer tokens. Architecture metadata is secondary to actual content.
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
    max_content_items: int = 100  # Limit content array size (increased from 20)

    # Content preservation (NEW)
    preserve_code_examples: bool = True  # Include code snippets
    preserve_headings: bool = True  # Keep section structure
    preserve_markdown: bool = True  # Extract dcc.Markdown content
    max_code_lines: int = 30  # Max lines per code example
    max_sections: int = 20  # Max number of sections to include

    # Advanced
    strict_mode: bool = True  # Validate array lengths
    minify: bool = False  # Single-line primitives where possible


# Characters that require quoting in TOON strings
TOON_SPECIAL_CHARS = re.compile(r'[\[\]\{\}:,"\\\n\r\t|]')
TOON_RESERVED_WORDS = {"true", "false", "null"}
TOON_NUMERIC_PATTERN = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
TOON_NEEDS_QUOTE_START = re.compile(r"^[-\s]|^\s|\s$")

# Regex patterns for markdown parsing
CODE_BLOCK_PATTERN = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)')


def extract_markdown_content(component, depth: int = 0, max_depth: int = 30) -> Dict[str, Any]:
    """
    Extract structured content from Dash components, including markdown.

    Returns a dict with:
        - sections: list of {heading, level, content}
        - code_examples: list of {language, code, description}
        - text_content: list of plain text strings
        - links: list of {text, href}
    """
    if depth > max_depth:
        return {"sections": [], "code_examples": [], "text_content": [], "links": []}

    result = {
        "sections": [],
        "code_examples": [],
        "text_content": [],
        "links": []
    }

    # Handle string content
    if isinstance(component, str):
        text = component.strip()
        if text:
            # Check if it's markdown content (has code blocks or headings)
            if '```' in text or text.startswith('#'):
                parsed = parse_markdown_content(text)
                result["sections"].extend(parsed["sections"])
                result["code_examples"].extend(parsed["code_examples"])
                result["text_content"].extend(parsed["text_content"])
                result["links"].extend(parsed["links"])
            else:
                result["text_content"].append(text)
        return result

    # Get component type
    component_name = getattr(component, "__class__", type(component)).__name__

    # Special handling for Markdown components
    if component_name == "Markdown":
        children = getattr(component, "children", None)
        if children and isinstance(children, str):
            parsed = parse_markdown_content(children)
            result["sections"].extend(parsed["sections"])
            result["code_examples"].extend(parsed["code_examples"])
            result["text_content"].extend(parsed["text_content"])
            result["links"].extend(parsed["links"])
        return result

    # Handle headings
    if component_name in ["H1", "H2", "H3", "H4", "H5", "H6"]:
        level = int(component_name[1])
        children = getattr(component, "children", "")
        if isinstance(children, str):
            result["sections"].append({
                "heading": children,
                "level": level,
                "content": ""
            })

    # Recursively process children
    if hasattr(component, "children"):
        children = component.children
        if children is not None:
            if isinstance(children, list):
                for child in children:
                    child_result = extract_markdown_content(child, depth + 1, max_depth)
                    result["sections"].extend(child_result["sections"])
                    result["code_examples"].extend(child_result["code_examples"])
                    result["text_content"].extend(child_result["text_content"])
                    result["links"].extend(child_result["links"])
            else:
                child_result = extract_markdown_content(children, depth + 1, max_depth)
                result["sections"].extend(child_result["sections"])
                result["code_examples"].extend(child_result["code_examples"])
                result["text_content"].extend(child_result["text_content"])
                result["links"].extend(child_result["links"])

    return result


def parse_markdown_content(markdown_text: str) -> Dict[str, Any]:
    """
    Parse markdown text into structured sections and code examples.
    """
    result = {
        "sections": [],
        "code_examples": [],
        "text_content": [],
        "links": []
    }

    if not markdown_text:
        return result

    # Extract code blocks first (before other parsing)
    code_blocks = []
    def extract_code_block(match):
        lang = match.group(1) or "text"
        code = match.group(2).strip()
        code_blocks.append({"language": lang, "code": code})
        return f"[CODE_BLOCK_{len(code_blocks) - 1}]"

    # Replace code blocks with placeholders
    text_without_code = CODE_BLOCK_PATTERN.sub(extract_code_block, markdown_text)
    result["code_examples"] = code_blocks

    # Extract links
    for match in LINK_PATTERN.finditer(text_without_code):
        result["links"].append({
            "text": match.group(1),
            "href": match.group(2)
        })

    # Parse sections by headings
    lines = text_without_code.split('\n')
    current_section = None
    current_content = []

    for line in lines:
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            # Save previous section
            if current_section:
                current_section["content"] = '\n'.join(current_content).strip()
                if current_section["content"] or current_section["heading"]:
                    result["sections"].append(current_section)

            # Start new section
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            current_section = {"heading": heading, "level": level, "content": ""}
            current_content = []
        else:
            current_content.append(line)

    # Save last section
    if current_section:
        current_section["content"] = '\n'.join(current_content).strip()
        if current_section["content"] or current_section["heading"]:
            result["sections"].append(current_section)
    elif current_content:
        # No headings found - treat entire content as text
        full_text = '\n'.join(current_content).strip()
        if full_text:
            result["text_content"].append(full_text)

    return result


def compress_code_example(code: str, max_lines: int = 30) -> str:
    """
    Compress a code example while preserving its essential structure.
    """
    lines = code.split('\n')

    if len(lines) <= max_lines:
        return code

    # Keep first and last portions, indicate truncation
    keep_start = max_lines // 2
    keep_end = max_lines - keep_start - 1

    compressed = lines[:keep_start]
    compressed.append(f"    # ... ({len(lines) - max_lines} lines omitted) ...")
    compressed.extend(lines[-keep_end:])

    return '\n'.join(compressed)


def compress_section_content(content: str, max_chars: int = 500) -> str:
    """
    Compress section content while preserving key information.
    """
    if len(content) <= max_chars:
        return content

    # Keep first portion and indicate truncation
    truncated = content[:max_chars].rsplit(' ', 1)[0]
    return truncated + "..."


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


def _generate_page_summary(
    title: str,
    description: str,
    purposes: List[str],
    component_count: int,
    callback_count: int,
    has_forms: bool,
    has_visualizations: bool,
) -> str:
    """Generate a brief synthesized summary of the page."""
    parts = []

    # Core description
    if description:
        parts.append(description.rstrip('.'))
    else:
        parts.append(f"The {title} page")

    # Purpose context
    purpose_phrases = []
    if "data-input" in purposes or has_forms:
        purpose_phrases.append("accepts user input")
    if "visualization" in purposes or has_visualizations:
        purpose_phrases.append("displays visualizations")
    if "navigation" in purposes:
        purpose_phrases.append("provides navigation")
    if "interactive" in purposes and callback_count > 0:
        purpose_phrases.append(f"has {callback_count} interactive callback(s)")

    if purpose_phrases:
        parts.append(f"This page {', '.join(purpose_phrases)}.")

    # Component context
    if component_count > 0:
        parts.append(f"Contains {component_count} components.")

    return " ".join(parts)


def _format_callback_description(cb: Dict, index: int) -> Dict:
    """Format a callback with human-readable description."""
    output = cb.get("output", "unknown")
    inputs = cb.get("inputs", [])
    state = cb.get("state", [])

    # Parse output for readable description
    output_parts = output.split(".")
    output_id = output_parts[0] if output_parts else output
    output_prop = output_parts[1] if len(output_parts) > 1 else "value"

    result = {
        "n": index + 1,  # Callback number
        "updates": output,
        "triggers": inputs,
    }

    if state:
        result["reads"] = state

    return result


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

    DESIGN PRINCIPLE: TOON should be a LOSSLESS SEMANTIC COMPRESSION of llms.txt.
    An AI reading llms.toon should understand the page as well as reading llms.txt,
    just with fewer tokens. Content is PRIMARY, architecture is secondary.

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

    # === ENHANCED CONTENT EXTRACTION ===
    # Extract structured content including markdown, code, and sections
    markdown_content = extract_markdown_content(layout)

    # Also get basic text content for fallback
    text_content = extract_text_content(layout)
    important_content = [t for t in text_content if t.startswith("[IMPORTANT]")]
    regular_content = [t for t in text_content if not t.startswith("[IMPORTANT]")]

    # Clean basic content
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

    # === APP CONTEXT (Enhanced - addresses Gap #1) ===
    if app:
        try:
            import dash
            page_registry = dash.page_registry if hasattr(dash, "page_registry") else {}
            total_pages = len(page_registry)
            if total_pages > 0:
                # Explicit context framing
                context_data = {
                    "context": f"Part of multi-page Dash app with {total_pages} pages",
                    "totalPages": total_pages,
                }

                # Related pages with paths
                related = []
                for p in page_registry.values():
                    if p.get("path") != page_path:
                        related.append({
                            "name": p.get("name", "Page"),
                            "path": p.get("path", "/"),
                        })

                if related:
                    context_data["relatedPages"] = related[:5]

                toon_data["app"] = context_data
        except Exception:
            pass

    # === PAGE PURPOSE (Enhanced - addresses Gap #2) ===
    purposes = []
    purpose_explanations = []

    if metadata.get("contains_forms"):
        purposes.append("data-input")
        purpose_explanations.append("Data Input: Contains form elements for user input")
    if metadata.get("contains_visualizations"):
        purposes.append("visualization")
        purpose_explanations.append("Visualization: Displays charts, graphs, or visual data")
    if metadata.get("contains_navigation") or navigation.get("links"):
        purposes.append("navigation")
        purpose_explanations.append("Navigation: Provides links to other sections")
    if interactivity.get("has_callbacks"):
        purposes.append("interactive")
        purpose_explanations.append("Interactive: Responds to user interactions via callbacks")

    if purposes:
        toon_data["purpose"] = {
            "types": purposes,
            "explanation": purpose_explanations,
        }

    # === CONTENT SECTION (PRIMARY - This is what matters for AI understanding) ===
    if config.include_content:
        content_data = {}

        # 1. Sections with headings and content
        sections = markdown_content.get("sections", [])
        if sections and config.preserve_headings:
            formatted_sections = []
            for section in sections[:config.max_sections]:
                heading = section.get("heading", "")
                level = section.get("level", 2)
                content = section.get("content", "")

                # Compress content if too long
                if len(content) > 500:
                    content = compress_section_content(content, 500)

                # Remove code block placeholders from content
                content = re.sub(r'\[CODE_BLOCK_\d+\]', '', content).strip()

                if heading or content:
                    section_obj = {"h": heading, "l": level}
                    if content:
                        section_obj["t"] = content
                    formatted_sections.append(section_obj)

            if formatted_sections:
                content_data["sections"] = formatted_sections

        # 2. Code examples (CRITICAL for documentation pages)
        code_examples = markdown_content.get("code_examples", [])
        if code_examples and config.preserve_code_examples:
            formatted_code = []
            for example in code_examples[:10]:  # Limit to 10 examples
                lang = example.get("language", "text")
                code = example.get("code", "")

                # Compress if too long
                if code:
                    code = compress_code_example(code, config.max_code_lines)
                    formatted_code.append({
                        "lang": lang,
                        "code": code
                    })

            if formatted_code:
                content_data["codeExamples"] = formatted_code

        # 3. Text content (fallback if no markdown structure found)
        text_items = markdown_content.get("text_content", [])
        if text_items:
            # Deduplicate and clean
            unique_text = []
            seen = set()
            for t in text_items:
                clean = t.strip()[:500]  # Limit length
                if clean and clean not in seen and len(clean) > 10:
                    seen.add(clean)
                    unique_text.append(clean)
            if unique_text:
                content_data["text"] = unique_text[:config.max_content_items]

        # 4. Important content from mark_important()
        if important_clean:
            content_data["important"] = important_clean

        # 5. Additional content if we have any
        if regular_clean and not content_data.get("sections"):
            content_data["additional"] = regular_clean[:50]

        if content_data:
            toon_data["content"] = content_data

    # === COMPONENTS BREAKDOWN (Enhanced - addresses Gap #3) ===
    comp_counts = components.get("counts", {})
    comp_types = components.get("types", {})

    components_data = {
        "total": comp_counts.get("total", 0),
        "interactive": comp_counts.get("interactive", 0),
        "static": comp_counts.get("static", 0),
    }

    # Include type distribution (top 10 component types)
    if comp_types:
        sorted_types = sorted(
            comp_types.items(), key=lambda x: x[1], reverse=True
        )[:10]
        # Format as compact type:count pairs
        type_breakdown = [
            {"type": t, "count": c}
            for t, c in sorted_types
            if t != "text" and c > 0
        ]
        if type_breakdown:
            components_data["breakdown"] = type_breakdown

    toon_data["components"] = components_data

    # === CALLBACKS (Enhanced - addresses Gap #4) ===
    callback_list = callbacks_data.get("list", [])
    callback_count = interactivity.get("callback_count", 0)

    if callback_list:
        callbacks_formatted = []
        for i, cb in enumerate(callback_list[:10]):  # Limit to 10
            cb_formatted = _format_callback_description(cb, i)
            callbacks_formatted.append(cb_formatted)

        toon_data["callbacks"] = {
            "total": callback_count,
            "flows": callbacks_formatted,
        }
    elif callback_count > 0:
        toon_data["callbacks"] = {"total": callback_count}

    # === NAVIGATION (Enhanced - addresses Gap #6: separate internal/external) ===
    nav_links = navigation.get("links", [])
    md_links = markdown_content.get("links", [])

    internal_links = []
    external_links = []
    seen_hrefs = set()

    for l in nav_links + md_links:
        href = l.get("href", "")
        if href and href not in seen_hrefs:
            seen_hrefs.add(href)
            link_obj = {"text": l.get("text", href)[:40], "href": href}

            if href.startswith("/") or href.startswith("#"):
                internal_links.append(link_obj)
            elif href.startswith("http"):
                external_links.append(link_obj)

    if internal_links or external_links:
        nav_data = {}
        if internal_links:
            nav_data["internal"] = internal_links[:10]
        if external_links:
            nav_data["external"] = external_links[:5]
        toon_data["navigation"] = nav_data

    # === TECHNICAL DETAILS ===
    toon_data["technical"] = {
        "maxDepth": metadata.get("max_depth", 0),
        "hasImportantSections": metadata.get("has_important_sections", False),
        "containsForms": metadata.get("contains_forms", False),
        "containsVisualizations": metadata.get("contains_visualizations", False),
    }

    # === SUMMARY (Enhanced - addresses Gap #5) ===
    summary = _generate_page_summary(
        title=title,
        description=description,
        purposes=purposes,
        component_count=comp_counts.get("total", 0),
        callback_count=callback_count,
        has_forms=metadata.get("contains_forms", False),
        has_visualizations=metadata.get("contains_visualizations", False),
    )
    toon_data["summary"] = summary

    # Metadata
    if config.include_metadata:
        toon_data["_meta"] = {
            "gen": "dash-improve-my-llms",
            "v": "1.1.0",
            "fmt": "toon/3.1",  # Version bump for enhanced format
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
            "version": "1.1.0",
            "format": "toon/3.0",
        }

    return toon_encode(toon_data, config)


__all__ = [
    "TOONConfig",
    "TOONEncoder",
    "toon_encode",
    "generate_llms_toon",
    "generate_architecture_toon",
    "extract_markdown_content",
    "parse_markdown_content",
    "compress_code_example",
    "compress_section_content",
    "needs_quoting",
    "format_toon_value",
]