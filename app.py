"""
Example Dash app demonstrating the dash-improve-my-llms hook v0.2.0

This example shows:
1. Basic setup with Dash Pages
2. Bot management with RobotsConfig (NEW v0.2.0)
3. SEO optimization with base_url (NEW v0.2.0)
4. Privacy controls with mark_hidden (NEW v0.2.0)
5. Marking components as important
6. Custom page metadata
7. Automatic llms.txt, page.json, and architecture.txt generation
8. Automatic robots.txt and sitemap.xml generation (NEW v0.2.0)
9. Visitor analytics tracking (admin dashboard)

Run with: python app.py
Then visit:
- http://localhost:8959/ (Home)
- http://localhost:8959/equipment (Equipment)
- http://localhost:8959/analytics (Analytics)
- http://localhost:8959/admin (Hidden Admin Dashboard - NEW!)
- http://localhost:8959/llms.txt (LLM-friendly docs)
- http://localhost:8959/page.json (Architecture)
- http://localhost:8959/architecture.txt (App overview)
- http://localhost:8959/robots.txt (Bot control - NEW!)
- http://localhost:8959/sitemap.xml (SEO sitemap - NEW!)
"""

import dash_mantine_components as dmc
from dash import Dash, dcc, html, page_container
from dash_improve_my_llms import add_llms_routes, RobotsConfig, mark_hidden
from flask import request
import json
from pathlib import Path
from datetime import datetime

# Import bot detection for visitor tracking
from dash_improve_my_llms.bot_detection import get_bot_type, is_any_bot

# Create app with Dash Pages enabled
app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)

server = app.server

# ============================================================================
# v0.2.0 CONFIGURATION (NEW!)
# ============================================================================

# Configure base URL for SEO (used in sitemap.xml and robots.txt)
app._base_url = "https://554d9a17-106e-455a-a015-1194587c953f.plotly.app"  # Change to your production URL

# Configure bot management policies
app._robots_config = RobotsConfig(
    block_ai_training=True,      # Block GPTBot, CCBot, anthropic-ai, etc.
    allow_ai_search=True,         # Allow ChatGPT-User, ClaudeBot, PerplexityBot
    allow_traditional=True,       # Allow Googlebot, Bingbot, etc.
    crawl_delay=10,               # 10 second delay between bot requests
    custom_rules=[],              # Add custom robots.txt rules here
    disallowed_paths=[
        "/admin",                 # Block admin page
        "/api/*",                 # Block API endpoints
    ]
)

# Add LLMS routes - enables all features
add_llms_routes(app)

# Hide admin page from AI bots and search engines (NEW v0.2.0!)
# This page won't appear in sitemap.xml or robots.txt
# Bots will get 404 for /admin/llms.txt and /admin/page.json
mark_hidden("/admin")

# ============================================================================
# VISITOR TRACKING (for admin dashboard)
# ============================================================================

# Path to store visitor analytics
ANALYTICS_FILE = Path(__file__).parent / "visitor_analytics.json"


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


