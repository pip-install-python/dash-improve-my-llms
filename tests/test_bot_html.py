#!/usr/bin/env python3
"""
Test script to verify bot HTML generation works correctly.
Tests different bot user agents and verifies they receive static HTML with structured data.
"""

import requests
from dash_improve_my_llms.bot_detection import (
    is_ai_training_bot,
    is_ai_search_bot,
    is_traditional_bot,
    get_bot_type,
)

# Test configuration
BASE_URL = "http://localhost:8959"  # Change if your app runs on a different port

# Test user agents
TEST_USER_AGENTS = {
    "search": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +https://www.anthropic.com)",
    "training": "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)",
    "traditional": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "browser": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def test_bot_detection():
    """Test that bot detection is working correctly."""
    print("=" * 80)
    print("BOT DETECTION TESTS".center(80))
    print("=" * 80)
    print()

    for bot_name, user_agent in TEST_USER_AGENTS.items():
        bot_type = get_bot_type(user_agent)
        print(f"✓ {bot_name.upper()}: Detected as '{bot_type}'")
        print(f"  User-Agent: {user_agent[:60]}...")
        print()


def test_static_html_generation(url=BASE_URL, path="/"):
    """Test that bots receive static HTML with structured data."""
    print("=" * 80)
    print("STATIC HTML GENERATION TESTS".center(80))
    print("=" * 80)
    print()

    full_url = f"{url}{path}"

    for bot_name, user_agent in TEST_USER_AGENTS.items():
        if bot_name == "training":
            print(f"Testing {bot_name.upper()} bot at {full_url}")
            print(f"  Expected: 403 Forbidden (training bots blocked)")

            try:
                response = requests.get(full_url, headers={"User-Agent": user_agent}, timeout=5)

                if response.status_code == 403:
                    print(f"  ✓ Status: {response.status_code} (Correctly blocked)")
                else:
                    print(f"  ✗ Status: {response.status_code} (Should be 403)")

                print()
            except Exception as e:
                print(f"  ✗ Error: {e}")
                print()

        elif bot_name in ["search", "traditional"]:
            print(f"Testing {bot_name.upper()} bot at {full_url}")
            print(f"  Expected: 200 OK with static HTML")

            try:
                response = requests.get(full_url, headers={"User-Agent": user_agent}, timeout=5)
                content = response.text

                print(f"  ✓ Status: {response.status_code}")

                # Check for structured data
                checks = {
                    "Schema.org JSON-LD": '"@context": "https://schema.org"' in content,
                    "Navigation": "<nav" in content,
                    "Meta description": 'meta name="description"' in content,
                    "AI Discovery links": '/llms.txt' in content,
                    "Sitemap link": "/sitemap.xml" in content or "/architecture.txt" in content,
                }

                for check_name, passed in checks.items():
                    status = "✓" if passed else "✗"
                    print(f"  {status} {check_name}: {'Found' if passed else 'Missing'}")

                print()
            except Exception as e:
                print(f"  ✗ Error: {e}")
                print()

        elif bot_name == "browser":
            print(f"Testing REGULAR BROWSER at {full_url}")
            print(f"  Expected: 200 OK with JavaScript app")

            try:
                response = requests.get(full_url, headers={"User-Agent": user_agent}, timeout=5)
                content = response.text

                print(f"  ✓ Status: {response.status_code}")

                # Check for Dash app indicators
                checks = {
                    "Dash app": "_dash-" in content or "dash" in content.lower(),
                    "React renderer": "dash-renderer" in content or "dash_renderer" in content,
                }

                for check_name, passed in checks.items():
                    status = "✓" if passed else "✗"
                    print(f"  {status} {check_name}: {'Found' if passed else 'Missing'}")

                print()
            except Exception as e:
                print(f"  ✗ Error: {e}")
                print()


def test_all_pages(url=BASE_URL):
    """Test all pages in the application."""
    print("=" * 80)
    print("TESTING ALL PAGES".center(80))
    print("=" * 80)
    print()

    pages = [
        ("/", "Home"),
        ("/equipment", "Equipment"),
        ("/analytics", "Analytics"),
    ]

    user_agent = TEST_USER_AGENTS["search"]  # Use ClaudeBot

    for path, name in pages:
        full_url = f"{url}{path}"
        print(f"Testing {name} page at {full_url}")

        try:
            response = requests.get(full_url, headers={"User-Agent": user_agent}, timeout=5)

            if response.status_code == 200:
                content = response.text
                has_structured_data = '"@context": "https://schema.org"' in content
                has_navigation = "<nav" in content
                has_ai_links = "/llms.txt" in content

                print(f"  ✓ Status: 200 OK")
                print(f"  {'✓' if has_structured_data else '✗'} Schema.org structured data")
                print(f"  {'✓' if has_navigation else '✗'} Navigation")
                print(f"  {'✓' if has_ai_links else '✗'} AI discovery links")
            else:
                print(f"  ✗ Status: {response.status_code}")

            print()
        except Exception as e:
            print(f"  ✗ Error: {e}")
            print()


if __name__ == "__main__":
    print("\n" + "🤖 Bot HTML Generation Test Suite".center(80) + "\n")

    # Test 1: Bot detection
    test_bot_detection()

    # Test 2: Static HTML generation
    print("\n⚠️  Make sure your Dash app is running at http://localhost:8959")
    print("   Run 'python app.py' in another terminal if it's not running.\n")

    print("Starting tests...")
    print()

    test_static_html_generation()

    # Test 3: All pages
    test_all_pages()

    print("=" * 80)
    print("TESTS COMPLETE".center(80))
    print("=" * 80)
    print()
    print("Summary:")
    print("  • Training bots should receive 403 Forbidden")
    print("  • Search/Traditional bots should receive static HTML with structured data")
    print("  • Regular browsers should receive the JavaScript Dash app")
    print()