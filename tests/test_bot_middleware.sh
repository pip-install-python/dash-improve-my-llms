#!/bin/bash

echo "🤖 Testing Bot Response Middleware"
echo "=================================="
echo ""

# Test 1: AI Training Bot (should get 403)
echo "1️⃣ Testing AI Training Bot (anthropic-ai) - Should get 403 Forbidden"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -s -A "anthropic-ai" http://localhost:8959/ | head -5
echo ""
echo ""

# Test 2: AI Search Bot (should get static HTML)
echo "2️⃣ Testing AI Search Bot (ClaudeBot) - Should get static HTML"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -s -A "ClaudeBot/1.0" http://localhost:8959/ | head -20
echo ""
echo ""

# Test 3: Regular Browser (should get full Dash app)
echo "3️⃣ Testing Regular Browser (Chrome) - Should get full Dash React app"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -s -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0" http://localhost:8959/ | grep -o "react-entry-point\|_dash-renderer\|403 Forbidden\|<noscript>" | head -5
echo ""
echo ""

# Summary
echo "📊 Summary of Expected Behavior:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Training Bot (anthropic-ai):  403 Forbidden (blocked)"
echo "✅ Search Bot (ClaudeBot):       Static HTML with <noscript> fallback"
echo "✅ Browser (Chrome):             Full Dash app with react-entry-point"
echo ""