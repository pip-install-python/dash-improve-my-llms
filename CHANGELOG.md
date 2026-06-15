# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-05-26

### Breaking Changes — scope rescoped for the Dash 4.x / MCP era

2.0 narrows the package to the surfaces that Dash 4.3's MCP server and
native Dash do NOT cover. Component-tree introspection — which Dash MCP
exposes live and structurally — has been removed. The package now
focuses on three audiences:

| Audience              | How they reach the app          | What 2.0 serves them                         |
|-----------------------|---------------------------------|----------------------------------------------|
| MCP clients           | JSON-RPC over Streamable HTTP   | `LLMS_DOC` registered as `dash.mcp` resource |
| Web crawlers          | Plain HTTPS, often no JS        | `/robots.txt`, `/sitemap.xml`, static HTML   |
| Paste-into-chat users | One-shot HTTP fetch             | `/llms.txt`, `/<page>/llms.txt` as markdown  |

### Removed

- `/page.json` and `/<page>/page.json` — Dash 4.3 MCP exposes layouts as
  resources natively.
- `/architecture.txt` and `/architecture.toon` — MCP describes
  component hierarchy more accurately and live per request.
- `/llms.toon` and `/<page>/llms.toon` — the entire `toon_generator.py`
  module (~1,900 lines).
- Component-tree extraction portion of `/llms.txt` — replaced by
  the explicit `LLMS_DOC` pattern.
- `mark_important()` and `mark_component_hidden()` — these up-ranked
  and excluded sections during layout extraction; with no extraction,
  they have no job. Kept as deprecation-warning no-ops for one release.
- `TOONConfig`, `PageType`, `generate_llms_toon`,
  `generate_architecture_toon`, `generate_documentation_toon`,
  `toon_encode`, `detect_page_type`, `extract_prose_content`,
  `extract_markdown_content` — all removed from the public API.

### Added

- **Multi-backend support** via a backend-detecting dispatcher in
  `add_llms_routes(app)`. The package now works under Flask, FastAPI,
  and Quart (Dash 4.1+) without any caller changes.
  - `dash_improve_my_llms/_flask_adapter.py`
  - `dash_improve_my_llms/_fastapi_adapter.py` (new)
  - `dash_improve_my_llms/_quart_adapter.py` (new)
- **MCP bridge** (`dash_improve_my_llms/_mcp_bridge.py`) — registers
  each non-hidden page's `LLMS_DOC` as a `dash.mcp` resource when
  Dash 4.3+ is available. Silent no-op on older Dash.
- **`LLMS_DOC` pattern** — every page module exports a module-level
  `LLMS_DOC = "..."` string. That string is served verbatim at
  `/<page>/llms.txt` and registered as the MCP resource body. No layout
  walking, no extraction, no surprises.
- **`register_page_metadata(path, llms_doc="...")`** — an alternative
  way to provide prose for pages whose docs are auto-generated or
  imported.
- **Missing-LLMS_DOC warning** — `add_llms_routes()` now emits a single
  `UserWarning` naming every non-hidden page without prose. Silence with
  `LLMSConfig(warn_missing_llms_doc=False)`.
- **Stub fallback** — pages without `LLMS_DOC` get a small placeholder
  body at their `/llms.txt` endpoint so bots receive a 200 instead of
  a 404. The stub names the page and explains how to add real prose.
- **Pure framework-agnostic handlers** in
  `dash_improve_my_llms/handlers.py`. Bot decisions, page lookup, and
  body generation are now testable without spinning up a server.
- **`LLMSConfig.register_mcp_resources`** flag (default `True`) — opt
  out of MCP bridge registration without touching the HTTP surfaces.

### Changed

- `add_llms_routes(app, config)` now detects the backend via
  `dash.backends.get_server_type` (Dash 4.2+) with a fallback to
  `type(app.server).__name__` for older Dash and unusual servers.
- `register_page_metadata()` now accepts a `llms_doc=` kwarg.
- Static-HTML prerender for crawlers now renders the page's
  `LLMS_DOC` as HTML (minimal markdown parser, no extra deps) instead
  of dumping the component tree.
- `pyproject.toml` no longer hard-depends on Flask. Install one of:
  - `pip install dash-improve-my-llms[flask]` (default for Dash 3.x)
  - `pip install dash-improve-my-llms[fastapi]` (Dash 4.1+)
  - `pip install dash-improve-my-llms[quart]` (Dash 4.1+ async)
  - `pip install dash-improve-my-llms[all]`

