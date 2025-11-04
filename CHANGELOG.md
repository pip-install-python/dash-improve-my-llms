# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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