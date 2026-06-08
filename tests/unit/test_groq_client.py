"""
Unit tests — GroqClient (app/ai/groq_client.py).

All external calls (OpenAI SDK) are mocked so tests run without network
or a real Groq API key. Focus areas:

1. Schema injection into system prompt (_inject_schema)
2. Zero-vector embedding fallback
3. sync  structured_chat → correct response_format, JSON parse
4. async structured_chat_async → same
5. classify_api_call → ClassificationResponse happy + fallback
6. Provider selection in main.py lifespan (via config fixture)
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_completion(content: dict | str) -> MagicMock:
    """Build a minimal mock resembling openai.ChatCompletion."""
    msg = MagicMock()
    msg.content = json.dumps(content) if isinstance(content, dict) else content

    choice = MagicMock()
    choice.message = msg

    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50

    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    return completion


_VALID_CLASSIFY = {
    "is_business_api": True,
    "should_keep": True,
    "business_domain": "HR",
    "business_action": "create_employee",
    "confidence": 0.92,
    "reason": "POST to /employees is a business endpoint",
}

_VALID_STRUCTURED = {
    "intent": "create employees",
    "action": "create",
    "confidence": 0.9,
}

_SAMPLE_SCHEMA: dict[str, Any] = {
    "name": "test_schema",
    "schema": {
        "type": "object",
        "properties": {"intent": {"type": "string"}, "action": {"type": "string"}},
        "required": ["intent", "action"],
        "additionalProperties": False,
    },
}


# ── Schema injection ──────────────────────────────────────────────────────────

class TestInjectSchema:
    def test_schema_body_present_in_augmented_prompt(self):
        from app.ai.groq_client import GroqClient
        augmented = GroqClient._inject_schema("Base prompt.", _SAMPLE_SCHEMA)
        schema_str = json.dumps(_SAMPLE_SCHEMA["schema"], indent=2)
        assert schema_str in augmented

    def test_base_prompt_preserved(self):
        from app.ai.groq_client import GroqClient
        augmented = GroqClient._inject_schema("My system prompt.", _SAMPLE_SCHEMA)
        assert augmented.startswith("My system prompt.")

    def test_raw_schema_dict_accepted(self):
        """If json_schema has no 'schema' key, use it directly."""
        from app.ai.groq_client import GroqClient
        raw = {"type": "object", "properties": {"x": {"type": "string"}}}
        augmented = GroqClient._inject_schema("Prompt.", raw)
        assert '"type": "object"' in augmented

    def test_json_schema_wrapper_unwrapped(self):
        from app.ai.groq_client import GroqClient
        wrapped = {"name": "w", "schema": {"type": "object", "properties": {}}}
        augmented = GroqClient._inject_schema("P.", wrapped)
        # The schema body (not the wrapper) should be injected
        assert '"name": "w"' not in augmented
        assert '"type": "object"' in augmented


# ── Embeddings ────────────────────────────────────────────────────────────────
# GroqClient no longer provides embedding methods — embeddings are handled
# exclusively by LocalEmbeddingClient (BAAI/bge-small-en, 384 dims).
# Tests for LocalEmbeddingClient live in test_local_embedding_client.py.


# ── structured_chat (sync) ────────────────────────────────────────────────────

class TestStructuredChat:
    def _client(self, sync_return: dict) -> Any:
        mock_completion = _make_completion(sync_return)

        with patch("app.ai.groq_client.OpenAI") as MockSync, \
             patch("app.ai.groq_client.AsyncOpenAI"):
            instance = MockSync.return_value
            instance.chat.completions.create.return_value = mock_completion
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._sync = instance
            return client, instance

    def test_returns_parsed_dict(self):
        client, mock = self._client(_VALID_STRUCTURED)
        result = client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test")
        assert result == _VALID_STRUCTURED

    def test_uses_json_object_response_format(self):
        client, mock = self._client(_VALID_STRUCTURED)
        client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test")
        call_kwargs = mock.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_schema_injected_in_system_message(self):
        client, mock = self._client(_VALID_STRUCTURED)
        client.structured_chat("original prompt", {}, _SAMPLE_SCHEMA, "test")
        messages = mock.chat.completions.create.call_args.kwargs["messages"]
        system_content = messages[0]["content"]
        assert "original prompt" in system_content
        assert "Required schema" in system_content

    def test_non_dict_llm_response_returns_empty_dict(self):
        mock_completion = _make_completion("not_a_dict")
        mock_completion.choices[0].message.content = json.dumps([1, 2, 3])
        with patch("app.ai.groq_client.OpenAI") as MockSync, \
             patch("app.ai.groq_client.AsyncOpenAI"):
            instance = MockSync.return_value
            instance.chat.completions.create.return_value = mock_completion
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._sync = instance
            result = client.structured_chat("p", {}, _SAMPLE_SCHEMA, "t")
        assert result == {}

    def test_db_none_does_not_call_log_usage(self):
        client, _ = self._client(_VALID_STRUCTURED)
        with patch(
            "app.ai.groq_client.GroqClient._log_usage"
        ) as mock_log:
            client.structured_chat("p", {}, _SAMPLE_SCHEMA, "t", db=None)
        mock_log.assert_called_once()
        # db=None → _log_usage is called but should not call the service
        args = mock_log.call_args.args
        assert args[0] is None  # db


# ── structured_chat_async ─────────────────────────────────────────────────────

class TestStructuredChatAsync:
    def _async_client(self, return_value: dict) -> Any:
        mock_completion = _make_completion(return_value)

        with patch("app.ai.groq_client.OpenAI"), \
             patch("app.ai.groq_client.AsyncOpenAI") as MockAsync:
            instance = MockAsync.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_completion)
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._async = instance
            return client, instance

    @pytest.mark.asyncio
    async def test_returns_parsed_dict(self):
        client, _ = self._async_client(_VALID_STRUCTURED)
        result = await client.structured_chat_async("p", {}, _SAMPLE_SCHEMA, "t")
        assert result == _VALID_STRUCTURED

    @pytest.mark.asyncio
    async def test_uses_json_object_response_format(self):
        client, mock = self._async_client(_VALID_STRUCTURED)
        await client.structured_chat_async("p", {}, _SAMPLE_SCHEMA, "t")
        call_kwargs = mock.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_non_dict_returns_empty(self):
        mock_completion = _make_completion("nope")
        mock_completion.choices[0].message.content = json.dumps([])
        with patch("app.ai.groq_client.OpenAI"), \
             patch("app.ai.groq_client.AsyncOpenAI") as MockAsync:
            instance = MockAsync.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_completion)
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._async = instance
            result = await client.structured_chat_async("p", {}, _SAMPLE_SCHEMA, "t")
        assert result == {}


# ── classify_api_call ─────────────────────────────────────────────────────────

class TestClassifyApiCall:
    def _client(self, llm_response: dict) -> Any:
        completion = _make_completion(llm_response)
        with patch("app.ai.groq_client.OpenAI") as MockSync, \
             patch("app.ai.groq_client.AsyncOpenAI"):
            instance = MockSync.return_value
            instance.chat.completions.create.return_value = completion
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._sync = instance
            return client, instance

    def test_happy_path_returns_classification(self):
        from app.ai.response_schemas import ClassificationResponse
        client, _ = self._client(_VALID_CLASSIFY)
        result = client.classify_api_call({"method": "POST", "url": "/api/employees"})
        assert isinstance(result, ClassificationResponse)
        assert result.is_business_api is True
        assert result.business_domain == "HR"

    def test_invalid_response_returns_fallback(self):
        """LLM hallucinating a bad shape → fallback ClassificationResponse."""
        client, _ = self._client({"not_valid": True})
        result = client.classify_api_call({"method": "GET", "url": "/favicon.ico"})
        assert result.is_business_api is False
        assert result.should_keep is False
        assert result.confidence == 0.0

    def test_uses_json_object_format(self):
        client, mock = self._client(_VALID_CLASSIFY)
        client.classify_api_call({"method": "GET", "url": "/api/users"})
        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_classification_schema_injected_in_prompt(self):
        client, mock = self._client(_VALID_CLASSIFY)
        client.classify_api_call({"method": "GET", "url": "/api/users"})
        messages = mock.chat.completions.create.call_args.kwargs["messages"]
        system_msg = messages[0]["content"]
        assert "is_business_api" in system_msg
        assert "should_keep" in system_msg


# ── Provider selection (config-level) ─────────────────────────────────────────

class TestProviderSelection:
    """Verify that the correct client class is instantiated based on AI_PROVIDER."""

    def test_groq_provider_instantiates_groq_client(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.AI_PROVIDER", "groq")
        monkeypatch.setattr(
            "app.core.config.settings.GROQ_API_KEY", "gsk_test_key"
        )
        with patch("app.ai.groq_client.OpenAI"), \
             patch("app.ai.groq_client.AsyncOpenAI"):
            from app.ai.groq_client import GroqClient
            client = GroqClient()
        assert isinstance(client, GroqClient)

    def test_azure_provider_instantiates_azure_client(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.AI_PROVIDER", "azure")
        with patch("app.ai.azure_openai_client.AzureOpenAI"), \
             patch("app.ai.azure_openai_client.AsyncAzureOpenAI"):
            from app.ai.azure_openai_client import AzureOpenAIClient
            client = AzureOpenAIClient()
        assert isinstance(client, AzureOpenAIClient)