### Migration from 1.x

For most apps, 2.0 migration is:

1. Add a `LLMS_DOC = """..."""` string at module scope on each page.
   You'll see a `UserWarning` at startup naming pages that need one.
2. Remove `mark_important(...)` and `mark_component_hidden(...)` calls.
   They're no-op shims in 2.0 and will be deleted in 2.1.
3. Update any links / references pointing at `/page.json`,
   `/architecture.txt`, or `/llms.toon` — those endpoints are gone.
4. Install the matching backend extra (`[flask]`, `[fastapi]`, or
   `[quart]`).

The HTTP surfaces that survived (`/llms.txt`, `/robots.txt`,
`/sitemap.xml`) and the `RobotsConfig`, `mark_hidden`,
`register_page_metadata` APIs are unchanged.

### Internal

- Public package surface: 4,373 → ~1,930 lines.
- `__init__.py`: 1,682 → ~290 lines (now mostly the dispatcher).
- Three new framework adapters total ~250 lines.
- Pure-function `handlers.py` (~380 lines) is testable without any
  server.

---

## [1.2.0] - 2025-12-13

### 🎯 Documentation-Aware TOON Generation

This release introduces **adaptive page type detection** and **documentation-optimized TOON generation**. The hook now intelligently detects whether a page is documentation, interactive, or hybrid, and generates TOON content optimized for each type.

### ✨ New Features

#### Page Type Detection
- **`PageType` Enum**: New enum with `DOCUMENTATION`, `INTERACTIVE`, and `HYBRID` values
- **`detect_page_type()`**: Automatically analyzes page layouts to determine content type
- **Scoring System**: Uses markdown content, section count, code blocks, callbacks, and interactive components

```python
from dash_improve_my_llms import detect_page_type, PageType

page_type = detect_page_type(layout, callback_count=2)
# Returns: PageType.DOCUMENTATION, PageType.INTERACTIVE, or PageType.HYBRID
```

#### Documentation-Optimized TOON Generation
- **`generate_documentation_toon()`**: New function for documentation-heavy pages
- **Full Prose Extraction**: Captures complete markdown content, not just structure
- **Code Block Preservation**: Maintains full code examples with language detection
- **Table Extraction**: Parses and preserves HTML tables for reference documentation
- **List Processing**: Extracts ordered and unordered lists

```python
from dash_improve_my_llms import generate_documentation_toon

toon_output = generate_documentation_toon(
    page_path="/examples/directives",
    layout=layout,
    page_name="Custom Directives",
    app=app
)
```

#### Enhanced Prose Extraction
- **`extract_prose_content()`**: New comprehensive text extraction function
- **Extracts from multiple sources**:
  - `dcc.Markdown` children (raw markdown text)
  - `html.P` paragraph content
  - `html.H1-H6` headings
  - `html.Li` list items
  - `html.Code/Pre` code elements
  - `html.Table` structures

```python
from dash_improve_my_llms import extract_prose_content

prose = extract_prose_content(layout)
# Returns: {
#   "sections": [...],
#   "code_blocks": [...],
#   "lists": [...],
#   "tables": [...],
#   "prose": [...],
#   "headings": [...],
#   "raw_markdown": [...]
# }
```

#### New TOONConfig Options
```python
from dash_improve_my_llms import TOONConfig

config = TOONConfig(
    # v1.2.0 New Options
    extract_prose=True,           # Extract prose text from components
    extract_code_blocks=True,     # Include full code blocks
    extract_tables=True,          # Preserve table structures
    max_prose_chars=5000,         # Limit prose per section
    max_code_blocks=15,           # Limit code examples per page
    section_depth=4,              # How deep to nest sections (h1-h4)
    include_examples=True,        # Include usage examples
    compress_code=True,           # Compress code (remove excess whitespace)
    page_type_override=None,      # Force: "documentation", "interactive", "hybrid"
)
```

#### Adaptive TOON Generation
`generate_llms_toon()` now automatically dispatches to the appropriate generator:
- **DOCUMENTATION pages**: Uses `generate_documentation_toon()` for prose-focused output
- **INTERACTIVE pages**: Uses component/callback-focused format
- **HYBRID pages**: Combines both with prose sections and code examples alongside interactive metadata

### 📊 Documentation TOON Format (v3.2)

