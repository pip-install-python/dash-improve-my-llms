"""
Admin Dashboard - Visitor Analytics

This page demonstrates:
1. mark_hidden() - This page is hidden from AI bots and search engines
2. Visitor tracking - Desktop, Mobile, Tablet, and Bot visits
3. Bot type detection - Identifies AI training, AI search, and traditional bots
4. Plotly visualizations - Beautiful graphs showing analytics
5. Real-time data - Updates on page refresh

This page won't appear in:
- sitemap.xml
- robots.txt (will be blocked)
- /admin/llms.txt (returns 404)
- /admin/page.json (returns 404)
"""

import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html, register_page
from dash_improve_my_llms import mark_hidden, register_page_metadata
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
from pathlib import Path
from collections import Counter

# Register page
register_page(
    __name__,
    path="/admin",
    name="Admin Dashboard",
)

# Register metadata
register_page_metadata(
    path="/admin",
    name="Admin Dashboard",
    description="Visitor analytics dashboard with device and bot tracking - Hidden from search engines",
)

# HIDE THIS PAGE FROM AI BOTS AND SEARCH ENGINES (NEW v0.2.0!)
mark_hidden("/admin")

# Path to analytics data
ANALYTICS_FILE = Path(__file__).parent.parent / "visitor_analytics.json"


def load_analytics():
    """Load analytics data from JSON file."""
    if ANALYTICS_FILE.exists():
        with open(ANALYTICS_FILE, "r") as f:
            data = json.load(f)

            # Clean up any _reload-hash or internal Dash paths from existing data
            clean_visits = []
            for visit in data.get("visits", []):
                path = visit.get("path", "")
                # Filter out internal Dash paths
                if not any(ext in path for ext in ['.css', '.js', '.png', '.jpg', '.ico', '_dash', '_reload-hash']):
                    clean_visits.append(visit)

            # Recalculate stats from clean visits
            stats = {
                "desktop": 0,
                "mobile": 0,
                "tablet": 0,
                "bot": 0,
                "total": 0
            }

            for visit in clean_visits:
                device_type = visit.get("device_type", "desktop")
                stats[device_type] = stats.get(device_type, 0) + 1
                stats["total"] += 1

            return {
                "visits": clean_visits,
                "stats": stats
            }

    return {
        "visits": [],
        "stats": {
            "desktop": 0,
            "mobile": 0,
            "tablet": 0,
            "bot": 0,
            "total": 0
        }
    }


def get_bot_visits_by_type(visits):
    """Get bot visits grouped by bot type."""
    bot_visits = [v for v in visits if v["device_type"] == "bot"]
    bot_types = Counter([v.get("bot_type", "unknown") for v in bot_visits])
    return bot_types


def get_visits_by_hour(visits):
    """Get visits grouped by hour for the last 24 hours."""
    now = datetime.now()
    twenty_four_hours_ago = now - timedelta(hours=24)

    # Filter visits from last 24 hours
    recent_visits = []
    for visit in visits:
        try:
            visit_time = datetime.fromisoformat(visit["timestamp"])
            if visit_time >= twenty_four_hours_ago:
                recent_visits.append(visit)
        except:
            continue

    # Group by hour
    hourly_counts = {}
    for i in range(24):
        hour = (now - timedelta(hours=23-i)).strftime("%H:00")
        hourly_counts[hour] = {"desktop": 0, "mobile": 0, "tablet": 0, "bot": 0}

    for visit in recent_visits:
        try:
            visit_time = datetime.fromisoformat(visit["timestamp"])
            hour_key = visit_time.strftime("%H:00")
            device_type = visit["device_type"]
            if hour_key in hourly_counts:
                hourly_counts[hour_key][device_type] += 1
        except:
            continue

    return hourly_counts


def get_top_pages(visits, limit=10):
    """Get most visited pages."""
    page_counts = Counter([v["path"] for v in visits if v["path"] not in ["/_dash-update-component", "/_dash-layout"]])
    return page_counts.most_common(limit)


