# dash-improve-my-llms

**Make your Dash applications AI-friendly with automatic documentation, bot management, and SEO optimization.**

[![PyPI version](https://img.shields.io/badge/version-0.2.0-blue.svg)](https://pypi.org/project/dash-improve-my-llms/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-88%20passed-success.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-98%25-success.svg)](htmlcov/)

---

## 🎯 Overview

`dash-improve-my-llms` is a comprehensive plugin that automatically generates **five types of AI-friendly documentation and SEO resources** for your Dash application:

### Automatic Documentation (v0.1.0)

1. **`llms.txt`** - Comprehensive, context-rich markdown optimized for LLM understanding
2. **`page.json`** - Detailed technical architecture with interactivity and data flow
3. **`architecture.txt`** - ASCII art representation of entire application

### Bot Management & SEO (v0.2.0 - NEW!)

4. **`robots.txt`** - Intelligent bot control with AI training bot blocking
5. **`sitemap.xml`** - SEO-optimized sitemap with intelligent priority inference
6. **Static HTML** - Bot-friendly pages with structured data

### Privacy Controls (v0.2.0 - NEW!)

- **`mark_hidden()`** - Hide sensitive pages from AI bots and search engines
- **Bot Detection** - Differentiate between AI training, AI search, and traditional bots
- **Configurable Policies** - Fine-grained control over which bots can access what

---

## 🚀 Quick Start

### Installation

```bash
pip install dash-improve-my-llms
```

### Basic Setup (30 seconds)

```python
from dash import Dash
from dash_improve_my_llms import add_llms_routes

app = Dash(__name__, use_pages=True)
add_llms_routes(app)  # That's it! 🎉

if __name__ == '__main__':
    app.run(debug=True)
```

Now visit:
- `http://localhost:8050/llms.txt` - LLM-friendly page context
- `http://localhost:8050/page.json` - Technical architecture
- `http://localhost:8050/architecture.txt` - App overview
- `http://localhost:8050/robots.txt` - Bot access control **NEW!**
- `http://localhost:8050/sitemap.xml` - SEO sitemap **NEW!**

---

## ✨ Key Features

### 📄 Automatic Documentation

- **Three comprehensive formats** (llms.txt, page.json, architecture.txt)
- **Smart context extraction** - Understands your app structure
- **Callback tracking** - Documents all data flows
- **Component categorization** - Automatic classification by purpose
- **Navigation mapping** - Tracks all internal/external links

### 🤖 Bot Management (NEW in v0.2.0)

- **AI Training Bot Blocking** - Block GPTBot, Claude-Web, CCBot, etc.
- **AI Search Allowance** - Allow ChatGPT-User, ClaudeBot, PerplexityBot
- **Traditional Search Engines** - Full support for Google, Bing, etc.
- **Configurable Policies** - Fine-grained control via `RobotsConfig`
- **Bot Detection** - Accurately identify bot types from user agents

### 🔒 Privacy Controls (NEW in v0.2.0)

- **Hide Sensitive Pages** - `mark_hidden()` excludes pages from AI/bots
- **Component Hiding** - Hide specific components from extraction
- **Automatic Exclusion** - Hidden pages removed from sitemaps/robots.txt
- **404 for Hidden Routes** - Bots get 404 on hidden page docs

### 🌐 SEO Optimization (NEW in v0.2.0)

- **Smart Sitemap Generation** - Automatic priority inference
- **Priority System** - Homepage=1.0, Dashboards=0.9, Reports=0.8, Docs=0.7
- **Change Frequency** - Intelligent frequency detection (daily, weekly, monthly)
- **Static HTML for Bots** - Schema.org structured data, Open Graph tags
- **Noscript Fallbacks** - Content for non-JS crawlers

### 🧪 Fully Tested

- **88 comprehensive tests** - 100% pass rate
- **98-100% coverage** - All new modules fully tested
- **Integration tests** - Real-world scenario coverage
- **Fast execution** - 0.22s for entire test suite

---

## 📖 Complete Example

### Setup with Bot Control

```python
from dash import Dash, html, dcc
from dash_improve_my_llms import (
    add_llms_routes,
    mark_important,
    mark_hidden,
    register_page_metadata,
    RobotsConfig
)

# Create app
app = Dash(__name__, use_pages=True)

# Configure bot policies
robots_config = RobotsConfig(
    block_ai_training=True,      # Block GPTBot, CCBot, etc.
    allow_ai_search=True,         # Allow ClaudeBot, ChatGPT-User
    allow_traditional=True,       # Allow Googlebot, Bingbot
    crawl_delay=10,               # 10 second delay between requests
    disallowed_paths=["/admin", "/api/*"]  # Block specific paths
)

# Set base URL for SEO
app._base_url = "https://myapp.com"
app._robots_config = robots_config

# Add LLMS routes with all features
add_llms_routes(app)

# Hide admin pages from AI bots
mark_hidden("/admin")
mark_hidden("/settings")

# Add custom metadata for better SEO
register_page_metadata(
    path="/",
    name="Equipment Management System",
    description="Comprehensive equipment tracking and analytics platform"
)

if __name__ == '__main__':
    app.run(debug=True)
```

### Page with Important Sections

```python
# pages/equipment.py
from dash import html, Input, Output, callback
from dash_improve_my_llms import mark_important, register_page_metadata
import dash_mantine_components as dmc

register_page_metadata(
    path="/equipment",
    name="Equipment Catalog",
    description="Browse and filter the complete equipment catalog"
)

def layout():
    return html.Div([
        html.H1("Equipment Catalog"),

        # Mark filters as important for AI understanding
        mark_important(
            html.Div([
                html.H2("Filters"),
                dmc.TextInput(
                    id="equipment-search",
                    placeholder="Search equipment...",
                ),
                dmc.Select(
                    id="equipment-category",
                    data=[
                        {"value": "all", "label": "All Categories"},
                        {"value": "tools", "label": "Tools"},
                        {"value": "machinery", "label": "Machinery"},
                    ],
                    value="all"
                ),
            ], id="filters")
        ),

        html.Div(id="equipment-list"),
    ])

@callback(
    Output("equipment-list", "children"),
    Input("equipment-search", "value"),
    Input("equipment-category", "value"),
)
def update_list(search, category):
    # Your filtering logic here
    return html.Div("Equipment items...")
```

### Hidden Admin Page

```python
# pages/admin.py
from dash import html, register_page
from dash_improve_my_llms import mark_hidden

register_page(__name__, path="/admin", name="Admin Panel")

# This page won't appear in sitemaps or llms.txt
mark_hidden("/admin")

def layout():
    return html.Div([
        html.H1("Admin Panel"),
        html.P("Sensitive administrative controls")
    ])
```

---

## 🤖 Bot Management

### RobotsConfig Options

```python
from dash_improve_my_llms import RobotsConfig

# Default configuration (recommended)
config = RobotsConfig(
    block_ai_training=True,      # Block AI training bots
    allow_ai_search=True,         # Allow AI search bots
    allow_traditional=True,       # Allow traditional search engines
    crawl_delay=None,             # No delay
    custom_rules=[],              # No custom rules
    disallowed_paths=[]           # No additional blocks
)

# Strict configuration (block everything except Google)
strict_config = RobotsConfig(
    block_ai_training=True,
    allow_ai_search=False,
    allow_traditional=True,
    crawl_delay=30,
    disallowed_paths=["/admin", "/api", "/internal/*"]
)

# Open configuration (allow everything)
open_config = RobotsConfig(
    block_ai_training=False,
    allow_ai_search=True,
    allow_traditional=True
)

# Apply to app
app._robots_config = config
```

### Bot Detection

The plugin automatically detects and handles different bot types:

| Bot Type | Examples | Default Policy |
|----------|----------|----------------|
| **AI Training** | GPTBot, Claude-Web, CCBot, Google-Extended, anthropic-ai | ❌ Blocked |
| **AI Search** | ChatGPT-User, ClaudeBot, PerplexityBot | ✅ Allowed |
| **Traditional** | Googlebot, Bingbot, Yahoo, DuckDuckBot | ✅ Allowed |

```python
from dash_improve_my_llms.bot_detection import (
    is_ai_training_bot,
    is_ai_search_bot,
    is_traditional_bot,
    get_bot_type
)

user_agent = "Mozilla/5.0 (compatible; GPTBot/1.0)"

if is_ai_training_bot(user_agent):
    print("AI training bot detected - blocking")

bot_type = get_bot_type(user_agent)  # Returns: "training", "search", "traditional", or "unknown"
```

---

## 🗺️ SEO Optimization

### Sitemap Generation

The plugin automatically generates an SEO-optimized sitemap with intelligent priority inference:

```python
# Automatic priority based on page type:
# - Homepage (/)           → Priority 1.0
# - Dashboards             → Priority 0.9
# - Reports/Analytics      → Priority 0.8
# - Documentation/Help     → Priority 0.7
# - Other pages            → Priority 0.5

# Change frequency inference:
# - Dashboards/Live        → daily
# - Reports/Analytics      → weekly
# - Documentation          → monthly
# - Static pages           → yearly
```

Example sitemap entry:
```xml
<url>
  <loc>https://myapp.com/</loc>
  <lastmod>2025-11-04</lastmod>
  <changefreq>weekly</changefreq>
  <priority>1.0</priority>
</url>
```

### Bot Response Middleware (The Key Feature!)

**Problem**: AI crawlers cannot execute JavaScript, so they see empty `<div id="react-entry-point">` placeholders instead of your actual content.

**Solution**: The middleware automatically detects bots and serves them llms.txt content wrapped in readable HTML.

```python
# What bots receive:
✅ Search Bots (ClaudeBot, ChatGPT-User) → llms.txt content in HTML
✅ Traditional Bots (Googlebot, Bingbot)  → llms.txt content in HTML
❌ Training Bots (GPTBot, anthropic-ai)   → 403 Forbidden
✅ Regular Users (Chrome, Firefox)        → Full Dash React app
```

**Before Middleware** (❌ Bad):
```html
<!-- Bots saw this - empty until JavaScript executes -->
<div id="react-entry-point">
    <div class="_dash-loading">Loading...</div>
</div>
```

**After Middleware** (✅ Good):
```html
<!-- Bots now see this - readable content immediately -->
<div class="bot-notice">
    🤖 Bot-Optimized Content
    Also available: llms.txt | page.json | architecture.txt
</div>
<pre>
# Equipment Catalog

> Browse and filter the complete equipment catalog

## Key Content
- Equipment search and filtering
- Category selection
...
</pre>
```

**Features:**
- **Automatic Detection**: Identifies bot type from user agent
- **Smart Serving**: llms.txt content for bots, React app for users
- **SEO Optimized**: Includes Schema.org, Open Graph, meta tags
- **Privacy Enforced**: Training bots get 403 when blocked
- **No JavaScript Required**: Bots see content immediately

### Static HTML Components

The HTML served to bots includes:

- **Schema.org JSON-LD** - Structured data for search engines
- **Open Graph tags** - Social media previews
- **Meta tags** - Description, robots, viewport
- **Navigation links** - Accessible site structure
- **Bot notice banner** - Links to documentation formats
- **llms.txt content** - Full page context in `<pre>` tag

---

## 🔒 Privacy Controls

### Hiding Pages

```python
from dash_improve_my_llms import mark_hidden, is_hidden

# Hide sensitive pages
mark_hidden("/admin")
mark_hidden("/settings")
mark_hidden("/internal/metrics")

# Check if page is hidden
if is_hidden("/admin"):
    print("Admin page is hidden from bots")

# Hidden pages are automatically:
# - Excluded from sitemap.xml
# - Blocked in robots.txt
# - Return 404 for /page-path/llms.txt
# - Return 404 for /page-path/page.json
```

### Hiding Components

```python
from dash_improve_my_llms import mark_component_hidden, is_component_hidden
from dash import html

# Hide sensitive components from extraction
api_key_display = html.Div([
    html.P("API Key: sk-..."),
    html.P("Secret: abc123"),
], id="api-keys")

mark_component_hidden(api_key_display)

# Check if component is hidden
if is_component_hidden("api-keys"):
    print("Component excluded from llms.txt")
```

---

## 📊 Generated Documentation

### llms.txt (Comprehensive Context)

```markdown
# Equipment Catalog

> Browse and filter the complete equipment catalog

## Application Context
This page is part of a multi-page Dash application with 3 total pages.

## Page Purpose
- **Data Input**: Contains form elements
- **Interactive**: Responds to user interactions

## Interactive Elements
**User Inputs:**
- TextInput (ID: equipment-search)
- Select (ID: equipment-category)

## Data Flow & Callbacks
**Callback 1:**
- Updates: equipment-list.children
- Triggered by: equipment-search.value, equipment-category.value
```

### page.json (Technical Architecture)

```json
{
  "path": "/equipment",
  "components": {
    "ids": {
      "equipment-search": {
        "type": "TextInput",
        "module": "dash_mantine_components"
      }
    },
    "categories": {
      "inputs": ["equipment-search", "equipment-category"],
      "interactive": ["equipment-search", "equipment-category"]
    }
  },
  "callbacks": {
    "list": [
      {
        "output": "equipment-list.children",
        "inputs": ["equipment-search.value"]
      }
    ]
  }
}
```

### robots.txt (Bot Control)

```
# Robots.txt for Dash Application
# Block AI training bots, allow search bots

User-agent: GPTBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: ClaudeBot
Allow: /

User-agent: *
Allow: /
Crawl-delay: 10
Disallow: /admin
Disallow: /api/*

Sitemap: https://myapp.com/sitemap.xml
```

---

## 🧪 Testing

The package has **comprehensive test coverage**:

```bash
# Run all 88 tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=dash_improve_my_llms --cov-report=term-missing

# Test results:
# ✅ Bot Detection: 14/14 tests (100% coverage)
# ✅ HTML Generator: 20/20 tests (100% coverage)
# ✅ Robots Generator: 16/16 tests (100% coverage)
# ✅ Sitemap Generator: 33/33 tests (98% coverage)
# ✅ Integration: 15/15 tests (Complete workflows)
# ✅ Total: 88/88 tests passing in 0.22s
```

See [TEST_REPORT.md](TEST_REPORT.md) for detailed test documentation.

---

## 🎨 API Reference

### Core Functions

#### `add_llms_routes(app, config=None)`

Add all LLMS routes to your Dash app (llms.txt, page.json, architecture.txt, robots.txt, sitemap.xml).

```python
from dash_improve_my_llms import add_llms_routes, LLMSConfig

config = LLMSConfig(
    enabled=True,
    max_depth=20,
    include_css=True,
    include_callbacks=True
)

add_llms_routes(app, config)
```

#### `mark_important(component, component_id=None)`

Mark a component as important for LLM context. All children inherit importance.

```python
important_section = mark_important(
    html.Div([...], id="key-metrics")
)
```

#### `mark_hidden(page_path)`

Hide a page from AI bots, search engines, and sitemaps.

```python
mark_hidden("/admin")
mark_hidden("/settings")
```

#### `register_page_metadata(path, name=None, description=None, **kwargs)`

Register custom metadata for better SEO and documentation.

```python
register_page_metadata(
    path="/analytics",
    name="Analytics Dashboard",
    description="Real-time business analytics",
    category="reporting"
)
```

### Bot Management

#### `RobotsConfig`

Configuration for robots.txt generation.

**Parameters:**
- `block_ai_training` (bool): Block AI training bots (default: True)
- `allow_ai_search` (bool): Allow AI search bots (default: True)
- `allow_traditional` (bool): Allow traditional search engines (default: True)
- `crawl_delay` (int, optional): Delay between requests in seconds
- `custom_rules` (list, optional): Additional robots.txt rules
- `disallowed_paths` (list, optional): Paths to block

```python
from dash_improve_my_llms import RobotsConfig

config = RobotsConfig(
    block_ai_training=True,
    crawl_delay=15,
    disallowed_paths=["/admin", "/api/*"]
)
app._robots_config = config
```

### Bot Detection Functions

```python
from dash_improve_my_llms.bot_detection import (
    is_ai_training_bot,
    is_ai_search_bot,
    is_traditional_bot,
    is_any_bot,
    get_bot_type
)

user_agent = request.headers.get('User-Agent', '')

# Check bot type
is_ai_training_bot(user_agent)  # Returns bool
is_ai_search_bot(user_agent)     # Returns bool
is_traditional_bot(user_agent)   # Returns bool
is_any_bot(user_agent)           # Returns bool
get_bot_type(user_agent)         # Returns "training", "search", "traditional", or "unknown"
```

---

## 🔧 Advanced Usage

### Custom Sitemap Entries

```python
from dash_improve_my_llms.sitemap_generator import SitemapEntry

custom_entry = SitemapEntry(
    loc="https://myapp.com/special",
    changefreq="monthly",
    priority=0.6
)

# Add to sitemap via configuration
```

### Programmatic Access

```python
from dash_improve_my_llms import (
    generate_llms_txt,
    generate_page_json,
    generate_architecture_txt
)
from dash_improve_my_llms.robots_generator import generate_robots_txt
from dash_improve_my_llms.sitemap_generator import generate_sitemap_xml

# Generate documentation programmatically
llms_content = generate_llms_txt("/mypage", layout_func, "My Page", app)
page_arch = generate_page_json("/mypage", layout_func, app)
app_arch = generate_architecture_txt(app)

# Generate SEO files
robots_content = generate_robots_txt(robots_config, sitemap_url, base_url)
sitemap_content = generate_sitemap_xml(pages, base_url)
```

---

## 🚀 Migration Guide

### Upgrading from v0.1.0 to v0.2.0

v0.2.0 is **fully backward compatible**. All v0.1.0 code works without changes.

**New features (optional):**

```python
# 1. Configure bot policies
app._robots_config = RobotsConfig(block_ai_training=True)

# 2. Set base URL for SEO
app._base_url = "https://myapp.com"

# 3. Hide sensitive pages
from dash_improve_my_llms import mark_hidden
mark_hidden("/admin")

# That's it! Enjoy:
# - /robots.txt
# - /sitemap.xml
# - Better SEO
# - Bot control
```

---

## 📦 What's New in v0.2.0

### New Features

- ✅ **Bot Detection** - Identify AI training, AI search, and traditional bots
- ✅ **Robots.txt Generation** - Automatic with configurable policies
- ✅ **Sitemap.xml Generation** - Smart priorities and change frequencies
- ✅ **Static HTML for Bots** - Schema.org structured data
- ✅ **Privacy Controls** - mark_hidden() for sensitive pages
- ✅ **Component Hiding** - Exclude components from extraction

### Improvements

- ✅ **88 Comprehensive Tests** - 100% pass rate in 0.22s
- ✅ **98-100% Coverage** - All new modules fully tested
- ✅ **Better SEO** - Priority inference, change frequency detection
- ✅ **Bot Differentiation** - Fine-grained control per bot type

### Files Added

- `dash_improve_my_llms/bot_detection.py` - Bot user agent detection
- `dash_improve_my_llms/robots_generator.py` - robots.txt generation
- `dash_improve_my_llms/sitemap_generator.py` - sitemap.xml generation
- `dash_improve_my_llms/html_generator.py` - Static HTML for bots
- `tests/test_bot_detection.py` - 14 comprehensive tests
- `tests/test_robots_generator.py` - 16 comprehensive tests
- `tests/test_sitemap_generator.py` - 33 comprehensive tests
- `tests/test_html_generator.py` - 20 comprehensive tests
- `tests/test_integration.py` - 15 integration tests
- `TEST_REPORT.md` - Complete test documentation

---

## 📊 Compatibility

- **Python:** 3.8, 3.9, 3.10, 3.11, 3.12+
- **Dash:** 3.2.0+
- **Dash Mantine Components:** 2.3.0+ (optional)

Works with:
- ✅ Dash Pages (`dash.register_page`)
- ✅ Manual routing (`dcc.Location`)
- ✅ Multi-page apps
- ✅ Single-page apps
- ✅ All Dash component libraries

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all 88 tests pass
5. Submit a pull request

```bash
# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=dash_improve_my_llms --cov-report=html

# Format code
black dash_improve_my_llms/ tests/
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Credits

Built by [Pip Install Python LLC](https://pip-install-python.com) for the Dash community.

Inspired by:
- [llms.txt specification](https://llmstxt.org/)
- [dmc-docs](https://www.dash-mantine-components.com/llms)

Special thanks to the Dash community and Plotly team.

---

## 🔗 Links

- **Documentation:** [CLAUDE.md](CLAUDE.md)
- **Test Report:** [TEST_REPORT.md](TEST_REPORT.md)
- **PyPI:** [dash-improve-my-llms](https://pypi.org/project/dash-improve-my-llms/)
- **Dash:** [dash.plotly.com](https://dash.plotly.com/)
- **Plotly Pro:** [plotly.pro](https://plotly.pro)
- **Issues:** [GitHub Issues](https://github.com/yourusername/dash-improve-my-llms/issues)

---

<div align="center">

**Made with ❤️ for the Dash community**

[⭐ Star on GitHub](https://github.com/yourusername/dash-improve-my-llms) | [📖 Read the Docs](CLAUDE.md) | [🐛 Report Bug](https://github.com/yourusername/dash-improve-my-llms/issues)

</div>