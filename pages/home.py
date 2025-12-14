import dash_mantine_components as dmc
from dash import dcc, html, register_page
from dash_improve_my_llms import mark_important, register_page_metadata

register_page(
    __name__,
    path="/",
    name="Home",
)

# Register metadata for better llms.txt generation
register_page_metadata(
    path="/",
    name="Home",
    description="Welcome page for the Equipment Management System with navigation and overview",
)

# ASCII Diagram showing how dash-improve-my-llms hook works
ARCHITECTURE_DIAGRAM = """
╔════════════════════════════════════════════════════════════════════════════════╗
║                    DASH-IMPROVE-MY-LLMS HOOK ARCHITECTURE                      ║
╚════════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────┐
│  STEP 1: INTEGRATE WITH YOUR DASH APP                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

    Your Dash Application                     Hook Integration
    ─────────────────────                     ────────────────

    from dash import Dash                     from dash_improve_my_llms import (
    from dash import dcc, html    ──────►         add_llms_routes,
                                                   RobotsConfig,
    app = Dash(__name__)          ──────►         mark_hidden
                                              )

    # Your pages here                        # Add the hook (1 line!)
    @app.callback(...)            ──────►    add_llms_routes(app)
    def my_callback(...):
        ...                                   # Optional: Configure bot management
                                              app._robots_config = RobotsConfig(
    app.run(debug=True)                           block_ai_training=True,
                                                  allow_ai_search=True
                                              )

┌─────────────────────────────────────────────────────────────────────────────────┐
│  STEP 2: AUTOMATIC ROUTE GENERATION                                            │
└─────────────────────────────────────────────────────────────────────────────────┘

    Hook automatically creates these routes for EVERY page in your app:

    Your Page: /                    Auto-Generated Routes:
    ───────────                     ──────────────────────
         │
         ├──────────────────────────► /llms.txt            (LLM-friendly markdown)
         │
         ├──────────────────────────► /llms.toon           (Token-optimized TOON - NEW v1.0.0!)
         │
         ├──────────────────────────► /page.json           (Technical architecture)
         │
         ├──────────────────────────► /architecture.txt    (App overview - global)
         │
         └──────────────────────────► /architecture.toon   (Token-optimized - NEW v1.0.0!)

    Your Page: /equipment           Auto-Generated Routes:
    ─────────────────               ──────────────────────
         │
         ├──────────────────────────► /equipment/llms.txt
         │
         ├──────────────────────────► /equipment/llms.toon (NEW v1.0.0!)
         │
         └──────────────────────────► /equipment/page.json

    Your Page: /analytics           Auto-Generated Routes:
    ─────────────────               ──────────────────────
         │
         ├──────────────────────────► /analytics/llms.txt
         │
         ├──────────────────────────► /analytics/llms.toon (NEW v1.0.0!)
         │
         └──────────────────────────► /analytics/page.json

┌─────────────────────────────────────────────────────────────────────────────────┐
│  STEP 3: SEO & BOT MANAGEMENT (v0.2.0)                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

    Global Routes (Auto-Generated):
    ───────────────────────────────

    /robots.txt       ───►  🤖 Bot Access Control
                            ├─ Block AI Training Bots (GPTBot, CCBot)
                            ├─ Allow AI Search Bots (ChatGPT-User, ClaudeBot)
                            ├─ Allow Traditional Bots (Googlebot, Bingbot)
                            └─ Custom crawl delays & disallowed paths

    /sitemap.xml      ───►  🗺️  SEO Sitemap
                            ├─ Lists all public pages
                            ├─ Smart priority inference (homepage=1.0, dashboards=0.9)
                            ├─ Change frequency detection
                            └─ Excludes hidden pages (mark_hidden)

┌─────────────────────────────────────────────────────────────────────────────────┐
│  STEP 4: CONTENT EXTRACTION & GENERATION                                       │
└─────────────────────────────────────────────────────────────────────────────────┘

    Your Dash Layout                         What Gets Extracted:
    ───────────────                          ───────────────────

    html.Div([                               📊 Component Tree
        html.H1("Dashboard"),      ────►         ├─ All component types
        dcc.Dropdown(id='filter'),               ├─ Component IDs & properties
        dcc.Graph(id='chart'),                   └─ Nesting structure

        mark_important(            ────►     ⭐ Important Sections
            html.Div([                           └─ Highlighted for LLMs
                html.H2("Key Metrics")
            ])                                🔗 Navigation Links
        ),                         ────►         ├─ Internal links (dcc.Link)
                                                 └─ External links (html.A)
        dcc.Link("Analytics",
            href="/analytics")                🎯 Callbacks & Interactivity
    ])                             ────►         ├─ Input components
                                                 ├─ Output components
    @callback(                                   ├─ State tracking
        Output('chart', 'figure'),               └─ Data flow graph
        Input('filter', 'value')
    )                              ────►     📝 Page Metadata
    def update_chart(filter_val):                ├─ Page name & description
        ...                                      ├─ Component counts
                                                 └─ Purpose inference

┌─────────────────────────────────────────────────────────────────────────────────┐
│  STEP 5: GENERATED OUTPUT FILES                                                │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  /llms.txt  (Markdown - LLM-Optimized Context)                          │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  # Equipment Catalog                                                    │
    │                                                                          │
    │  > Browse and filter equipment with search and category filters         │
    │                                                                          │
    │  ## Application Context                                                 │
    │  This page is part of a multi-page Dash application with 3 pages.      │
    │                                                                          │
    │  ## Interactive Elements                                                │
    │  - TextInput (ID: equipment-search) - Search equipment...               │
    │  - Select (ID: equipment-category) - Select category                    │
    │                                                                          │
    │  ## Data Flow & Callbacks                                               │
    │  Callback 1: Updates equipment-list.children                            │
    │    Triggered by: equipment-search.value, equipment-category.value       │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  /page.json  (JSON - Technical Architecture)                            │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  {                                                                       │
    │    "path": "/equipment",                                                │
    │    "name": "Equipment Catalog",                                         │
    │    "components": {                                                       │
    │      "ids": {                                                            │
    │        "equipment-search": {"type": "TextInput", ...},                  │
    │        "equipment-category": {"type": "Select", ...}                    │
    │      },                                                                  │
    │      "categories": {                                                     │
    │        "inputs": ["equipment-search", "equipment-category"],            │
    │        "interactive": [...]                                             │
    │      }                                                                   │
    │    },                                                                    │
    │    "interactivity": {                                                    │
    │      "has_callbacks": true,                                             │
    │      "callback_count": 1                                                │
    │    }                                                                     │
    │  }                                                                       │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  /architecture.txt  (ASCII Art - App Overview)                          │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  ┌─ ENVIRONMENT                                                         │
    │  ├─── Python Version: 3.12.3                                            │
    │  ├─── Dash Version: 3.3.0                                               │
    │  ├─── Key Dependencies: dash-mantine-components, plotly, pandas         │
    │  │                                                                       │
    │  ├─ CALLBACKS                                                           │
    │  ├─── Total Callbacks: 4                                                │
    │  ├─── By Module:                                                        │
    │  │    ├─── pages.equipment: 1 callback(s)                               │
    │  │    └─── pages.analytics: 1 callback(s)                               │
    │  │                                                                       │
    │  ├─ PAGES                                                               │
    │  │  ├── Home (Path: /)                                                  │
    │  │  │   ├─ Components: 35                                               │
    │  │  │   └─ Interactive: 0                                               │
    │  │  │                                                                    │
    │  │  ├── Equipment Catalog (Path: /equipment)                            │
    │  │  │   ├─ Components: 23                                               │
    │  │  │   ├─ Interactive: 2                                               │
    │  │  │   └─ Callbacks: 1                                                 │
    │  │  │                                                                    │
    │  │  └── Analytics Dashboard (Path: /analytics)                          │
    │  │      ├─ Components: 41                                               │
    │  │      └─ Interactive: 1                                               │
    │  └─ END                                                                  │
    └─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│  PRIVACY & BOT CONTROL (v0.2.0)                                                │
└─────────────────────────────────────────────────────────────────────────────────┘

    Hide Sensitive Pages:                    Result:
    ────────────────────                     ───────

    mark_hidden("/admin")          ────►     ❌ Excluded from sitemap.xml
                                             ❌ Blocked in robots.txt
                                             ❌ /admin/llms.txt returns 404
                                             ❌ /admin/page.json returns 404
                                             ✅ Still accessible to logged-in users

    Bot Management:                          Result:
    ──────────────                           ───────

    RobotsConfig(                  ────►     🚫 GPTBot, CCBot blocked (training)
      block_ai_training=True,                ✅ ChatGPT-User allowed (search)
      allow_ai_search=True,                  ✅ Googlebot allowed (traditional)
      crawl_delay=10                         ⏱️  10s delay between requests
    )

╔════════════════════════════════════════════════════════════════════════════════╗
║  BENEFITS FOR LLMS & DEVELOPERS                                                ║
╚════════════════════════════════════════════════════════════════════════════════╝

    LLM Benefits:                            Developer Benefits:
    ─────────────                            ──────────────────

    ✅ Complete app context                  ✅ Auto-generated docs (always in sync)
    ✅ Page purpose understanding            ✅ Zero maintenance overhead
    ✅ Interactive elements mapped           ✅ One-line integration
    ✅ Data flow comprehension               ✅ Comprehensive testing (88 tests)
    ✅ Navigation structure                  ✅ Bot management & SEO built-in
    ✅ Callback relationships                ✅ Privacy controls for sensitive pages

═══════════════════════════════════════════════════════════════════════════════════

Made with ❤️  by Pip Install Python LLC | https://pip-install-python.com
"""


