# Dash LLMS Plugin

Automatic `llms.txt`, `page.json`, and `architecture.txt` generation for Dash applications, making your Dash apps LLM-friendly and comprehensively documented.

## Overview

This plugin automatically generates **three types of comprehensive metadata** for your Dash application:

1. **`llms.txt`** - Comprehensive, context-rich description optimized for LLM understanding
   - Application context and related pages
   - Page purpose (Data Input, Visualization, Navigation, Interactive)
   - Interactive elements with detailed input/output information
   - Key content (important sections and additional content)
   - Navigation links (internal and external)
   - Component breakdown and statistics
   - Data flow and callback information
   - Technical details and narrative summary

2. **`page.json`** - Detailed architecture with interactivity and data flow
   - Complete component tree with IDs and properties
   - Component categorization (inputs, outputs, containers, navigation, display)
   - Interactivity metadata (callbacks, interactive components)
   - Navigation data (links with counts)
   - Callback information (inputs, outputs, state, data flow graph)
   - Component statistics (total, interactive, static, unique types)
   - Metadata flags (contains forms, visualizations, navigation)

3. **`architecture.txt`** - ASCII art representation of entire application
   - Environment information (Python version, Dash version)
   - Dependencies (dash-mantine-components, plotly, pandas, etc.)
   - Application configuration (multi-page, callback exceptions)
   - Callback information (total count, breakdown by module)
   - Page details (components, interactive elements, callbacks per page)
   - Route documentation
   - Application-wide statistics
   - Top component types

## Features

- ✨ **Automatic generation** - Three comprehensive documentation files generated automatically
- 🎯 **Mark important sections** - Highlight key content for LLMs
- 🔄 **Cascading importance** - Child components inherit importance automatically
- 📄 **Triple format support** - llms.txt (comprehensive context), page.json (detailed architecture), architecture.txt (app overview)
- 🚀 **Easy integration** - One function call to enable all features
- 🔌 **Compatible** with Dash Pages and manual routing
- 📦 **No dependencies** beyond Dash itself
- 🧠 **Smart context** - llms.txt uses both page.json and architecture.txt data for comprehensive understanding
- 🔗 **Dependency tracking** - Automatically detects and documents Python packages and versions
- ⚡ **Callback intelligence** - Extracts and documents all callbacks with inputs, outputs, and state
- 🎨 **Component categorization** - Automatically categorizes components by purpose (inputs, outputs, navigation, etc.)
- 🗺️ **Navigation mapping** - Tracks all internal and external links
- 📊 **Rich metadata** - Interactivity flags, form detection, visualization detection, and more

## Installation

### From PyPI (Recommended)

```bash
pip install dash-improve-my-llms
```

### From Source

```bash
pip install -e .
```

### Build and Install

```bash
python -m build
pip install dist/dash_improve_my_llms-0.1.0-py3-none-any.whl
```

## Quick Start

### Basic Setup with Dash Pages

```python
from dash import Dash, html, register_page
from dash_improve_my_llms import add_llms_routes

# Create your Dash app
app = Dash(__name__, use_pages=True)

# Add LLMS routes - that's it!
add_llms_routes(app)

# Define your pages as normal
register_page("home", path="/", layout=html.Div([
    html.H1("Welcome to My App")
]))

if __name__ == '__main__':
    app.run(debug=True)
```

Now visit:
- `http://localhost:8050/llms.txt` - Comprehensive LLM-friendly page context
- `http://localhost:8050/page.json` - Detailed technical architecture with callbacks
- `http://localhost:8050/architecture.txt` - ASCII art overview of entire application

### Marking Important Sections

Use `mark_important()` to highlight key content for LLMs. All children are automatically considered important:

```python
from dash import html
from dash_improve_my_llms import mark_important

layout = html.Div([
    html.H1("My Dashboard"),

    # Mark this entire section as important
    mark_important(
        html.Div([
            html.H2("Critical Metrics"),
            html.P("Revenue: $1.2M"),
            html.P("Users: 50,000"),
        ], id="key-metrics")
    ),

    # This section won't be marked as important
    html.Div([
        html.H2("Additional Info"),
        html.P("Some supplementary information"),
    ])
])
```

### Adding Page Metadata

Provide custom descriptions for better llms.txt generation:

```python
from dash_improve_my_llms import register_page_metadata

register_page_metadata(
    path="/dashboard",
    name="Analytics Dashboard",
    description="Real-time analytics dashboard showing key business metrics and performance indicators"
)
```

## Complete Example

See `app.py` for a full working example with:
- Multiple pages (Home, Equipment, Analytics)
- Important section marking
- Custom metadata
- Integration with dash-mantine-components
- Interactive callbacks

Run it with:
```bash
python app.py
```

## API Reference

### `add_llms_routes(app, config=None)`

Add LLMS routes to your Dash app.

**Parameters:**
- `app` (Dash): Your Dash application instance
- `config` (LLMSConfig, optional): Configuration object

**Example:**
```python
from dash_improve_my_llms import add_llms_routes, LLMSConfig

config = LLMSConfig(
    enabled=True,
    include_css=True,
    include_callbacks=True,
    max_depth=20
)

add_llms_routes(app, config)
```

### `mark_important(component, component_id=None)`

Mark a component as important for LLM context. All children inherit importance.

**Parameters:**
- `component`: Dash component to mark
- `component_id` (str, optional): Optional ID to track the component

**Returns:**
- The same component (for chaining)

**Example:**
```python
important_section = mark_important(
    html.Div([
        html.H2("Key Information"),
        html.P("Critical details here")
    ], id="main-content")
)
```

### `register_page_metadata(path, name=None, description=None, **kwargs)`

Register custom metadata for a page.

**Parameters:**
- `path` (str): Page URL path
- `name` (str, optional): Display name
- `description` (str, optional): Page description
- `**kwargs`: Additional custom metadata

**Example:**
```python
register_page_metadata(
    path="/analytics",
    name="Analytics Dashboard",
    description="Interactive dashboard for business analytics",
    category="reporting",
    access_level="admin"
)
```

### `LLMSConfig`

Configuration class for the LLMS plugin.

**Parameters:**
- `enabled` (bool): Enable/disable plugin (default: True)
- `auto_detect_pages` (bool): Auto-detect pages (default: True)
- `include_css` (bool): Include CSS in page.json (default: True)
- `include_callbacks` (bool): Include callbacks in page.json (default: True)
- `max_depth` (int): Maximum component tree depth (default: 20)
- `exclude_patterns` (list, optional): URL patterns to exclude

## How It Works

### llms.txt Generation

The enhanced llms.txt generation creates comprehensive, context-rich documentation by:

1. **Generating page.json data** first to extract complete architecture
2. **Analyzing application context** from Dash page registry
3. **Inferring page purpose** from component types (forms, visualizations, navigation)
4. **Extracting interactivity** information (callbacks, inputs, outputs)
5. **Categorizing components** by purpose and tracking all IDs
6. **Mapping navigation** (internal and external links)
7. **Creating narrative summary** that tells the "truth" of the page

Example comprehensive output:
```markdown
# Equipment Catalog

> Browse and filter the complete equipment catalog with search and category filters

---

## Application Context

This page is part of a multi-page Dash application with 3 total pages.

**Related Pages:**
- Home (`/`)
- Analytics Dashboard (`/analytics`)

## Page Purpose

- **Data Input**: Contains form elements for user data entry
- **Navigation**: Provides links to other sections of the application
- **Interactive**: Responds to user interactions with dynamic updates

## Interactive Elements

This page contains **2 interactive components** with **4 callback(s)** that respond to user actions.

**User Inputs:**
- TextInput (ID: `equipment-search`) - Search equipment...
- Select (ID: `equipment-category`) - Select category

## Key Content

**Primary Information (marked as important):**
- Filters
- Search equipment...
- Select category

**Additional Content:**
- Equipment Catalog
- Equipment List
- Statistics
...

## Navigation

**Internal Links:**
- ← Back to Home → `/`
- View Analytics → → `/analytics`

## Component Breakdown

**Total Components**: 23
- Interactive: 2
- Static/Display: 21

**Component Types:**
- Div: 6
- H2: 2
- Link: 2
...

## Data Flow & Callbacks

This page has **4 callback(s)** that handle user interactions:

**Callback 1:**
- Updates: `equipment-list.children`
- Triggered by: `equipment-search.value`, `equipment-category.value`

## Technical Details

- **Path**: `/equipment`
- **Max Component Depth**: 3
- **Has Important Sections**: Yes
- **Full Architecture**: Available at `/equipment/page.json`
- **Global App Architecture**: Available at `/architecture.txt`

---

## Summary

The **Equipment Catalog** page browse and filter the complete equipment catalog...
It contains 2 interactive component(s) that allow users to input data and trigger 4 callback(s).
Users can navigate to 2 other page(s) from here.

---

*Generated with https://pip-install-python.com | dash-improve-my-llms hook*
Pip Install Python LLC | https://plotly.pro
```