def save_analytics(data):
    """Save analytics data to JSON file."""
    with open(ANALYTICS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def detect_device_type(user_agent):
    """Detect device type from user agent."""
    ua_lower = user_agent.lower()

    if is_any_bot(user_agent):
        return "bot"
    elif any(mobile in ua_lower for mobile in ["mobile", "android", "iphone", "ipod"]):
        return "mobile"
    elif any(tablet in ua_lower for tablet in ["tablet", "ipad"]):
        return "tablet"
    else:
        return "desktop"


def track_visit():
    """Track page visit with device and bot detection."""
    try:
        user_agent = request.headers.get('User-Agent', 'Unknown')
        path = request.path

        # Don't track asset requests and Dash internal paths
        if any(ext in path for ext in ['.css', '.js', '.png', '.jpg', '.ico', '_dash', '_reload-hash']):
            return

        device_type = detect_device_type(user_agent)
        bot_type = get_bot_type(user_agent) if device_type == "bot" else None

        # Load current analytics
        analytics = load_analytics()

        # Add new visit
        visit = {
            "timestamp": datetime.now().isoformat(),
            "path": path,
            "device_type": device_type,
            "bot_type": bot_type,
            "user_agent": user_agent[:200]  # Truncate long user agents
        }

        analytics["visits"].append(visit)
        analytics["stats"][device_type] += 1
        analytics["stats"]["total"] += 1

        # Keep only last 1000 visits to prevent file from growing too large
        if len(analytics["visits"]) > 1000:
            analytics["visits"] = analytics["visits"][-1000:]

        save_analytics(analytics)

    except Exception as e:
        print(f"Error tracking visit: {e}")


# Add before_request hook to track all visits
@app.server.before_request
def before_request():
    """Track visitor analytics before each request."""
    track_visit()


# ============================================================================
# MAIN APP LAYOUT
# ============================================================================

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
                            "Powered by dash-improve-my-llms v0.2.0 with Bot Management & SEO",
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
                        # Page Navigation
                        dcc.Link(
                            "🏠 Home",
                            href="/",
                            style={"margin": "0 15px", "textDecoration": "none", "fontWeight": "bold"},
                        ),
                        dcc.Link(
                            "🔧 Equipment",
                            href="/equipment",
                            style={"margin": "0 15px", "textDecoration": "none", "fontWeight": "bold"},
                        ),
                        dcc.Link(
                            "📊 Analytics",
                            href="/analytics",
                            style={"margin": "0 15px", "textDecoration": "none", "fontWeight": "bold"},
                        ),
                        dcc.Link(
                            "🔒 Admin",
                            href="/admin",
                            style={
                                "margin": "0 15px",
                                "textDecoration": "none",
                                "fontWeight": "bold",
                                "color": "#ff6b6b"
                            },
                        ),

                        html.Span("|", style={"margin": "0 10px", "color": "#ccc"}),

                        # Documentation Links (v0.1.0)
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

                        html.Span("|", style={"margin": "0 10px", "color": "#ccc"}),

                        # SEO Links (v0.2.0 NEW!)
                        html.A(
                            "🤖 robots.txt",
                            href="/robots.txt",
                            target="_blank",
                            style={"margin": "0 10px", "textDecoration": "none", "color": "#51cf66"},
                            title="NEW v0.2.0: Bot access control"
                        ),
                        html.A(
                            "🗺️ sitemap.xml",
                            href="/sitemap.xml",
                            target="_blank",
                            style={"margin": "0 10px", "textDecoration": "none", "color": "#51cf66"},
                            title="NEW v0.2.0: SEO sitemap"
                        ),
                    ],
                    style={
                        "padding": "15px 20px",
                        "background": "#f8f9fa",
                        "borderBottom": "2px solid #e0e0e0",
                        "fontSize": "14px",
                    },
                ),

                # Page content
                html.Div(
                    [page_container],
                    style={"padding": "30px", "maxWidth": "1400px", "margin": "0 auto"},
                ),

                # Footer with v0.2.0 features
                html.Div(
                    [
                        html.Div(
                            [
                                html.Strong("✨ NEW in v0.2.0: "),
                                "Bot Management • SEO Optimization • Privacy Controls • Visitor Analytics",
                            ],
                            style={
                                "textAlign": "center",
                                "color": "#51cf66",
                                "fontSize": "14px",
                                "marginBottom": "10px",
                                "fontWeight": "bold"
                            },
                        ),
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
                                " | ",
                                html.A(
                                    "View Test Report (88/88 passing)",
                                    href="https://github.com/yourusername/dash-improve-my-llms/blob/main/TEST_REPORT.md",
                                    target="_blank",
                                    style={"color": "#51cf66"}
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
                        "background": "#f8f9fa",
                    },
                ),
            ],
            style={"fontFamily": "Arial, sans-serif"},
        ),
    ]
)

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🚀 dash-improve-my-llms v0.2.0 - Example App")
    print("="*80)
    print("\n📍 Available Routes:")
    print("   • http://localhost:8959/ (Home)")
    print("   • http://localhost:8959/equipment (Equipment Catalog)")
    print("   • http://localhost:8959/analytics (Analytics Dashboard)")
    print("   • http://localhost:8959/admin (Admin Dashboard - Hidden from bots!) 🔒")
    print("\n📄 Documentation Routes (v0.1.0):")
    print("   • http://localhost:8959/llms.txt (LLM-friendly context)")
    print("   • http://localhost:8959/page.json (Technical architecture)")
    print("   • http://localhost:8959/architecture.txt (App overview)")
    print("\n🤖 SEO Routes (NEW v0.2.0):")
    print("   • http://localhost:8959/robots.txt (Bot access control)")
    print("   • http://localhost:8959/sitemap.xml (SEO sitemap)")
    print("\n✨ New Features:")
    print("   ✅ Bot Detection & Management")
    print("   ✅ SEO Optimization with smart sitemaps")
    print("   ✅ Privacy Controls (mark_hidden)")
    print("   ✅ Visitor Analytics Dashboard")
    print("   ✅ 88 Tests Passing (100%)")
    print("\n" + "="*80 + "\n")

    app.run(debug=True, port=8959)