Documentation pages now generate a specialized format optimized for tutorials, guides, and API docs:

```toon
meta:
  path: /examples/directives
  name: Custom Directives
  type: documentation
  generator: dash-improve-my-llms
  version: 1.2.0
  format: toon/3.2

context:
  description: Part of 7-page Dash documentation site
  totalPages: 7
  relatedPages[6]{name,path}:
    Getting Started,/getting-started
    Interactive Components,/examples/components
    ...

sections[5]:
  1:
    n: 1
    title: Table of Contents Directive
    level: 2
    content: >
      The toc directive generates navigation from markdown headings.
      Place it at the start of your documentation file...

  2:
    n: 2
    title: Execute Directive
    level: 2
    content: >
      The exec directive renders Python components inline with
      optional source code display...

codeExamples[3]:
  1:
    n: 1
    lang: python
    code: |
      from dash import html
      import dash_mantine_components as dmc

      component = dmc.Button("Click Me!", id="demo")

  2:
    n: 2
    lang: markdown
    code: |
      .. exec::docs.examples.button_example
          :code: false

tables[1]:
  1:
    n: 1
    headers: [Directive, Syntax, Purpose]
    rows[5]:
      [toc, ".. toc::", Generate table of contents]
      [exec, ".. exec::path", Render Python component]
      ...

lists[2]:
  1:
    type: unordered
    items[4]:
      - Use toc at the start of every page
      - Combine exec with source for examples
      ...

summary: Documentation page: Custom Directives. Contains 5 section(s). Includes 3 code example(s). Has 1 reference table(s).
```

### 🔧 Technical Changes

- TOON format version bumped to `toon/3.2`
- Package version bumped to `1.2.0`
- New exports in `__all__`: `PageType`, `detect_page_type`, `extract_prose_content`, `generate_documentation_toon`
- Hybrid pages now include prose sections and code examples alongside interactive metadata

### 💡 Use Cases

**For Documentation Sites (like Dash-Documentation-Boilerplate)**:
- Full prose content is captured from `dcc.Markdown` components
- Code examples are preserved for tutorials
- Directive syntax examples are maintained
- Reference tables are extractable

**For Interactive Dashboards**:
- Continues to use optimized callback/component format
- No changes to existing behavior

**For Mixed Applications**:
- Hybrid detection combines both approaches
- Documentation content appears alongside interactive metadata

### 💡 Breaking Changes

None - v1.2.0 is fully backward compatible with v1.1.0. Existing code continues to work without modification. The new page type detection is automatic and enhances output quality.

---

## [1.1.0] - 2025-12-13

### 🎯 Enhanced TOON Format: Lossless Semantic Compression

This release addresses the critical content gap between `llms.txt` and `llms.toon` formats. The TOON format now achieves **lossless semantic compression** - preserving all meaningful content while maintaining 40-50% token reduction.

### ✨ New Features

#### Enhanced Content Extraction
- **Markdown Content Extraction**: New `extract_markdown_content()` function captures content from `dcc.Markdown` components
- **Code Block Parsing**: New `parse_markdown_content()` extracts and preserves code examples from markdown
- **Smart Compression**: New `compress_code_example()` and `compress_section_content()` functions maintain essential information while reducing tokens

#### TOON Format v3.1 Improvements

**Gap #1 - Application Context**: Added explicit context framing
```toon
context: Part of multi-page Dash app with 3 total pages
related_pages[3]{path,name}:
  /,Home
  /equipment,Equipment Catalog
  /analytics,Analytics Dashboard
```

**Gap #2 - Page Purpose Explanations**: Human-readable purpose descriptions
```toon
purpose:
  flags: [data_input, interactive]
  explanation:
    - Contains form elements for data entry
    - Responds to user interactions with dynamic updates
```

**Gap #3 - Component Breakdown**: Type distribution added
```toon
components:
  total: 23
  interactive: 5
  static: 18
  breakdown:
    Div: 8
    Button: 3
    TextInput: 2
    Select: 2
    Graph: 1
```

**Gap #4 - Callback Descriptions**: Human-readable callback documentation
```toon
callbacks[2]:
  1:
    updates: equipment-list.children
    triggers: equipment-search.value, equipment-category.value
    description: Updates equipment list when search or category changes
  2:
    updates: stats-display.children
    triggers: equipment-list.children
    reads: current-filter.data
    description: Updates statistics based on filtered equipment list
```

