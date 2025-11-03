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


# Define layout - must be named 'layout'
def layout():
    return html.Div(
        [
            html.H1("Welcome to Equipment Management System"),
            html.P("This system helps you track and manage your equipment inventory."),
            # Mark this section as important - all children will be considered important
            mark_important(
                html.Div(
                    [
                        html.H2("Quick Links"),
                        html.Ul(
                            [
                                html.Li(dcc.Link("View Equipment Catalog", href="/equipment")),
                                html.Li(dcc.Link("View Analytics Dashboard", href="/analytics")),
                            ]
                        ),
                    ],
                    id="quick-links",
                )
            ),
            html.Div(
                [
                    html.H3("Features"),
                    html.Ul(
                        [
                            html.Li("Real-time equipment tracking"),
                            html.Li("Usage analytics and reporting"),
                            html.Li("Maintenance scheduling"),
                            html.Li("Cost analysis"),
                        ]
                    ),
                ]
            ),
            html.Div(
                [
                    html.P("Try accessing the LLM-friendly documentation:"),
                    html.Ul(
                        [
                            html.Li(html.A("/llms.txt", href="/llms.txt", target="_blank")),
                            html.Li(html.A("/page.json", href="/page.json", target="_blank")),
                            html.Li(
                                html.A(
                                    "/architecture.txt",
                                    href="/architecture.txt",
                                    target="_blank",
                                )
                            ),
                        ]
                    ),
                ],
                style={"marginTop": "20px", "padding": "10px", "background": "#e8f4f8"},
            ),
        ]
    )