def layout():
    analytics = load_analytics()
    visits = analytics["visits"]
    stats = analytics["stats"]
    bot_types = get_bot_visits_by_type(visits)
    hourly_data = get_visits_by_hour(visits)
    top_pages = get_top_pages(visits)

    # Get recent bot visits with details
    recent_bot_visits = [v for v in visits if v["device_type"] == "bot"][-20:]
    recent_bot_visits.reverse()

    return dmc.Container([
        # Header Section - Improved visual hierarchy
        dmc.Stack([
            dmc.Group([
                dmc.Stack([
                    dmc.Title("Admin Dashboard", order=1, c="gray.9"),
                    dmc.Text(
                        "Visitor Analytics & Bot Tracking",
                        size="lg",
                        c="dimmed"
                    ),
                ], gap=4),
                dmc.Stack([
                    dmc.Badge("Hidden Page", color="red", size="lg", variant="filled"),
                    dmc.Text("Not in sitemap.xml", size="xs", c="dimmed"),
                ], gap=4, align="flex-end"),
            ], justify="space-between", align="flex-start"),

            # Info Alert - Better clarity
            dmc.Alert(
                children=[
                    dmc.Text([
                        "This page demonstrates ",
                        dmc.Code("mark_hidden()"),
                        " functionality. It's excluded from sitemaps, blocked in robots.txt, and returns 404 for AI bot documentation requests."
                    ], size="sm"),
                ],
                title="🔒 Privacy Control Demo",
                color="blue",
                variant="light",
                radius="md",
            ),
        ], gap="xl", mb="xl"),

        # Stats Cards Section - Improved spacing and visual hierarchy
        dmc.SimpleGrid(
            cols={"base": 1, "xs": 2, "sm": 3, "md": 5},
            spacing="lg",
            mb="xl",
            children=[
                create_stat_card(
                    value=stats['total'],
                    label="Total Visits",
                    icon="📊",
                    color="violet"
                ),
                create_stat_card(
                    value=stats['desktop'],
                    label="Desktop",
                    icon="🖥️",
                    color="gray"
                ),
                create_stat_card(
                    value=stats['mobile'],
                    label="Mobile",
                    icon="📱",
                    color="gray"
                ),
                create_stat_card(
                    value=stats['tablet'],
                    label="Tablet",
                    icon="📲",
                    color="gray"
                ),
                create_stat_card(
                    value=stats['bot'],
                    label="Bots",
                    icon="🤖",
                    color="gray"
                ),
            ]
        ),

        # Main Content - Tabs for progressive disclosure
        dmc.Tabs(
            value="overview",
            children=[
                dmc.TabsList([
                    dmc.TabsTab("Overview", value="overview"),
                    dmc.TabsTab("Bot Activity", value="bots"),
                    dmc.TabsTab("Configuration", value="config"),
                ]),

                # Overview Tab
                dmc.TabsPanel(value="overview", pt="xl", children=[
                    dmc.Stack([
                        # Charts Grid - Better layout with consistent spacing
                        dmc.SimpleGrid(
                            cols={"base": 1, "md": 2},
                            spacing="lg",
                            mb="lg",
                            children=[
                                create_chart_card(
                                    title="Device Distribution",
                                    description="Breakdown by device type",
                                    chart=create_device_pie_chart(stats)
                                ),
                                create_chart_card(
                                    title="Bot Types",
                                    description="AI Training, Search, and Traditional bots",
                                    chart=create_bot_types_chart(bot_types)
                                ),
                            ]
                        ),

                        # Full-width hourly chart
                        create_chart_card(
                            title="Visits by Hour",
                            description="Activity over the last 24 hours",
                            chart=create_hourly_chart(hourly_data)
                        ),

                        # Top pages chart
                        create_chart_card(
                            title="Most Visited Pages",
                            description="Top 10 pages by visit count",
                            chart=create_top_pages_chart(top_pages)
                        ),
                    ], gap="lg"),
                ]),

                # Bot Activity Tab
                dmc.TabsPanel(value="bots", pt="xl", children=[
                    dmc.Stack([
                        dmc.Alert(
                            children="Track AI training bots, AI search bots, and traditional search engines visiting your application.",
                            title="Bot Monitoring",
                            color="blue",
                            variant="light",
                        ),

                        dmc.Paper([
                            dmc.Title("Recent Bot Visits", order=3, mb="md"),
                            create_bot_visits_table(recent_bot_visits) if recent_bot_visits else dmc.Text(
                                "No bot visits yet. Bots will be tracked automatically.",
                                c="dimmed",
                                fs="italic"
                            ),
                        ], p="lg", radius="md", withBorder=True),
                    ], gap="lg"),
                ]),

                # Configuration Tab
                dmc.TabsPanel(value="config", pt="xl", children=[
                    dmc.Stack([
                        # Bot Type Reference
                        dmc.Paper([
                            dmc.Title("Bot Type Reference", order=3, mb="lg"),
                            dmc.SimpleGrid(
                                cols={"base": 1, "sm": 3},
                                spacing="lg",
                                children=[
                                    create_bot_type_info(
                                        "AI Training",
                                        "GPTBot, anthropic-ai, Claude-Web, CCBot, Google-Extended",
                                        "🚫 Blocked by default",
                                        "red"
                                    ),
                                    create_bot_type_info(
                                        "AI Search",
                                        "ChatGPT-User, ClaudeBot, PerplexityBot",
                                        "✅ Allowed by default",
                                        "blue"
                                    ),
                                    create_bot_type_info(
                                        "Traditional",
                                        "Googlebot, Bingbot, Yahoo, DuckDuckBot",
                                        "✅ Allowed by default",
                                        "green"
                                    ),
                                ]
                            ),
                        ], p="lg", radius="md", withBorder=True, mb="lg"),

                        # Current Configuration
                        dmc.Paper([
                            dmc.Title("Current Configuration", order=3, mb="md"),
                            dmc.Code(
                                """RobotsConfig(
    block_ai_training=True,
    allow_ai_search=True,
    allow_traditional=True,
    crawl_delay=10,
    disallowed_paths=["/admin", "/api/*"]
)""",
                                block=True,
                            ),
                        ], p="lg", radius="md", withBorder=True),
                    ], gap="lg"),
                ]),
            ]
        ),

        # Footer Navigation
        dmc.Divider(mt="xl", mb="lg"),
        dmc.Group([
            dcc.Link("← Home", href="/", style={"textDecoration": "none"}),
            dcc.Link("Equipment", href="/equipment", style={"textDecoration": "none"}),
            dcc.Link("Analytics", href="/analytics", style={"textDecoration": "none"}),
        ], gap="lg"),

    ], size="xl", py="xl")


