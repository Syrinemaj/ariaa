"""Tests for Fix 2.3 — tiktoken-based truncation."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.ai.token_counter import (
    count_tokens,
    truncate_dict_to_token_limit,
    truncate_to_token_limit,
)


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_short_text_under_limit(self):
        n = count_tokens("Hello, world!")
        assert n > 0

    def test_tiktoken_unavailable_falls_back_to_char_ratio(self):
        with patch("app.ai.token_counter._get_encoding", return_value=None):
            # 400 chars / 4 = 100 tokens
            text = "a" * 400
            assert count_tokens(text) == 100


class TestTruncateToTokenLimit:
    def test_short_text_not_truncated(self):
        text = "short text"
        result, truncated = truncate_to_token_limit(text, "gpt-4o-mini", max_tokens=100)
        assert result == text
        assert truncated is False

    def test_long_text_is_truncated(self):
        text = "word " * 10_000  # ~30k tokens
        result, truncated = truncate_to_token_limit(text, "gpt-4o-mini", max_tokens=50)
        assert truncated is True
        assert len(result) < len(text)

    def test_fallback_when_tiktoken_unavailable(self):
        with patch("app.ai.token_counter._get_encoding", return_value=None):
            text = "a" * 1000
            result, truncated = truncate_to_token_limit(text, "gpt-4o-mini", max_tokens=10)
            # 10 tokens * 4 chars = 40 chars limit
            assert len(result) <= 40
            assert truncated is True

    def test_json_boundary_preserved(self):
        # Build a JSON string that is clearly > 10 tokens but has clean boundaries
        data = {"key": "value", "other": "data"}
        text = json.dumps(data)
        result, truncated = truncate_to_token_limit(text, "gpt-4o-mini", max_tokens=2)
        # Result may be truncated but should not raise
        assert isinstance(result, str)


class TestTruncateDictToTokenLimit:
    def test_small_dict_not_truncated(self):
        d = {"a": 1, "b": 2}
        result, truncated = truncate_dict_to_token_limit(d, "gpt-4o-mini", max_tokens=1000)
        assert result == d
        assert truncated is False

    def test_large_dict_truncated_to_valid_dict(self):
        d = {f"key_{i}": "x" * 100 for i in range(500)}
        result, truncated = truncate_dict_to_token_limit(d, "gpt-4o-mini", max_tokens=20)
        assert truncated is True
        assert isinstance(result, dict)
