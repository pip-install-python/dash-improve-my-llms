import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html, register_page
from dash_improve_my_llms import mark_important, register_page_metadata

register_page(
    __name__,
    path="/analytics",
    name="Analytics Dashboard",
)

register_page_metadata(
    path="/analytics",
    name="Analytics Dashboard",
    description="Real-time analytics and usage statistics for equipment tracking",
)


def layout():
    return html.Div(
        [
            html.H1("Analytics Dashboard"),
            mark_important(
                html.Div(
                    [
                        html.H2("Key Metrics"),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.H3(
                                            "95%",
                                            style={
                                                "color": "green",
                                                "fontSize": "36px",
                                            },
                                        ),
                                        html.P("Utilization Rate"),
                                    ],
                                    style={
                                        "flex": "1",
                                        "textAlign": "center",
                                        "padding": "20px",
                                        "background": "#e8f5e9",
                                    },
                                ),
                                html.Div(
                                    [
                                        html.H3(
                                            "142",
                                            style={"color": "blue", "fontSize": "36px"},
                                        ),
                                        html.P("Active Items"),
                                    ],
                                    style={
                                        "flex": "1",
                                        "textAlign": "center",
                                        "padding": "20px",
                                        "background": "#e3f2fd",
                                    },
                                ),
                                html.Div(
                                    [
                                        html.H3(
                                            "$12.5K",
                                            style={
                                                "color": "orange",
                                                "fontSize": "36px",
                                            },
                                        ),
                                        html.P("Monthly Savings"),
                                    ],
                                    style={
                                        "flex": "1",
                                        "textAlign": "center",
                                        "padding": "20px",
                                        "background": "#fff3e0",
                                    },
                                ),
                            ],
                            style={
                                "display": "flex",
                                "gap": "20px",
                                "marginBottom": "30px",
                            },
                        ),
                    ],
                    id="key-metrics",
                )
            ),
            html.Div(
                [
                    html.H2("Usage Trends"),
                    dmc.Select(
                        id="trend-period",
                        data=[
                            {"value": "week", "label": "Last Week"},
                            {"value": "month", "label": "Last Month"},
                            {"value": "year", "label": "Last Year"},
                        ],
                        value="month",
                        style={"width": "200px", "marginBottom": "20px"},
                    ),
                    html.Div(
                        id="trend-chart",
                        children=[html.P("📊 Chart showing usage trends over time")],
                        style={
                            "padding": "40px",
                            "background": "#f5f5f5",
                            "textAlign": "center",
                        },
                    ),
                ]
            ),
            html.Div(
                [
                    html.H2("Recent Activity"),
                    html.Ul(
                        [
                            html.Li("Forklift #23 checked out by John (2 hours ago)"),
                            html.Li("CNC Machine completed maintenance (5 hours ago)"),
                            html.Li("New drill press added to inventory (Yesterday)"),
                            html.Li("Monthly report generated (2 days ago)"),
                        ]
                    ),
                ],
                style={"marginTop": "30px"},
            ),
            html.Div(
                [
                    dcc.Link("← Back to Home", href="/"),
                    " | ",
                    dcc.Link("View Equipment →", href="/equipment"),
                ],
                style={"marginTop": "20px"},
            ),
        ]
    )


@callback(
    Output("trend-chart", "children"),
    Input("trend-period", "value"),
)
def update_trend_chart(period):
    return html.P(f"📊 Showing trends for: {period}")