**Gap #5 - Summary Section**: Synthesized page summary
```toon
summary: >
  Equipment Catalog is a data input and interactive page with 23 components
  (5 interactive) and 2 callbacks. Users can search and filter equipment
  with real-time updates. Contains forms and interactive visualizations.
```

**Gap #6 - Link Categorization**: Internal vs external links separated
```toon
navigation:
  internal[2]:
    Home: /
    Analytics: /analytics
  external[1]:
    Documentation: https://docs.example.com
```

#### New TOONConfig Options
```python
TOONConfig(
    preserve_code_examples=True,   # Include code snippets (NEW)
    preserve_headings=True,        # Keep section structure (NEW)
    preserve_markdown=True,        # Extract dcc.Markdown content (NEW)
    max_code_lines=30,             # Max lines per code example (NEW)
    max_sections=20,               # Max sections to include (NEW)
    max_content_items=100,         # Increased from 20 (UPDATED)
)
```

#### New Helper Functions
- `_generate_page_summary()`: Creates synthesized page summaries
- `_format_callback_description()`: Generates human-readable callback descriptions

### 🔧 Technical Changes

- TOON format version bumped to `toon/3.1`
- Package version bumped to `1.1.0`
- Enhanced `generate_llms_toon()` with all 6 gap fixes
- Improved content extraction depth and accuracy

### 📊 Token Efficiency

| Format | Tokens | Reduction |
|--------|--------|-----------|
| llms.txt | ~15,000 | baseline |
| llms.toon v1.0.0 | ~200 | 98% (too aggressive, lost content) |
| llms.toon v1.1.0 | ~6,000-8,000 | 40-50% (lossless semantic) |

### 💡 Design Principle

> **TOON should be a LOSSLESS SEMANTIC COMPRESSION of llms.txt content**
>
> The goal is not maximum token reduction, but optimal information density.
> All meaningful content is preserved while removing only formatting overhead.

### 💡 Breaking Changes

None - v1.1.0 is fully backward compatible with v1.0.0.

---

## [1.0.0] - 2025-12-07

### 🎉 Major Release: TOON Format Support

This release marks the **production-ready 1.0.0 milestone** with the addition of TOON (Token-Oriented Object Notation) format support, achieving **50-60% token reduction** compared to markdown llms.txt output.

### ✨ New Features

#### TOON Format Integration
- **New `/llms.toon` endpoint**: Token-optimized LLM documentation format
- **New `/<page>/llms.toon` endpoints**: Per-page TOON format support
- **New `/architecture.toon` endpoint**: Token-optimized application architecture
- **Built-in TOON encoder**: Works without external dependencies (fallback encoder)
- **Optional `python-toon` package support**: For full spec compliance

#### TOON Format Benefits
- **50-60% fewer tokens** compared to markdown llms.txt format
- **Tabular arrays** for uniform data structures (`[N]{fields}:` syntax)
- **Explicit length markers** for LLM validation
- **YAML-like readability** with JSON-compatible data model
- **Primitive arrays** inline format for lists

#### New Module: `toon_generator.py` (~600 lines)
- `TOONConfig` dataclass for configuration
- `TOONEncoder` class for TOON format encoding
- `toon_encode()` function with fallback support
- `generate_llms_toon()` for page-level TOON output
- `generate_architecture_toon()` for app-wide architecture

#### New Exports
```python
from dash_improve_my_llms import (
    TOONConfig,           # Configuration dataclass
    toon_encode,          # Low-level encoder
    generate_llms_toon,   # Page TOON generation
    generate_architecture_toon,  # App TOON generation
)
```

### 📝 Documentation Updates

- Updated `templates/index.html` with TOON discovery links
- Updated `html_generator.py` with TOON links in noscript sections
- Updated `app.py` with TOON route examples and documentation
- Updated `pages/home.py` with TOON feature showcase
- Created `TOON_INTEGRATION_PLAN.md` implementation guide

### 🔧 Technical Changes

- Version bumped to `1.0.0` (Production/Stable)
- Updated pyproject.toml classifiers to "Production/Stable"
- Added TOON-related keywords to package metadata
- Updated bot middleware to skip TOON routes

### 💡 TOON Format Example

**Markdown llms.txt (~312 tokens):**
```markdown
# Equipment Catalog

> Browse and filter the complete equipment catalog

## Interactive Elements
**User Inputs:**
- TextInput (ID: `equipment-search`) - Search equipment...
- Select (ID: `equipment-category`)
```