def create_stat_card(value, label, icon, color="violet"):
    """Create a stat card with improved visual hierarchy."""
    return dmc.Paper([
        dmc.Stack([
            dmc.Group([
                dmc.Text(icon, size="xl"),
                dmc.Title(
                    f"{value:,}",
                    order=2,
                    c=f"{color}.6" if color != "gray" else "gray.9"
                ),
            ], gap="xs", justify="center"),
            dmc.Text(label, size="sm", c="dimmed", ta="center"),
        ], gap="xs", align="center"),
    ], p="lg", radius="md", withBorder=True, shadow="sm")


def create_chart_card(title, description, chart):
    """Create a chart card with consistent styling."""
    return dmc.Paper([
        dmc.Stack([
            dmc.Stack([
                dmc.Title(title, order=3),
                dmc.Text(description, size="sm", c="dimmed"),
            ], gap=4),
            dcc.Graph(
                figure=chart,
                config={'displayModeBar': False},
                style={"height": "350px"}
            ),
        ], gap="md"),
    ], p="lg", radius="md", withBorder=True, shadow="sm")


def create_bot_type_info(title, bots, status, color):
    """Create bot type information card."""
    return dmc.Paper([
        dmc.Stack([
            dmc.Badge(title, color=color, size="lg", variant="filled"),
            dmc.Text(bots, size="sm", c="dimmed"),
            dmc.Text(status, size="xs", fw=600, c=color),
        ], gap="xs"),
    ], p="md", radius="md", withBorder=True)


def create_device_pie_chart(stats):
    """Create pie chart for device distribution."""
    labels = []
    values = []
    colors = ['#7950f2', '#495057', '#495057', '#495057', '#495057']  # Violet primary, gray for others

    device_data = [
        ('Desktop', stats['desktop']),
        ('Mobile', stats['mobile']),
        ('Tablet', stats['tablet']),
        ('Bots', stats['bot']),
    ]

    for label, value in device_data:
        if value > 0:
            labels.append(label)
            values.append(value)

    if not values:
        labels = ['No visits yet']
        values = [1]
        colors = ['#e9ecef']

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors[:len(values)]),
        hole=0.5,
        textinfo='label+percent',
        textposition='auto',
    )])

    fig.update_layout(
        showlegend=True,
        margin=dict(t=10, b=10, l=10, r=10),
        height=350,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5
        ),
        font=dict(size=12),
    )

    return fig


def create_bot_types_chart(bot_types):
    """Create bar chart for bot types."""
    if not bot_types:
        fig = go.Figure()
        fig.add_annotation(
            text="No bot visits yet",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14, color="#868e96")
        )
        fig.update_layout(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            margin=dict(t=10, b=10, l=10, r=10),
            height=350,
        )
        return fig

    # Map bot types to colors - using restrained palette
    color_map = {
        'training': '#fa5252',
        'search': '#228be6',
        'traditional': '#40c057',
        'unknown': '#868e96'
    }

    labels = list(bot_types.keys())
    values = list(bot_types.values())
    colors = [color_map.get(label, '#868e96') for label in labels]

    # Capitalize labels for display
    display_labels = [label.capitalize() if label != 'unknown' else 'Unknown' for label in labels]

    fig = go.Figure(data=[go.Bar(
        x=display_labels,
        y=values,
        marker=dict(color=colors),
        text=values,
        textposition='auto',
    )])

    fig.update_layout(
        xaxis_title="Bot Type",
        yaxis_title="Visits",
        margin=dict(t=10, b=40, l=40, r=10),
        height=350,
        showlegend=False,
        font=dict(size=12),
    )

    return fig