# Define layout - must be named 'layout'
def layout():
    return html.Div(
        [
            html.H1("Welcome to dash-improve-my-llms v1.2.0"),
            html.P(
                "Make your Dash applications AI-friendly with automatic documentation generation, "
                "TOON format support (50-60% fewer tokens), bot management, and SEO optimization.",
                style={"fontSize": "18px", "marginBottom": "30px"}
            ),

            # ASCII Architecture Diagram
            html.Div(
                [
                    html.H2("🏗️ Hook Architecture & Integration Flow"),
                    html.Pre(
                        ARCHITECTURE_DIAGRAM,
                        style={
                            "background": "#1e1e1e",
                            "color": "#d4d4d4",
                            "padding": "20px",
                            "borderRadius": "8px",
                            "overflow": "auto",
                            "fontSize": "12px",
                            "fontFamily": "monospace",
                            "lineHeight": "1.5",
                            "border": "2px solid #667eea",
                            "boxShadow": "0 4px 6px rgba(0,0,0,0.1)"
                        }
                    ),
                ],
                style={"marginBottom": "40px"}
            ),

            # Quick Start Section
            html.Div(
                [
                    html.H2("🚀 Quick Start"),
                    html.P("Get started with just 3 lines of code:"),
                    html.Pre(
                        """from dash import Dash
from dash_improve_my_llms import add_llms_routes

app = Dash(__name__, use_pages=True)
add_llms_routes(app)  # ✨ That's it!

app.run(debug=True)""",
                        style={
                            "background": "#f8f9fa",
                            "padding": "15px",
                            "borderRadius": "5px",
                            "border": "1px solid #e0e0e0",
                            "fontFamily": "monospace",
                            "fontSize": "14px"
                        }
                    ),
                ],
                style={"marginBottom": "30px"}
            ),

            # Quick Links Section
            mark_important(
                html.Div(
                    [
                        html.H2("🔗 Try the Generated Documentation"),
                        html.P("See the hook in action - explore the auto-generated routes:"),
                        html.Div(
                            [
                                # Documentation Routes
                                html.Div(
                                    [
                                        html.H3("📄 Documentation Routes", style={"fontSize": "18px"}),
                                        html.Ul(
                                            [
                                                html.Li([
                                                    html.A("/llms.txt", href="/llms.txt", target="_blank"),
                                                    " - LLM-friendly markdown context"
                                                ]),
                                                html.Li([
                                                    html.A("/page.json", href="/page.json", target="_blank"),
                                                    " - Technical architecture JSON"
                                                ]),
                                                html.Li([
                                                    html.A("/architecture.txt", href="/architecture.txt", target="_blank"),
                                                    " - ASCII art app overview"
                                                ]),
                                            ]
                                        ),
                                    ],
                                    style={"flex": "1", "marginRight": "15px"}
                                ),

                                # TOON Format Routes (v1.2.0!)
                                html.Div(
                                    [
                                        html.H3("🎯 TOON Format (v1.2.0)", style={"fontSize": "18px", "color": "#e599f7"}),
                                        html.Ul(
                                            [
                                                html.Li([
                                                    html.A("/llms.toon", href="/llms.toon", target="_blank"),
                                                    " - Token-optimized (40-60% fewer tokens)"
                                                ]),
                                                html.Li([
                                                    html.A("/v120-features/llms.toon", href="/v120-features/llms.toon", target="_blank"),
                                                    " - Documentation-optimized TOON (v1.2.0)"
                                                ]),
                                                html.Li([
                                                    html.A("/architecture.toon", href="/architecture.toon", target="_blank"),
                                                    " - Token-optimized architecture"
                                                ]),
                                            ]
                                        ),
                                    ],
                                    style={"flex": "1", "marginRight": "15px"}
                                ),

                                # SEO Routes
                                html.Div(
                                    [
                                        html.H3("🤖 SEO Routes", style={"fontSize": "18px", "color": "#51cf66"}),
                                        html.Ul(
                                            [
                                                html.Li([
                                                    html.A("/robots.txt", href="/robots.txt", target="_blank"),
                                                    " - Bot access control"
                                                ]),
                                                html.Li([
                                                    html.A("/sitemap.xml", href="/sitemap.xml", target="_blank"),
                                                    " - SEO sitemap"
                                                ]),
                                            ]
                                        ),
                                    ],
                                    style={"flex": "1"}
                                ),
                            ],
                            style={"display": "flex"}
                        ),

                        # Page-Specific Routes
                        html.Div(
                            [
                                html.H3("📑 Page-Specific Routes", style={"fontSize": "18px", "marginTop": "20px"}),
                                html.P("Every page gets its own documentation:"),
                                html.Ul(
                                    [
                                        html.Li([
                                            html.A("/equipment/llms.txt", href="/equipment/llms.txt", target="_blank"),
                                            " - Equipment page context"
                                        ]),
                                        html.Li([
                                            html.A("/equipment/page.json", href="/equipment/page.json", target="_blank"),
                                            " - Equipment page architecture"
                                        ]),
                                        html.Li([
                                            html.A("/analytics/llms.txt", href="/analytics/llms.txt", target="_blank"),
                                            " - Analytics page context"
                                        ]),
                                        html.Li([
                                            html.A("/analytics/page.json", href="/analytics/page.json", target="_blank"),
                                            " - Analytics page architecture"
                                        ]),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    id="quick-links",
                    style={
                        "background": "linear-gradient(135deg, #667eea15 0%, #764ba215 100%)",
                        "padding": "25px",
                        "borderRadius": "10px",
                        "border": "2px solid #667eea"
                    }
                )
            ),

            # Navigation to Other Pages
            html.Div(
                [
                    html.H2("📱 Explore Example Pages"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("🔧 Equipment", style={"fontSize": "18px"}),
                                    html.P("Browse and filter equipment catalog with interactive filters"),
                                    dcc.Link("View Equipment →", href="/equipment", style={"fontWeight": "bold"})
                                ],
                                style={
                                    "flex": "1",
                                    "background": "white",
                                    "padding": "20px",
                                    "borderRadius": "8px",
                                    "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                                    "marginRight": "15px"
                                }
                            ),
                            html.Div(
                                [
                                    html.H3("📊 Analytics", style={"fontSize": "18px"}),
                                    html.P("Real-time analytics dashboard with Plotly visualizations"),
                                    dcc.Link("View Analytics →", href="/analytics", style={"fontWeight": "bold"})
                                ],
                                style={
                                    "flex": "1",
                                    "background": "white",
                                    "padding": "20px",
                                    "borderRadius": "8px",
                                    "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                                    "marginRight": "15px"
                                }
                            ),
                            html.Div(
                                [
                                    html.H3("🔒 Admin", style={"fontSize": "18px", "color": "#ff6b6b"}),
                                    html.P("Hidden admin dashboard with visitor analytics (mark_hidden demo)"),
                                    dcc.Link("View Admin →", href="/admin", style={"fontWeight": "bold", "color": "#ff6b6b"})
                                ],
                                style={
                                    "flex": "1",
                                    "background": "white",
                                    "padding": "20px",
                                    "borderRadius": "8px",
                                    "boxShadow": "0 2px 4px rgba(0,0,0,0.1)"
                                }
                            ),
                        ],
                        style={"display": "flex"}
                    ),
                    # v1.2.0 Features Page
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("📚 v1.2.0 Features", style={"fontSize": "18px", "color": "#667eea"}),
                                    html.P("Documentation-aware TOON generation with PageType detection, prose extraction, and optimized output"),
                                    dcc.Link("Explore v1.2.0 →", href="/v120-features", style={"fontWeight": "bold", "color": "#667eea"})
                                ],
                                style={
                                    "background": "linear-gradient(135deg, #667eea15 0%, #764ba215 100%)",
                                    "padding": "20px",
                                    "borderRadius": "8px",
                                    "border": "2px solid #667eea",
                                    "marginTop": "15px"
                                }
                            ),
                        ]
                    ),
                ],
                style={"marginTop": "40px"}
            ),

            # Features Section
            html.Div(
                [
                    html.H2("✨ v1.2.0 Features"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("📚 Doc-Aware TOON (v1.2.0)", style={"fontSize": "16px", "color": "#e599f7"}),
                                    html.Ul(
                                        [
                                            html.Li("PageType detection (DOC/INTERACTIVE/HYBRID)"),
                                            html.Li("Full prose extraction from dcc.Markdown"),
                                            html.Li("Code block & table preservation"),
                                            html.Li("Adaptive TOON generation"),
                                        ],
                                        style={"fontSize": "14px"}
                                    ),
                                ],
                                style={"flex": "1", "marginRight": "15px"}
                            ),
                            html.Div(
                                [
                                    html.H3("🤖 Bot Management", style={"fontSize": "16px", "color": "#667eea"}),
                                    html.Ul(
                                        [
                                            html.Li("Block AI training bots"),
                                            html.Li("Allow AI search bots"),
                                            html.Li("Control search engines"),
                                            html.Li("Custom crawl delays"),
                                        ],
                                        style={"fontSize": "14px"}
                                    ),
                                ],
                                style={"flex": "1", "marginRight": "15px"}
                            ),
                            html.Div(
                                [
                                    html.H3("🗺️ SEO Optimization", style={"fontSize": "16px", "color": "#51cf66"}),
                                    html.Ul(
                                        [
                                            html.Li("Automatic sitemap.xml"),
                                            html.Li("Smart priority inference"),
                                            html.Li("robots.txt policies"),
                                            html.Li("Hidden page exclusion"),
                                        ],
                                        style={"fontSize": "14px"}
                                    ),
                                ],
                                style={"flex": "1", "marginRight": "15px"}
                            ),
                            html.Div(
                                [
                                    html.H3("🔐 Privacy Controls", style={"fontSize": "16px", "color": "#ff6b6b"}),
                                    html.Ul(
                                        [
                                            html.Li("mark_hidden() pages"),
                                            html.Li("Component hiding"),
                                            html.Li("404 for bot requests"),
                                            html.Li("Sitemap exclusion"),
                                        ],
                                        style={"fontSize": "14px"}
                                    ),
                                ],
                                style={"flex": "1"}
                            ),
                        ],
                        style={"display": "flex"}
                    ),
                ],
                style={
                    "marginTop": "40px",
                    "background": "#f8f9fa",
                    "padding": "20px",
                    "borderRadius": "8px"
                }
            ),

            # Test Report
            html.Div(
                [
                    html.H2("🧪 Quality Assurance"),
                    html.P([
                        "✅ ",
                        html.Strong("88/88 Tests Passing (100%)"),
                        " - Comprehensive test coverage with 98-100% for new modules"
                    ]),
                    html.P([
                        "📊 View the complete ",
                        html.A(
                            "Test Report",
                            href="https://github.com/yourusername/dash-improve-my-llms/blob/main/TEST_REPORT.md",
                            target="_blank",
                            style={"color": "#51cf66"}
                        ),
                        " for detailed test results and coverage analysis."
                    ]),
                ],
                style={
                    "marginTop": "30px",
                    "background": "#e3f2fd",
                    "padding": "20px",
                    "borderRadius": "8px",
                    "border": "1px solid #2196f3"
                }
            ),
        ],
        style={"maxWidth": "1200px"}
    )
