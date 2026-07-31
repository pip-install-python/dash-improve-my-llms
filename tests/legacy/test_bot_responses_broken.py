#!/usr/bin/env python
"""
Test bot response differentiation

This script tests that different bot types receive different responses:
- Training bots (when blocked): 403 Forbidden
- Search/Traditional bots: Static HTML
- Regular browsers: Full Dash React app
"""

import requests
from typing import Dict, List

BASE_URL = "http://localhost:8959"

# Test cases
TEST_CASES = [
    {
        "name": "AI Training Bot (GPTBot)",
        "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.0; +https://openai.com/gptbot)",
        "expected": "403",
        "bot_type": "training",
    },
    {
        "name": "AI Training Bot (anthropic-ai)",
        "user_agent": "anthropic-ai",
        "expected": "403",
        "bot_type": "training",
    },
    {
        "name": "AI Search Bot (ClaudeBot)",
        "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
        "expected": "static_html",
        "bot_type": "search",
    },
    {
        "name": "AI Search Bot (ChatGPT-User)",
        "user_agent": "ChatGPT-User",
        "expected": "static_html",
        "bot_type": "search",
    },
    {
        "name": "Traditional Bot (Googlebot)",
        "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "expected": "static_html",
        "bot_type": "traditional",
    },
    {
        "name": "Regular Browser (Chrome)",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "expected": "dash_app",
        "bot_type": "browser",
    },
    {
        "name": "Regular Browser (Firefox)",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
        "expected": "dash_app",
        "bot_type": "browser",
    },
]


def analyze_response(response: requests.Response) -> Dict:
    """Analyze the response and determine what type it is."""
    status = response.status_code
    content = response.text

    result = {"status_code": status, "content_length": len(content), "type": "unknown"}

    if status == 403:
        result["type"] = "403_forbidden"
        result["has_403_message"] = "403 Forbidden" in content
        result["has_bot_blocked_message"] = "AI training bots are not allowed" in content
    elif "Bot-Optimized Content" in content and '<div id="react-entry-point">' not in content:
        # New detection for llms.txt-based bot responses
        result["type"] = "static_html"
        result["has_bot_notice"] = True
        result["has_llms_content"] = "llms.txt" in content
        result["has_documentation_links"] = "page.json" in content and "architecture.txt" in content
        result["is_crawlable"] = "<pre>" in content  # llms.txt content in pre tag
    elif "<noscript>" in content and '<div id="react-entry-point">' not in content:
        # Legacy detection for noscript-based responses
        result["type"] = "static_html"
        result["has_noscript"] = True
        result["has_structured_data"] = "application/ld+json" in content or "schema.org" in content
        result["has_navigation"] = "<nav>" in content or "navigation" in content.lower()
    elif '<div id="react-entry-point">' in content:
        result["type"] = "dash_app"
        result["has_react_entry"] = True
        result["has_dash_renderer"] = "_dash-renderer" in content
        result["has_js_bundles"] = "dash_core_components" in content

    return result