**TOON format (~127 tokens):**
```toon
page:
  path: /equipment
  name: Equipment Catalog
  description: Browse and filter the complete equipment catalog

interactive:
  inputs[2]{id,type,placeholder}:
    equipment-search,TextInput,Search equipment...
    equipment-category,Select,
```

### 📦 New Routes

| Route | Description |
|-------|-------------|
| `/llms.toon` | Token-optimized LLM documentation |
| `/<page>/llms.toon` | Per-page TOON format |
| `/architecture.toon` | Token-optimized architecture |

### 💡 Breaking Changes

None - v1.0.0 is fully backward compatible with v0.3.0.

### 🔗 References

- [TOON Specification v3.0](https://github.com/toon-format/spec)
- [python-toon PyPI](https://pypi.org/project/python-toon/)

---

## [0.3.0] - 2025-11-05

### 🎉 Enhanced Bot HTML Generation

Critical fix: AI chatbots (ChatGPT, Claude, etc.) can now properly see and navigate your Dash apps.

#### What Changed
- ✅ Bots now receive **comprehensive static HTML** with full content
- ✅ Complete **Schema.org structured data** for AI understanding
- ✅ Full **navigation structure** for proper crawling
- ✅ **SEO meta tags** and Open Graph support
- ✅ **Important sections** rendered as proper HTML

#### Technical Improvements
- Enhanced `html_generator.py` with full structured data
- Added Schema.org JSON-LD for all pages
- Improved navigation rendering for bots
- Added noscript fallback content

---

## [0.2.0] - 2025-11-04

### 🎉 Major New Features

#### Bot Detection & Response Middleware
- **Bot Detection System**: Automatically detect and categorize bots into three types:
  - **Training Bots**: GPTBot, anthropic-ai, CCBot, Google-Extended, etc.
  - **Search Bots**: ClaudeBot, ChatGPT-User, PerplexityBot, etc.
  - **Traditional Bots**: Googlebot, Bingbot, Yahoo, DuckDuckBot, etc.
- **Bot Response Middleware**: Serve different content based on bot type
  - Training bots: 403 Forbidden (when `block_ai_training=True`)
  - Search/Traditional bots: llms.txt content wrapped in HTML (solves JavaScript execution problem)
  - Browsers: Full Dash React application
- **Solves Critical Issue**: AI crawlers cannot execute JavaScript, so they now receive readable llms.txt content instead of empty `<div id="react-entry-point">` placeholders

#### robots.txt Generation
- **Dynamic robots.txt**: Automatically generated based on `RobotsConfig`
- **RobotsConfig Dataclass**: Configure bot access policies
  ```python
  RobotsConfig(
      block_ai_training=True,      # Block AI training bots
      allow_ai_search=True,        # Allow AI search bots
      allow_traditional=True,      # Allow traditional search bots
      crawl_delay=10,              # Crawl delay in seconds
      disallowed_paths=["/admin", "/api/*"]  # Paths to block
  )
  ```
- **Smart Bot Rules**: Automatically generates appropriate rules for each bot type
- **Hidden Pages**: Respects `mark_hidden()` for privacy control

#### sitemap.xml Generation
- **SEO-Optimized Sitemaps**: Automatic XML sitemap generation
- **Smart Priority Inference**: Automatically determines page priority based on:
  - Root pages (/) → High priority (0.9-1.0)
  - Important pages (marked with `mark_important()`) → Medium-high priority (0.7-0.8)
  - Detail pages (/item/:id) → Medium priority (0.5-0.6)
  - Utility pages (/settings) → Lower priority (0.3-0.5)
- **Respects Hidden Pages**: Pages marked with `mark_hidden()` are excluded from sitemap
- **Automatic Updates**: Always reflects current app structure

#### Visitor Analytics & Tracking
- **Device Detection**: Automatically detect device type (desktop, mobile, tablet, bot)
- **Bot Tracking**: Track bot visits with bot type categorization
- **Analytics Storage**: JSON-based visitor tracking with timestamps
- **Privacy-First**: File-based storage, no external services required

#### Admin Dashboard
- **Professional UI/UX**: Built with design.txt best practices
  - Restrained color palette (violet primary, gray secondary)
  - Systematic spacing tokens (xs, sm, md, lg, xl)
  - Progressive disclosure with tabs
  - Visual hierarchy (prominent numbers, small labels)
- **Three Main Tabs**:
  - **Overview**: Charts and visualizations
    - Total visits and device breakdown
    - Visits by hour (last 24h)
    - Device distribution pie chart
    - Top visited pages bar chart
  - **Bot Activity**: Detailed bot visit logs
    - Bot type categorization
    - User agent information
    - Visit timestamps
    - Path tracking
  - **Configuration**: Bot type reference and settings
    - Complete bot type documentation
    - Example user agents
    - Configuration examples
- **Real-time Data**: Auto-refreshing analytics
- **Hidden by Default**: Admin page excluded from robots.txt and sitemap.xml

### ✨ Enhanced Features

#### llms.txt Generation
- **Application Context**: Multi-page app information with related pages list
- **Page Purpose Inference**: Automatically determines page purpose
  - Data Input, Visualization, Navigation, Interactive
- **Interactive Elements**: Detailed breakdown of inputs and outputs with IDs
- **Navigation Mapping**: Internal and external links with destinations
- **Component Statistics**: Total, interactive, and static counts
- **Data Flow & Callbacks**: Complete callback information showing triggers
- **Narrative Summary**: Human-readable summary of page purpose

#### page.json Generation
- **Component IDs**: All component IDs extracted with types, modules, and properties
- **Component Categories**: Automatic categorization
  - inputs, outputs, containers, navigation, display, interactive
- **Navigation Data**: All links extracted with text and destinations
- **Interactivity Metadata**: has_callbacks, callback_count, interactive_components
- **Callback Information**: Full callback data with inputs, outputs, and state
- **Callback Graph**: Data flow graph showing trigger relationships
- **Rich Metadata**: Flags for forms, visualizations, and navigation

#### architecture.txt Generation
- **Environment Detection**: Python version, Dash version, key packages
- **Dependencies Context**: Automatically detects installed packages
- **Callback Breakdown**: Total callbacks grouped by module
- **Page Descriptions**: Includes custom metadata descriptions
- **Interactive Components**: Counts interactive vs static components per page
- **Enhanced Statistics**: Total pages, callbacks, components, interactive components
- **Top Components**: Shows most-used component types across entire app

### 🛠️ Technical Improvements

- **Flask Middleware Integration**: `before_request` hook for bot interception
- **Hidden Page Support**:
  - `mark_hidden(path)` - Hide entire page from bots
  - `mark_component_hidden(component)` - Hide specific components
- **Page Metadata Registration**: `register_page_metadata()` for custom descriptions
- **Comprehensive Testing**: 100% pass rate on bot response tests (7/7 passing)
  - Training bot blocking
  - Search bot llms.txt serving
  - Browser full app serving
  - Documentation link verification

### 📚 Documentation

- **Implementation Guides**:
  - BOT_MIDDLEWARE_IMPLEMENTATION.md - Complete middleware documentation
  - ADMIN_UX_IMPROVEMENTS.md - UI/UX design principles applied
  - IMPLEMENTATION_SUMMARY.md - Feature implementation summary
  - TEST_REPORT.md - Comprehensive test coverage report

- **Testing Scripts**:
  - test_bot_responses.py - Comprehensive Python test suite
  - test_bot_middleware.sh - Quick bash test script

- **Updated README**: Complete v0.2.0 feature documentation with examples

### 🐛 Bug Fixes

- Fixed `_reload-hash` requests being tracked in analytics
- Fixed RobotsConfig import error in __init__.py
- Fixed bot response differentiation (bots no longer receive React app)

### 💡 Breaking Changes

None - v0.2.0 is fully backward compatible with v0.1.0.

### 🔒 Security

- Training bot blocking prevents unauthorized content scraping for AI model training
- 403 Forbidden responses for blocked bots with clear error messages
- Admin dashboard hidden from search engines by default

---

## [0.1.0] - Initial Release

### Added
- Basic llms.txt generation for Dash pages
- page.json architecture export
- architecture.txt application overview
- `mark_important()` for highlighting key content
- `add_llms_routes()` hook for easy integration
- Multi-page Dash application support

---

**Made with ❤️ by Pip Install Python LLC**
- Homepage: https://pip-install-python.com
- Plotly Pro: https://plotly.pro
- Repository: https://github.com/pip-install-python/dash-improve-my-llms