"""
Example Dash app demonstrating the dash-improve-my-llms hook

This example shows:
1. Basic setup with Dash Pages
2. Marking components as important
3. Custom page metadata
4. Automatic llms.txt, page.json, and architecture.txt generation

Run with: python app.py
Then visit:
- http://localhost:8050/ (Home)
- http://localhost:8050/equipment (Equipment)
- http://localhost:8050/analytics (Analytics)
- http://localhost:8050/llms.txt (LLM-friendly docs for current page)
- http://localhost:8050/page.json (Architecture for current page)
- http://localhost:8050/architecture.txt (Overall app architecture)
"""

import dash_mantine_components as dmc
from dash import Dash, dcc, html, page_container
from dash_improve_my_llms import add_llms_routes

# Create app with Dash Pages enabled
app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)

# Add LLMS routes - this enables automatic generation
add_llms_routes(app)

# Main app layout with navigation
app.layout = dmc.MantineProvider(
    [
        html.Div(
            [
                # Header
                html.Div(
                    [
                        html.H1(
                            "Equipment Management System",
                            style={"margin": "0", "color": "white"},
                        ),
                        html.P(
                            "Powered by dash-improve-my-llms hook",
                            style={
                                "margin": "5px 0 0 0",
                                "fontSize": "14px",
                                "color": "rgba(255,255,255,0.8)",
                            },
                        ),
                    ],
                    style={
                        "padding": "20px",
                        "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                        "color": "white",
                    },
                ),
                # Navigation
                html.Div(
                    [
                        dcc.Link(
                            "🏠 Home",
                            href="/",
                            style={"margin": "0 15px", "textDecoration": "none"},
                        ),
                        dcc.Link(
                            "🔧 Equipment",
                            href="/equipment",
                            style={"margin": "0 15px", "textDecoration": "none"},
                        ),
                        dcc.Link(
                            "📊 Analytics",
                            href="/analytics",
                            style={"margin": "0 15px", "textDecoration": "none"},
                        ),
                        html.Span("|", style={"margin": "0 10px", "color": "#ccc"}),
                        html.A(
                            "📄 llms.txt",
                            href="/llms.txt",
                            target="_blank",
                            style={"margin": "0 10px", "textDecoration": "none"},
                        ),
                        html.A(
                            "📋 page.json",
                            href="/page.json",
                            target="_blank",
                            style={"margin": "0 10px", "textDecoration": "none"},
                        ),
                        html.A(
                            "🏗️ architecture.txt",
                            href="/architecture.txt",
                            target="_blank",
                            style={"margin": "0 10px", "textDecoration": "none"},
                        ),
                    ],
                    style={
                        "padding": "15px 20px",
                        "background": "#f8f9fa",
                        "borderBottom": "2px solid #e0e0e0",
                    },
                ),
                # Page content
                html.Div(
                    [page_container],
                    style={"padding": "30px", "maxWidth": "1200px", "margin": "0 auto"},
                ),
                # Footer
                html.Div(
                    [
                        html.P(
                            [
                                "Built with ",
                                html.A(
                                    "Dash",
                                    href="https://dash.plotly.com",
                                    target="_blank",
                                ),
                                " and ",
                                html.A(
                                    "dash-improve-my-llms",
                                    href="https://github.com/yourusername/dash-improve-my-llms",
                                    target="_blank",
                                ),
                            ],
                            style={
                                "textAlign": "center",
                                "color": "#666",
                                "fontSize": "14px",
                            },
                        ),
                    ],
                    style={
                        "padding": "20px",
                        "borderTop": "1px solid #e0e0e0",
                        "marginTop": "40px",
                    },
                ),
            ],
            style={"fontFamily": "Arial, sans-serif"},
        ),
    ]
)

if __name__ == "__main__":
    app.run(debug=True, port=8959)