def test_bot_response(test_case: Dict) -> Dict:
    """Test a single bot/browser and analyze the response."""
    print(f"\n{'='*80}")
    print(f"Testing: {test_case['name']}")
    print(f"Bot Type: {test_case['bot_type']}")
    print(f"Expected: {test_case['expected']}")
    print(f"{'='*80}")

    headers = {"User-Agent": test_case["user_agent"]}

    try:
        response = requests.get(BASE_URL, headers=headers, timeout=5)
        analysis = analyze_response(response)

        print(f"Status Code: {analysis['status_code']}")
        print(f"Content Length: {analysis['content_length']} bytes")
        print(f"Response Type: {analysis['type']}")

        # Check expectations
        expected = test_case["expected"]
        actual = analysis["type"]

        if expected == "403" and actual == "403_forbidden":
            print("✅ PASS: Correctly blocked with 403")
            success = True
        elif expected == "static_html" and actual == "static_html":
            print("✅ PASS: Correctly served static HTML")
            if analysis.get("has_bot_notice"):
                print("   ✓ Has bot-optimized content notice")
            if analysis.get("has_llms_content"):
                print("   ✓ Has llms.txt content")
            if analysis.get("has_documentation_links"):
                print("   ✓ Has documentation links (page.json, architecture.txt)")
            if analysis.get("is_crawlable"):
                print("   ✓ Content is crawlable (in <pre> tag)")
            if analysis.get("has_structured_data"):
                print("   ✓ Has structured data (Schema.org)")
            if analysis.get("has_noscript"):
                print("   ✓ Has <noscript> fallback")
            success = True
        elif expected == "dash_app" and actual == "dash_app":
            print("✅ PASS: Correctly served full Dash app")
            if analysis.get("has_react_entry"):
                print("   ✓ Has React entry point")
            if analysis.get("has_dash_renderer"):
                print("   ✓ Has Dash renderer")
            success = True
        else:
            print(f"❌ FAIL: Expected {expected}, got {actual}")
            success = False

        return {
            "test_case": test_case["name"],
            "success": success,
            "expected": expected,
            "actual": actual,
            "analysis": analysis,
        }

    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to server")
        print("   Make sure the app is running: python app.py")
        return {"test_case": test_case["name"], "success": False, "error": "connection_error"}
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return {"test_case": test_case["name"], "success": False, "error": str(e)}


def main():
    """Run all tests and print summary."""
    print("\n" + "=" * 80)
    print("BOT RESPONSE MIDDLEWARE TESTS".center(80))
    print("=" * 80)
    print(f"\nTesting against: {BASE_URL}")
    print(f"Total test cases: {len(TEST_CASES)}\n")

    results = []
    for test_case in TEST_CASES:
        result = test_bot_response(test_case)
        results.append(result)

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY".center(80))
    print("=" * 80)

    passed = sum(1 for r in results if r.get("success", False))
    failed = len(results) - passed

    print(f"\nTotal Tests: {len(results)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Pass Rate: {(passed/len(results)*100):.1f}%\n")

    # Show details of failed tests
    failed_tests = [r for r in results if not r.get("success", False)]
    if failed_tests:
        print("\nFailed Tests:")
        print("-" * 80)
        for result in failed_tests:
            print(f"  • {result['test_case']}")
            if "expected" in result and "actual" in result:
                print(f"    Expected: {result['expected']}, Got: {result['actual']}")
            elif "error" in result:
                print(f"    Error: {result['error']}")
        print()

    # Print configuration info
    print("\nCurrent RobotsConfig:")
    print("-" * 80)
    print(
        """RobotsConfig(
    block_ai_training=True,   # Training bots should get 403
    allow_ai_search=True,     # Search bots should get static HTML
    allow_traditional=True,   # Traditional bots should get static HTML
    crawl_delay=10,
    disallowed_paths=["/admin", "/api/*"]
)"""
    )
    print()

    # Print what each bot type should receive
    print("\nExpected Behavior:")
    print("-" * 80)
    print("🚫 Training Bots  (GPTBot, anthropic-ai, CCBot):")
    print("   → 403 Forbidden (blocked by block_ai_training=True)")
    print()
    print("🔍 Search Bots    (ClaudeBot, ChatGPT-User, PerplexityBot):")
    print("   → llms.txt content wrapped in HTML (bot-optimized, crawlable)")
    print("   → Links to /llms.txt, /page.json, /architecture.txt, /sitemap.xml")
    print()
    print("🌐 Traditional    (Googlebot, Bingbot, Yahoo):")
    print("   → llms.txt content wrapped in HTML (bot-optimized, crawlable)")
    print("   → Links to /llms.txt, /page.json, /architecture.txt, /sitemap.xml")
    print()
    print("👤 Browsers       (Chrome, Firefox, Safari):")
    print("   → Full Dash React app with JavaScript bundles")
    print()
    print("💡 Key Insight:")
    print("   AI crawlers cannot execute JavaScript, so they get llms.txt content")
    print("   instead of <div id='react-entry-point'> placeholders.")
    print()


if __name__ == "__main__":
    main()