def create_hourly_chart(hourly_data):
    """Create stacked area chart for hourly visits."""
    if not hourly_data:
        fig = go.Figure()
        fig.add_annotation(
            text="No visit data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14, color="#868e96")
        )
        fig.update_layout(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            margin=dict(t=10, b=10, l=10, r=10),
            height=350,
        )
        return fig

    hours = list(hourly_data.keys())
    desktop_counts = [hourly_data[h]['desktop'] for h in hours]
    mobile_counts = [hourly_data[h]['mobile'] for h in hours]
    tablet_counts = [hourly_data[h]['tablet'] for h in hours]
    bot_counts = [hourly_data[h]['bot'] for h in hours]

    fig = go.Figure()

    # Using restrained color palette
    fig.add_trace(go.Scatter(
        x=hours, y=desktop_counts,
        name='Desktop',
        mode='lines',
        line=dict(width=2, color='#7950f2'),
        fill='tonexty',
        stackgroup='one',
    ))

    fig.add_trace(go.Scatter(
        x=hours, y=mobile_counts,
        name='Mobile',
        mode='lines',
        line=dict(width=2, color='#228be6'),
        fill='tonexty',
        stackgroup='one',
    ))

    fig.add_trace(go.Scatter(
        x=hours, y=tablet_counts,
        name='Tablet',
        mode='lines',
        line=dict(width=2, color='#40c057'),
        fill='tonexty',
        stackgroup='one',
    ))

    fig.add_trace(go.Scatter(
        x=hours, y=bot_counts,
        name='Bots',
        mode='lines',
        line=dict(width=2, color='#fab005'),
        fill='tonexty',
        stackgroup='one',
    ))

    fig.update_layout(
        xaxis_title="Hour",
        yaxis_title="Visits",
        margin=dict(t=10, b=40, l=40, r=10),
        height=350,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        font=dict(size=12),
    )

    return fig


def create_top_pages_chart(top_pages):
    """Create horizontal bar chart for top pages."""
    if not top_pages:
        fig = go.Figure()
        fig.add_annotation(
            text="No page visits yet",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14, color="#868e96")
        )
        fig.update_layout(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            margin=dict(t=10, b=10, l=10, r=10),
            height=350,
        )
        return fig

    pages = [page[0] for page in top_pages]
    counts = [page[1] for page in top_pages]

    fig = go.Figure(data=[go.Bar(
        x=counts,
        y=pages,
        orientation='h',
        marker=dict(color='#7950f2'),
        text=counts,
        textposition='auto',
    )])

    fig.update_layout(
        xaxis_title="Visits",
        yaxis_title="Page",
        margin=dict(t=10, b=40, l=150, r=10),
        height=350,
        showlegend=False,
        font=dict(size=12),
    )

    return fig


def create_bot_visits_table(bot_visits):
    """Create a table showing recent bot visits."""
    if not bot_visits:
        return dmc.Text("No bot visits recorded yet.", c="dimmed", fs="italic")

    rows = []
    for visit in bot_visits:
        timestamp = visit.get('timestamp', 'Unknown')
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = timestamp

        bot_type = visit.get('bot_type', 'unknown')

        # Color code by bot type
        if bot_type == 'training':
            badge = dmc.Badge("Training", color="red", size="sm", variant="filled")
        elif bot_type == 'search':
            badge = dmc.Badge("Search", color="blue", size="sm", variant="filled")
        elif bot_type == 'traditional':
            badge = dmc.Badge("Traditional", color="green", size="sm", variant="filled")
        else:
            badge = dmc.Badge("Unknown", color="gray", size="sm", variant="outline")

        user_agent = visit.get('user_agent', 'Unknown')
        truncated_ua = user_agent[:80] + "..." if len(user_agent) > 80 else user_agent

        rows.append(
            dmc.TableTr([
                dmc.TableTd(dmc.Text(time_str, size="sm", ff="monospace")),
                dmc.TableTd(badge),
                dmc.TableTd(dmc.Code(visit.get('path', '/'), style={"fontSize": "12px"})),
                dmc.TableTd(dmc.Text(truncated_ua, size="xs", c="dimmed", style={"maxWidth": "400px"})),
            ])
        )

    return dmc.Table([
        dmc.TableThead(
            dmc.TableTr([
                dmc.TableTh("Timestamp"),
                dmc.TableTh("Bot Type"),
                dmc.TableTh("Page"),
                dmc.TableTh("User Agent"),
            ])
        ),
        dmc.TableTbody(rows),
    ], striped=True, highlightOnHover=True, withTableBorder=True, withColumnBorders=True)