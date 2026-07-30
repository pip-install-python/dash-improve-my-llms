"""
Analytics dashboard page.

Demonstrates a Plotly-style metric-card layout with a single callback
driven by a period dropdown. The /analytics/llms.txt endpoint serves
the LLMS_DOC string below verbatim.
"""

import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html, register_page

from dash_improve_my_llms import register_page_metadata

register_page(__name__, path="/analytics", name="Analytics Dashboard")


LLMS_DOC = """\
# Analytics Dashboard

> Headline metrics, a usage-trend chart selector, and a recent-activity feed.

## What this page does

Renders three Key Metrics cards (utilization, active item count,
monthly savings), a "Usage Trends" section with a period selector
(week / month / year), and a "Recent Activity" feed of the last few
notable events.

The metric values are illustrative and hard-coded. The period
selector updates the chart placeholder via a single callback; it
does not yet pull real data.

## What the user can do

- Read the three top-line metrics at a glance.
- Switch the trend period via the dropdown to see the chart update.
- Skim the recent-activity list to understand what's happened lately.

## What the page does NOT do

The chart is a placeholder — no actual Plotly figure is rendered. The
"recent activity" list is static. A real implementation would back
this with timeseries data and a `dcc.Graph` showing utilization
percent over time, plus a paginated event log.

## How this page is wired up

One callback maps the period dropdown's value to the contents of the
`trend-chart` div. No other interactivity. The metric cards are
static and re-render only on full page load.
"""


register_page_metadata(
    path="/analytics",
    name="Analytics Dashboard",
    description="Headline metrics, a trend chart selector, and a recent-activity feed — a regular Dash page wired up with its own LLMS_DOC.",
)


def layout():
    return html.Div(
        [
            html.H1("Analytics Dashboard"),
            html.Div(
                [
                    html.H2("Key Metrics"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("95%", style={"color": "green", "fontSize": "36px"}),
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
                                    html.H3("142", style={"color": "blue", "fontSize": "36px"}),
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
                                        "$12.5K", style={"color": "orange", "fontSize": "36px"}
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
                        style={"display": "flex", "gap": "20px", "marginBottom": "30px"},
                    ),
                ],
                id="key-metrics",
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
                    dcc.Link("MCP Audience →", href="/audiences/mcp-clients"),
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
