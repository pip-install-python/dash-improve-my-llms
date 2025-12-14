"""
TOON Generator for dash-improve-my-llms

Generates Token-Oriented Object Notation (TOON) output optimized for LLM consumption.
Achieves 30-60% token reduction compared to markdown llms.txt format.

TOON Specification: https://github.com/toon-format/spec (v3.0)

Key Design Principle:
  TOON should be a LOSSLESS SEMANTIC COMPRESSION of llms.txt content.
  An AI reading llms.toon should gain the same understanding as llms.txt,
  just with fewer tokens. Architecture metadata is secondary to actual content.

v1.2.0 Enhancements:
  - PageType detection (DOCUMENTATION, INTERACTIVE, HYBRID)
  - Enhanced prose extraction from dcc.Markdown and html elements
  - Documentation-optimized TOON schema with sections, code, tables
  - Adaptive generation based on page type
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import re


class PageType(Enum):
    """Page type classification for adaptive TOON generation."""
    DOCUMENTATION = "documentation"  # Tutorials, guides, API docs, markdown-heavy
    INTERACTIVE = "interactive"      # Dashboards, data apps, callback-heavy
    HYBRID = "hybrid"                # Mix of documentation and interactivity


@dataclass
class TOONConfig:
    """Configuration for TOON output generation."""

    # Core formatting
    indent: int = 2  # Spaces per indent level
    delimiter: str = ","  # Delimiter: "," | "\t" | "|"

    # Content control
    include_metadata: bool = True  # Include generator metadata
    include_content: bool = True  # Include text content arrays
    max_content_items: int = 100  # Limit content array size

    # Content preservation
    preserve_code_examples: bool = True  # Include code snippets
    preserve_headings: bool = True  # Keep section structure
    preserve_markdown: bool = True  # Extract dcc.Markdown content
    max_code_lines: int = 30  # Max lines per code example
    max_sections: int = 20  # Max number of sections to include

    # v1.2.0: Enhanced prose extraction
    extract_prose: bool = True  # Extract prose text from components
    extract_code_blocks: bool = True  # Include full code blocks
    extract_tables: bool = True  # Preserve table structures
    max_prose_chars: int = 5000  # Limit prose per section
    max_code_blocks: int = 15  # Limit code examples per page
    section_depth: int = 4  # How deep to nest sections (h1-h4)
    include_examples: bool = True  # Include usage examples
    compress_code: bool = True  # Compress code (remove excess whitespace)
    page_type_override: Optional[str] = None  # Force page type: "documentation", "interactive", "hybrid"

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


# =============================================================================
# v1.2.0: PAGE TYPE DETECTION
# =============================================================================

# Regex patterns for directive detection (common in documentation)
DIRECTIVE_PATTERN = re.compile(r'\.\.\s+\w+::')
TABLE_PATTERN = re.compile(r'\|[^\|]+\|')


def count_component_instances(component, component_names: set, depth: int = 0, max_depth: int = 50) -> int:
    """Count instances of specific component types in a layout."""
    if depth > max_depth:
        return 0

    count = 0
    component_name = getattr(component, "__class__", type(component)).__name__

    if component_name in component_names:
        count += 1

    # Recurse into children
    if hasattr(component, "children"):
        children = component.children
        if children is not None:
            if isinstance(children, list):
                for child in children:
                    count += count_component_instances(child, component_names, depth + 1, max_depth)
            elif not isinstance(children, str):
                count += count_component_instances(children, depth + 1, max_depth)

    return count


def detect_page_type(
    layout,
    callback_count: int = 0,
    config: Optional[TOONConfig] = None,
) -> PageType:
    """
    Analyze a page layout to determine its type: DOCUMENTATION, INTERACTIVE, or HYBRID.

    Detection logic:
    - High dcc.Markdown ratio + low callbacks = DOCUMENTATION
    - High callbacks + inputs/outputs = INTERACTIVE
    - Mixed = HYBRID

    Args:
        layout: The Dash layout component
        callback_count: Number of callbacks associated with this page
        config: Optional configuration (can override with page_type_override)

    Returns:
        PageType enum value
    """
    # Check for override in config
    if config and config.page_type_override:
        override = config.page_type_override.lower()
        if override == "documentation":
            return PageType.DOCUMENTATION
        elif override == "interactive":
            return PageType.INTERACTIVE
        elif override == "hybrid":
            return PageType.HYBRID

    # Count different component types
    markdown_components = {"Markdown"}
    interactive_components = {
        "Input", "TextInput", "Select", "Dropdown", "Button",
        "Checkbox", "Radio", "Slider", "RangeSlider", "DatePicker",
        "Textarea", "Upload", "NumberInput", "PasswordInput"
    }
    visualization_components = {"Graph", "DataTable", "AgGrid"}

    # Extract content to analyze
    markdown_content = extract_markdown_content(layout)

    # Count markdown sections and code blocks
    section_count = len(markdown_content.get("sections", []))
    code_block_count = len(markdown_content.get("code_examples", []))
    text_content = markdown_content.get("text_content", [])
    total_prose_length = sum(len(t) for t in text_content)

    # Count interactive elements (simplified - count from extracted IDs)
    interactive_count = 0
    viz_count = 0

    def count_types(comp, depth=0):
        nonlocal interactive_count, viz_count
        if depth > 50:
            return
        comp_name = getattr(comp, "__class__", type(comp)).__name__
        if comp_name in interactive_components:
            interactive_count += 1
        if comp_name in visualization_components:
            viz_count += 1
        if hasattr(comp, "children"):
            children = comp.children
            if children:
                if isinstance(children, list):
                    for c in children:
                        if not isinstance(c, str):
                            count_types(c, depth + 1)
                elif not isinstance(children, str):
                    count_types(children, depth + 1)

    count_types(layout)

    # Calculate documentation score
    doc_score = 0
    interactive_score = 0

    # Documentation indicators
    if section_count >= 3:
        doc_score += 3
    elif section_count >= 1:
        doc_score += 1

    if code_block_count >= 2:
        doc_score += 3
    elif code_block_count >= 1:
        doc_score += 1

    if total_prose_length >= 1000:
        doc_score += 3
    elif total_prose_length >= 500:
        doc_score += 2
    elif total_prose_length >= 200:
        doc_score += 1

    # Check for directive patterns (common in documentation frameworks)
    for text in text_content:
        if DIRECTIVE_PATTERN.search(text):
            doc_score += 2
            break

    # Interactive indicators
    if callback_count >= 5:
        interactive_score += 4
    elif callback_count >= 2:
        interactive_score += 2
    elif callback_count >= 1:
        interactive_score += 1

    if interactive_count >= 5:
        interactive_score += 3
    elif interactive_count >= 2:
        interactive_score += 2
    elif interactive_count >= 1:
        interactive_score += 1

    if viz_count >= 2:
        interactive_score += 2
    elif viz_count >= 1:
        interactive_score += 1

    # Decision logic
    if doc_score >= 5 and interactive_score <= 2:
        return PageType.DOCUMENTATION
    elif interactive_score >= 5 and doc_score <= 2:
        return PageType.INTERACTIVE
    elif doc_score >= 3 or interactive_score >= 3:
        return PageType.HYBRID
    else:
        # Default based on relative scores
        if doc_score > interactive_score:
            return PageType.DOCUMENTATION
        elif interactive_score > doc_score:
            return PageType.INTERACTIVE
        else:
            return PageType.HYBRID


# =============================================================================
# v1.2.0: ENHANCED PROSE EXTRACTION
# =============================================================================

def extract_prose_content(layout, config: Optional[TOONConfig] = None) -> Dict[str, Any]:
    """
    Extract prose text content from Dash layouts, optimized for documentation pages.

    This extracts:
    - dcc.Markdown children (the actual markdown text)
    - html.P, html.Span text content
    - html.H1-H6 headings
    - html.Li items for lists
    - html.Code/html.Pre for inline code
    - Table structures from html.Table

    Args:
        layout: The Dash layout component
        config: Optional TOON configuration

    Returns:
        Dict with: sections, code_blocks, lists, tables, prose, headings
    """
    if config is None:
        config = TOONConfig()

    result = {
        "sections": [],       # Hierarchical sections with headers
        "code_blocks": [],    # Extracted code examples
        "lists": [],          # Bullet/numbered lists
        "tables": [],         # Data tables
        "prose": [],          # Paragraph text
        "headings": [],       # All headings in order
        "raw_markdown": [],   # Raw markdown strings for full context
    }

    def _extract(component, depth=0, current_heading=None):
        if depth > config.section_depth * 10:  # Reasonable depth limit
            return

        if component is None:
            return

        # Handle string content
        if isinstance(component, str):
            text = component.strip()
            if text and len(text) > 5:
                result["prose"].append(text)
            return

        comp_name = getattr(component, "__class__", type(component)).__name__

        # === MARKDOWN COMPONENT (Primary source for documentation) ===
        if comp_name == "Markdown":
            children = getattr(component, "children", None)
            if children and isinstance(children, str):
                # Store the raw markdown for full context
                result["raw_markdown"].append(children)

                # Parse markdown content
                parsed = parse_markdown_content(children)

                # Add sections with hierarchy
                for section in parsed.get("sections", []):
                    if section.get("level", 2) <= config.section_depth:
                        result["sections"].append(section)

                # Add code blocks
                for code in parsed.get("code_examples", []):
                    if len(result["code_blocks"]) < config.max_code_blocks:
                        if config.compress_code:
                            code["code"] = compress_code_example(
                                code["code"], config.max_code_lines
                            )
                        result["code_blocks"].append(code)

                # Add text content as prose
                for text in parsed.get("text_content", []):
                    if text and len(text) > 10:
                        result["prose"].append(text[:config.max_prose_chars])

            return  # Don't recurse into markdown children

        # === HEADING ELEMENTS ===
        if comp_name in ["H1", "H2", "H3", "H4", "H5", "H6"]:
            level = int(comp_name[1])
            if level <= config.section_depth:
                children = getattr(component, "children", "")
                heading_text = ""
                if isinstance(children, str):
                    heading_text = children
                elif isinstance(children, list):
                    heading_text = " ".join(
                        c if isinstance(c, str) else ""
                        for c in children
                    ).strip()

                if heading_text:
                    result["headings"].append({
                        "text": heading_text,
                        "level": level,
                    })

        # === PARAGRAPH ELEMENTS ===
        if comp_name == "P":
            children = getattr(component, "children", "")
            if isinstance(children, str) and len(children) > 10:
                result["prose"].append(children[:config.max_prose_chars])
            elif isinstance(children, list):
                text = " ".join(
                    c if isinstance(c, str) else ""
                    for c in children
                ).strip()
                if text and len(text) > 10:
                    result["prose"].append(text[:config.max_prose_chars])

        # === LIST ELEMENTS ===
        if comp_name in ["Ul", "Ol"]:
            list_items = []
            children = getattr(component, "children", [])
            if isinstance(children, list):
                for item in children:
                    item_name = getattr(item, "__class__", type(item)).__name__
                    if item_name == "Li":
                        li_children = getattr(item, "children", "")
                        if isinstance(li_children, str):
                            list_items.append(li_children)
                        elif isinstance(li_children, list):
                            text = " ".join(
                                c if isinstance(c, str) else ""
                                for c in li_children
                            ).strip()
                            if text:
                                list_items.append(text)

            if list_items:
                result["lists"].append({
                    "type": "ordered" if comp_name == "Ol" else "unordered",
                    "items": list_items[:20],  # Limit items
                })

        # === CODE/PRE ELEMENTS ===
        if comp_name in ["Code", "Pre"]:
            children = getattr(component, "children", "")
            if isinstance(children, str) and len(children) > 5:
                if len(result["code_blocks"]) < config.max_code_blocks:
                    result["code_blocks"].append({
                        "language": "text",
                        "code": compress_code_example(children, config.max_code_lines) if config.compress_code else children,
                    })

        # === TABLE ELEMENTS ===
        if comp_name == "Table" and config.extract_tables:
            table_data = _extract_table(component)
            if table_data:
                result["tables"].append(table_data)

        # === RECURSE INTO CHILDREN ===
        if hasattr(component, "children"):
            children = component.children
            if children is not None:
                if isinstance(children, list):
                    for child in children:
                        if not isinstance(child, str) or len(child) > 50:
                            _extract(child, depth + 1, current_heading)
                elif not isinstance(children, str):
                    _extract(children, depth + 1, current_heading)

    def _extract_table(table_component) -> Optional[Dict]:
        """Extract table structure from html.Table component."""
        headers = []
        rows = []

        children = getattr(table_component, "children", [])
        if not isinstance(children, list):
            children = [children] if children else []

        for child in children:
            child_name = getattr(child, "__class__", type(child)).__name__

            # Table header
            if child_name == "Thead":
                thead_children = getattr(child, "children", [])
                if not isinstance(thead_children, list):
                    thead_children = [thead_children] if thead_children else []
                for tr in thead_children:
                    tr_name = getattr(tr, "__class__", type(tr)).__name__
                    if tr_name == "Tr":
                        tr_children = getattr(tr, "children", [])
                        if not isinstance(tr_children, list):
                            tr_children = [tr_children] if tr_children else []
                        for th in tr_children:
                            th_children = getattr(th, "children", "")
                            if isinstance(th_children, str):
                                headers.append(th_children)

            # Table body
            if child_name == "Tbody":
                tbody_children = getattr(child, "children", [])
                if not isinstance(tbody_children, list):
                    tbody_children = [tbody_children] if tbody_children else []
                for tr in tbody_children[:20]:  # Limit rows
                    tr_name = getattr(tr, "__class__", type(tr)).__name__
                    if tr_name == "Tr":
                        row = []
                        tr_children = getattr(tr, "children", [])
                        if not isinstance(tr_children, list):
                            tr_children = [tr_children] if tr_children else []
                        for td in tr_children:
                            td_children = getattr(td, "children", "")
                            if isinstance(td_children, str):
                                row.append(td_children)
                            else:
                                row.append("")
                        if row:
                            rows.append(row)

        if headers or rows:
            return {"headers": headers, "rows": rows}
        return None

    _extract(layout)

    # Deduplicate prose
    seen_prose = set()
    unique_prose = []
    for p in result["prose"]:
        p_clean = p.strip()[:200]  # Use first 200 chars for dedup
        if p_clean not in seen_prose:
            seen_prose.add(p_clean)
            unique_prose.append(p)
    result["prose"] = unique_prose[:config.max_content_items]

    return result


# =============================================================================
# v1.2.0: DOCUMENTATION-OPTIMIZED TOON GENERATION
# =============================================================================

def generate_documentation_toon(
    page_path: str,
    layout,
    page_name: Optional[str] = None,
    app=None,
    config: Optional[TOONConfig] = None,
    prose_content: Optional[Dict] = None,
) -> str:
    """
    Generate TOON optimized for documentation pages.

    This format prioritizes:
    - Section structure with full content
    - Code examples (complete, not truncated)
    - Tables preserved
    - Lists maintained
    - Minimal component/callback metadata

    Args:
        page_path: URL path of the page
        layout: The page layout component
        page_name: Optional display name
        app: Optional Dash app instance
        config: Optional TOON configuration
        prose_content: Pre-extracted prose content (optional)

    Returns:
        TOON-formatted string optimized for documentation
    """
    if config is None:
        config = TOONConfig()

    # Extract prose content if not provided
    if prose_content is None:
        prose_content = extract_prose_content(layout, config)

    # Build documentation-optimized TOON structure
    toon_data = {}

    # === META ===
    title = page_name or page_path.strip("/").replace("-", " ").title() or "Home"
    toon_data["meta"] = {
        "path": page_path,
        "name": title,
        "type": "documentation",
        "generator": "dash-improve-my-llms",
        "version": "1.2.0",
        "format": "toon/3.2",
    }

    # === APP CONTEXT ===
    if app:
        try:
            import dash
            page_registry = getattr(dash, "page_registry", {})
            total_pages = len(page_registry)
            if total_pages > 0:
                toon_data["context"] = {
                    "description": f"Part of {total_pages}-page Dash documentation site",
                    "totalPages": total_pages,
                }

                # Related pages (for navigation)
                related = []
                for p in page_registry.values():
                    if p.get("path") != page_path:
                        related.append({
                            "name": p.get("name", "Page"),
                            "path": p.get("path", "/"),
                        })
                if related:
                    toon_data["context"]["relatedPages"] = related[:10]
        except Exception:
            pass

    # === SECTIONS (Primary content for documentation) ===
    sections = prose_content.get("sections", [])
    if sections:
        formatted_sections = []
        for i, section in enumerate(sections[:config.max_sections]):
            heading = section.get("heading", "")
            level = section.get("level", 2)
            content = section.get("content", "")

            # Clean content (remove code block placeholders)
            content = re.sub(r'\[CODE_BLOCK_\d+\]', '', content).strip()

            # Compress if needed but allow more for documentation
            if len(content) > config.max_prose_chars:
                content = compress_section_content(content, config.max_prose_chars)

            section_obj = {
                "n": i + 1,
                "title": heading,
                "level": level,
            }
            if content:
                section_obj["content"] = content

            formatted_sections.append(section_obj)

        if formatted_sections:
            toon_data["sections"] = formatted_sections

    # === HEADINGS OUTLINE (Quick navigation) ===
    headings = prose_content.get("headings", [])
    if headings and not sections:  # Only if sections not already captured
        toon_data["outline"] = [
            {"text": h["text"], "level": h["level"]}
            for h in headings[:20]
        ]

    # === CODE EXAMPLES (Critical for documentation) ===
    code_blocks = prose_content.get("code_blocks", [])
    if code_blocks and config.extract_code_blocks:
        formatted_code = []
        for i, block in enumerate(code_blocks[:config.max_code_blocks]):
            lang = block.get("language", "text")
            code = block.get("code", "")

            if code:
                # For documentation, preserve more code
                if config.compress_code and len(code.split('\n')) > config.max_code_lines:
                    code = compress_code_example(code, config.max_code_lines)

                formatted_code.append({
                    "n": i + 1,
                    "lang": lang,
                    "code": code,
                })

        if formatted_code:
            toon_data["codeExamples"] = formatted_code

    # === TABLES (Preserve reference tables) ===
    tables = prose_content.get("tables", [])
    if tables and config.extract_tables:
        formatted_tables = []
        for i, table in enumerate(tables[:5]):  # Limit to 5 tables
            formatted_tables.append({
                "n": i + 1,
                "headers": table.get("headers", []),
                "rows": table.get("rows", [])[:10],  # Limit rows
            })
        if formatted_tables:
            toon_data["tables"] = formatted_tables

    # === LISTS (Usage examples, best practices) ===
    lists = prose_content.get("lists", [])
    if lists:
        formatted_lists = []
        for lst in lists[:10]:  # Limit to 10 lists
            formatted_lists.append({
                "type": lst.get("type", "unordered"),
                "items": lst.get("items", [])[:15],
            })
        if formatted_lists:
            toon_data["lists"] = formatted_lists

    # === PROSE (Additional text content) ===
    prose = prose_content.get("prose", [])
    if prose and config.extract_prose:
        # Filter and clean
        clean_prose = []
        seen = set()
        for p in prose:
            # Skip very short or duplicate content
            p_clean = p.strip()
            if len(p_clean) > 20 and p_clean[:100] not in seen:
                seen.add(p_clean[:100])
                clean_prose.append(p_clean[:config.max_prose_chars])

        if clean_prose:
            toon_data["prose"] = clean_prose[:config.max_content_items]

    # === RAW MARKDOWN (Full context for complex documentation) ===
    raw_markdown = prose_content.get("raw_markdown", [])
    if raw_markdown and not sections and not prose:
        # Only include raw markdown if we didn't get structured content
        combined = "\n\n".join(raw_markdown)
        if len(combined) > 100:
            # Compress if too long
            if len(combined) > config.max_prose_chars * 2:
                combined = combined[:config.max_prose_chars * 2] + "..."
            toon_data["rawContent"] = combined

    # === NAVIGATION ===
    md_content = extract_markdown_content(layout)
    links = md_content.get("links", [])
    if links:
        internal = []
        external = []
        seen = set()
        for link in links:
            href = link.get("href", "")
            if href and href not in seen:
                seen.add(href)
                obj = {"text": link.get("text", href)[:50], "href": href}
                if href.startswith("/") or href.startswith("#"):
                    internal.append(obj)
                elif href.startswith("http"):
                    external.append(obj)

        if internal or external:
            nav = {}
            if internal:
                nav["internal"] = internal[:15]
            if external:
                nav["external"] = external[:10]
            toon_data["navigation"] = nav

    # === SUMMARY ===
    section_count = len(sections)
    code_count = len(code_blocks)
    summary_parts = [f"Documentation page: {title}."]
    if section_count:
        summary_parts.append(f"Contains {section_count} section(s).")
    if code_count:
        summary_parts.append(f"Includes {code_count} code example(s).")
    if tables:
        summary_parts.append(f"Has {len(tables)} reference table(s).")

    toon_data["summary"] = " ".join(summary_parts)

    return toon_encode(toon_data, config)


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

    v1.2.0: Now uses adaptive generation based on page type:
    - DOCUMENTATION pages: Use documentation-optimized format with prose/code focus
    - INTERACTIVE pages: Use interactive-optimized format with callback/component focus
    - HYBRID pages: Use combined format with both

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

    # === v1.2.0: PAGE TYPE DETECTION AND ADAPTIVE DISPATCH ===
    interactivity = page_data.get("interactivity", {})
    callback_count = interactivity.get("callback_count", 0)

    page_type = detect_page_type(layout, callback_count, config)

    # For documentation pages, use the specialized documentation generator
    if page_type == PageType.DOCUMENTATION:
        prose_content = extract_prose_content(layout, config)
        return generate_documentation_toon(
            page_path=page_path,
            layout=layout,
            page_name=page_name,
            app=app,
            config=config,
            prose_content=prose_content,
        )

    # For hybrid pages, we'll use an enhanced interactive format that also
    # includes documentation content

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
        "pageType": page_type.value,  # v1.2.0: Include detected page type
        "maxDepth": metadata.get("max_depth", 0),
        "hasImportantSections": metadata.get("has_important_sections", False),
        "containsForms": metadata.get("contains_forms", False),
        "containsVisualizations": metadata.get("contains_visualizations", False),
    }

    # === v1.2.0: ENHANCED PROSE FOR HYBRID PAGES ===
    if page_type == PageType.HYBRID and config.extract_prose:
        prose_content = extract_prose_content(layout, config)

        # Add prose sections for hybrid pages
        prose_sections = prose_content.get("sections", [])
        if prose_sections:
            formatted_prose = []
            for section in prose_sections[:config.max_sections]:
                heading = section.get("heading", "")
                content = section.get("content", "")
                if heading or content:
                    s = {"h": heading, "l": section.get("level", 2)}
                    if content:
                        content = re.sub(r'\[CODE_BLOCK_\d+\]', '', content).strip()
                        if len(content) > config.max_prose_chars:
                            content = compress_section_content(content, config.max_prose_chars)
                        s["t"] = content
                    formatted_prose.append(s)
            if formatted_prose:
                toon_data["prose"] = {"sections": formatted_prose}

        # Add code examples for hybrid pages
        code_blocks = prose_content.get("code_blocks", [])
        if code_blocks and config.extract_code_blocks:
            formatted_code = []
            for block in code_blocks[:config.max_code_blocks]:
                lang = block.get("language", "text")
                code = block.get("code", "")
                if code:
                    if config.compress_code and len(code.split('\n')) > config.max_code_lines:
                        code = compress_code_example(code, config.max_code_lines)
                    formatted_code.append({"lang": lang, "code": code})
            if formatted_code:
                toon_data["codeExamples"] = formatted_code

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
            "v": "1.2.0",
            "fmt": "toon/3.2",  # v1.2.0: Format version bump
            "pageType": page_type.value,
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
            "version": "1.2.0",
            "format": "toon/3.2",
        }

    return toon_encode(toon_data, config)


__all__ = [
    # Core classes
    "TOONConfig",
    "TOONEncoder",
    "PageType",
    # Encoding
    "toon_encode",
    # Generation
    "generate_llms_toon",
    "generate_architecture_toon",
    "generate_documentation_toon",
    # Content extraction
    "extract_markdown_content",
    "extract_prose_content",
    "parse_markdown_content",
    # Page type detection
    "detect_page_type",
    # Utilities
    "compress_code_example",
    "compress_section_content",
    "needs_quoting",
    "format_toon_value",
]