### page.json Generation

The enhanced page.json provides comprehensive technical documentation:

1. **Traverses component tree** recursively with full property extraction
2. **Extracts all component IDs** with their types, modules, and properties
3. **Categorizes components** by purpose (inputs, outputs, containers, navigation, display, interactive)
4. **Extracts navigation links** with text and destinations
5. **Analyzes callbacks** from the app instance (inputs, outputs, state)
6. **Generates interactivity metadata** (callback count, interactive component count)
7. **Creates callback data flow graph** showing trigger relationships

Example comprehensive output:
```json
{
  "path": "/equipment",
  "name": "Equipment Catalog",
  "description": "Browse and filter equipment...",
  "architecture": {
    "type": "Div",
    "children_count": 4,
    "children": [...]
  },
  "components": {
    "ids": {
      "equipment-search": {
        "type": "TextInput",
        "module": "dash_mantine_components",
        "important": true,
        "props": {"placeholder": "Search equipment..."}
      }
    },
    "categories": {
      "inputs": ["equipment-search", "equipment-category"],
      "outputs": [],
      "containers": ["filters", "..."],
      "navigation": ["Link-...", "..."],
      "interactive": ["equipment-search", "equipment-category"]
    },
    "types": {
      "Div": 6,
      "TextInput": 1,
      "Select": 1
    },
    "counts": {
      "total": 23,
      "interactive": 2,
      "static": 21,
      "unique_types": 8
    }
  },
  "interactivity": {
    "has_callbacks": true,
    "callback_count": 4,
    "interactive_components": 2,
    "inputs": ["equipment-search", "equipment-category"],
    "outputs": []
  },
  "navigation": {
    "links": [
      {"href": "/", "text": "← Back to Home", "type": "Link"},
      {"href": "/analytics", "text": "View Analytics →", "type": "Link"}
    ],
    "outbound_count": 2,
    "external_count": 0
  },
  "metadata": {
    "has_important_sections": true,
    "max_depth": 3,
    "contains_forms": true,
    "contains_visualizations": false,
    "contains_navigation": true
  },
  "callbacks": {
    "list": [
      {
        "output": "equipment-list.children",
        "inputs": ["equipment-search.value", "equipment-category.value"],
        "state": []
      }
    ],
    "graph": {
      "equipment-list.children": {
        "triggers": ["equipment-search.value", "equipment-category.value"]
      }
    }
  }
}
```

### architecture.txt Generation

The architecture.txt provides a bird's-eye view of your entire application:

1. **Detects environment** (Python version, Dash version)
2. **Scans dependencies** (automatically detects dash-mantine-components, plotly, pandas, etc.)
3. **Analyzes application config** (multi-page, callback exceptions)
4. **Extracts callback information** grouped by module
5. **Summarizes all pages** with component counts, interactive elements, callbacks
6. **Documents routes** (pages and documentation routes)
7. **Generates statistics** (total pages, callbacks, components, interactive components)
8. **Lists top components** across the entire application

