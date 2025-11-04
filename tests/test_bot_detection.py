"""
Tests for bot detection module.
  # AI Training Bots (should show bot_type: "training")
  curl -A "GPTBot/1.0" http://localhost:8959/
  curl -A "anthropic-ai" http://localhost:8959/
  curl -A "Claude-Web/1.0" http://localhost:8959/
  curl -A "CCBot/2.0" http://localhost:8959/
  curl -A "Google-Extended/2.1" http://localhost:8959/

  # AI Search Bots (should show bot_type: "search")
  curl -A "ChatGPT-User" http://localhost:8959/
  curl -A "ClaudeBot/1.0" http://localhost:8959/
  curl -A "PerplexityBot/1.0" http://localhost:8959/

  # Traditional Search Bots (should show bot_type: "traditional")
  curl -A "Googlebot/2.1" http://localhost:8959/
  curl -A "Bingbot/2.0" http://localhost:8959/
  curl -A "Yahoo! Slurp" http://localhost:8959/
  curl -A "DuckDuckBot/1.0" http://localhost:8959/
"""

import pytest
from dash_improve_my_llms.bot_detection import (
    is_ai_training_bot,
    is_ai_search_bot,
    is_traditional_bot,
    is_any_bot,
    get_bot_type,
    get_all_bot_lists,
)


def test_detects_gptbot():
    """Test detection of OpenAI GPTBot."""
    ua = "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)"
    assert is_ai_training_bot(ua) is True
    assert is_any_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_detects_claudebot():
    """Test detection of Anthropic ClaudeBot."""
    ua = "Mozilla/5.0 (compatible; ClaudeBot/1.0)"
    assert is_ai_search_bot(ua) is True
    assert is_any_bot(ua) is True
    assert get_bot_type(ua) == "search"


def test_detects_googlebot():
    """Test detection of Google Search bot."""
    ua = "Mozilla/5.0 (compatible; Googlebot/2.1)"
    assert is_traditional_bot(ua) is True
    assert is_any_bot(ua) is True
    assert get_bot_type(ua) == "traditional"


def test_detects_anthropic_ai():
    """Test detection of Anthropic AI training bot."""
    ua = "Anthropic-AI (https://www.anthropic.com)"
    assert is_ai_training_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_detects_chatgpt_user():
    """Test detection of ChatGPT browsing."""
    ua = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0"
    assert is_ai_search_bot(ua) is True
    assert get_bot_type(ua) == "search"


def test_detects_perplexitybot():
    """Test detection of Perplexity bot."""
    ua = "PerplexityBot/1.0"
    assert is_ai_search_bot(ua) is True
    assert get_bot_type(ua) == "search"


def test_detects_regular_browser():
    """Test that regular browsers are not detected as bots."""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    assert is_any_bot(ua) is False
    assert get_bot_type(ua) == "unknown"


def test_detects_firefox():
    """Test that Firefox is not detected as a bot."""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
    assert is_any_bot(ua) is False
    assert get_bot_type(ua) == "unknown"


def test_detects_safari():
    """Test that Safari is not detected as a bot."""
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    assert is_any_bot(ua) is False
    assert get_bot_type(ua) == "unknown"


def test_case_insensitive():
    """Test that bot detection is case-insensitive."""
    ua_upper = "MOZILLA/5.0 (COMPATIBLE; GPTBOT/1.0)"
    ua_lower = "mozilla/5.0 (compatible; gptbot/1.0)"
    ua_mixed = "MoZiLLa/5.0 (CoMpAtIbLe; GpTbOt/1.0)"

    assert is_ai_training_bot(ua_upper) is True
    assert is_ai_training_bot(ua_lower) is True
    assert is_ai_training_bot(ua_mixed) is True


def test_get_all_bot_lists():
    """Test that all bot lists are returned correctly."""
    bot_lists = get_all_bot_lists()

    assert "training" in bot_lists
    assert "search" in bot_lists
    assert "traditional" in bot_lists

    assert isinstance(bot_lists["training"], list)
    assert isinstance(bot_lists["search"], list)
    assert isinstance(bot_lists["traditional"], list)

    assert "gptbot" in bot_lists["training"]
    assert "claudebot" in bot_lists["search"]
    assert "googlebot" in bot_lists["traditional"]


def test_detects_ccbot():
    """Test detection of Common Crawl bot."""
    ua = "CCBot/2.0 (https://commoncrawl.org/faq/)"
    assert is_ai_training_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_detects_google_extended():
    """Test detection of Google Extended (Gemini training)."""
    ua = "Google-Extended"
    assert is_ai_training_bot(ua) is True
    assert get_bot_type(ua) == "training"


def test_empty_user_agent():
    """Test handling of empty user agent."""
    ua = ""
    assert is_any_bot(ua) is False
    assert get_bot_type(ua) == "unknown"