Example output:
```
================================================================================
                         DASH APPLICATION ARCHITECTURE
================================================================================

┌─ ENVIRONMENT
│
├─── Python Version: 3.11.8
├─── Dash Version: 3.3.0
├─── Key Dependencies:
│    ├─── dash-mantine-components==2.3.0
│    ├─── plotly==6.0.1
│    └─── pandas==2.2.3
│
├─ APPLICATION
│
├─── Name: Dash
├─── Server: app
├─── Multi-Page: Yes
├─── Suppress Callback Exceptions: True
│
├─ CALLBACKS
│
├─── Total Callbacks: 4
├─── By Module:
│    ├─── pages.equipment: 1 callback(s)
│    ├─── pages.analytics: 1 callback(s)
│    └─── dash.dash: 1 callback(s)
│
├─ PAGES
│  ├── Home
│      ├─ Path: /
│      ├─ Module: pages.home
│      ├─ Description: Welcome page for the Equipment Management System...
│      ├─ Components: 35
│      ├─ Interactive: 0
│      ├─ Callbacks: 0
│      └─ Types: Div, H1, text, P, H2
│
│  ├── Equipment Catalog
│      ├─ Path: /equipment
│      ├─ Module: pages.equipment
│      ├─ Description: Browse and filter the complete equipment catalog...
│      ├─ Components: 23
│      ├─ Interactive: 2
│      ├─ Callbacks: 1
│      └─ Types: Div, H1, text, H2, TextInput
│
├─ ROUTES
│  ├── Documentation Routes:
│  │   ├── /llms.txt (current page context)
│  │   ├── /page.json (current page architecture)
│  │   ├── /architecture.txt (global architecture)
│  │   └── /<page_path>/llms.txt (specific page)
│  ├── Page Routes:
│  │   ├─── / (Home)
│  │   ├─── /equipment (Equipment Catalog)
│  │   └─── /analytics (Analytics Dashboard)
│
├─ STATISTICS
│  ├── Total Pages: 3
│  ├── Total Callbacks: 4
│  ├── Total Components: 99
│  ├── Interactive Components: 3
│  └── Unique Component Types: 11
│
├─ TOP COMPONENTS
│  ├── Div: 45
│  ├── text: 38
│  ├── P: 8
│  ├── Li: 7
│  └── H2: 5
│
└─ END

================================================================================
*Generated with https://pip-install-python.com | dash-improve-my-llms hook*
Pip Install Python LLC | https://plotly.pro
================================================================================
```

## Use Cases

### For AI Assistants

LLMs can use these files to:
- Understand page structure and content
- Answer questions about your app
- Help debug layout issues
- Generate documentation
- Suggest improvements

### For Documentation

- Auto-generate API docs
- Create user guides
- Build sitemaps
- Generate component inventories

### For Development

- Understand page complexity
- Track component usage
- Identify optimization opportunities
- Document application architecture

## Compatibility

- **Dash**: 3.2.0+
- **Dash Mantine Components**: 2.3.0+ (optional)
- **Python**: 3.8+

Works with:
- ✅ Dash Pages (`dash.register_page`)
- ✅ Manual routing (`dcc.Location`)
- ✅ Multi-page apps
- ✅ Single-page apps
- ✅ All Dash component libraries

## Advanced Usage

### Custom Content Extraction

You can customize how content is extracted by extending the plugin:

```python
from dash_improve_my_llms import extract_text_content

# Custom extraction for your components
def my_custom_extractor(component):
    texts = extract_text_content(component)
    # Add custom logic here
    return texts
```

### Integration with Existing Routes

The plugin uses Dash hooks to add routes non-invasively:

```python
# Your existing routes work unchanged
@app.server.route('/api/data')
def get_data():
    return jsonify({"status": "ok"})

# LLMS routes are added automatically
add_llms_routes(app)
```

### Programmatic Access

Access the generated content programmatically:

```python
from dash_improve_my_llms import generate_llms_txt, generate_page_json

# Generate for a specific layout
llms_content = generate_llms_txt("/mypage", my_layout_function)
page_arch = generate_page_json("/mypage", my_layout_function)

print(llms_content)
print(json.dumps(page_arch, indent=2))
```

## Troubleshooting

### Routes not working?

Make sure you call `add_llms_routes()` after creating your app:

```python
app = Dash(__name__, use_pages=True)
add_llms_routes(app)  # Add this!
```

### Content not showing?

Check that your page is registered correctly:

```python
import dash
print(dash.page_registry)  # Should show your pages
```

### Important sections not marked?

Verify the component has an `id`:

```python
mark_important(
    html.Div([...], id="my-section")  # ID is important!
)
```

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Credits

Built for the Dash community. Inspired by the [llms.txt specification](https://llmstxt.org/) and the [dmc-docs](https://www.dash-mantine-components.com/llms).

## Related Projects

- [llms-txt](https://github.com/simonw/llms-txt) - Original llms.txt Python library
- [Dash](https://dash.plotly.com/) - Python framework for building web apps
- [Dash Mantine Components](https://dash-mantine-components.com/) - Modern component library

## Support

- 📖 [Documentation](https://github.com/yourusername/dash-llms-plugin)
- 🐛 [Issue Tracker](https://github.com/yourusername/dash-llms-plugin/issues)
- 💬 [Dash Community Forum](https://community.plotly.com/c/dash)

---

Made with ❤️ for the Dash community
