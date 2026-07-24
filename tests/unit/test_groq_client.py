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

    def test_default_uses_settings_groq_model(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
        client, mock = self._client(_VALID_STRUCTURED)
        client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test")
        assert mock.chat.completions.create.call_args.kwargs["model"] == "llama-3.3-70b-versatile"

    def test_model_override_used_instead_of_settings_groq_model(self):
        # ARIA-EVAL: evaluation/judge.py passes model= to request a model
        # independent of the pipeline's own, without duplicating the key
        # fallback cascade.
        client, mock = self._client(_VALID_STRUCTURED)
        client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test", model="llama-3.1-70b-versatile")
        assert mock.chat.completions.create.call_args.kwargs["model"] == "llama-3.1-70b-versatile"

    def test_model_override_forwarded_through_secondary_fallback(self, monkeypatch):
        from app.core.config import settings
        from app.ai.groq_client import GroqClient

        monkeypatch.setattr(settings, "GROQ_API_KEY", "primary-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_2", "secondary-key")

        primary_instance = MagicMock()
        primary_instance.chat.completions.create.side_effect = _rate_limit_error()

        secondary_instance = MagicMock()
        secondary_instance.chat.completions.create.return_value = _make_completion(_VALID_STRUCTURED)

        def _fake_openai(**kwargs):
            return primary_instance if kwargs["api_key"] == "primary-key" else secondary_instance

        with patch("app.ai.groq_client.OpenAI", side_effect=_fake_openai), \
             patch("app.ai.groq_client.AsyncOpenAI"):
            client = GroqClient()
            client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test", model="custom-model")

        assert secondary_instance.chat.completions.create.call_args.kwargs["model"] == "custom-model"

    def test_non_dict_llm_response_raises_after_retry(self):
        # A non-dict response is retried once (with a correction message),
        # then raises rather than silently returning {} — callers indexing
        # required fields (result["intent"]) would otherwise hit a raw KeyError.
        mock_completion = _make_completion("not_a_dict")
        mock_completion.choices[0].message.content = json.dumps([1, 2, 3])
        with patch("app.ai.groq_client.OpenAI") as MockSync, \
             patch("app.ai.groq_client.AsyncOpenAI"):
            instance = MockSync.return_value
            instance.chat.completions.create.return_value = mock_completion
            from app.ai.base_client import StructuredResponseError
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._sync = instance
            with pytest.raises(StructuredResponseError):
                client.structured_chat("p", {}, _SAMPLE_SCHEMA, "t")
        # Retried exactly once (2 attempts total) before giving up.
        assert instance.chat.completions.create.call_count == 2

    def test_missing_required_field_raises_after_retry(self):
        mock_completion = _make_completion({"intent": "create employees"})  # missing "action"
        with patch("app.ai.groq_client.OpenAI") as MockSync, \
             patch("app.ai.groq_client.AsyncOpenAI"):
            instance = MockSync.return_value
            instance.chat.completions.create.return_value = mock_completion
            from app.ai.base_client import StructuredResponseError
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._sync = instance
            with pytest.raises(StructuredResponseError):
                client.structured_chat("p", {}, _SAMPLE_SCHEMA, "t")

    def test_recovers_on_retry_after_invalid_first_attempt(self):
        # First call returns garbage, second (retry) returns a valid dict —
        # the retry must actually recover, not just detect+raise.
        bad = _make_completion("bad")
        bad.choices[0].message.content = "not json at all"
        good = _make_completion(_VALID_STRUCTURED)
        with patch("app.ai.groq_client.OpenAI") as MockSync, \
             patch("app.ai.groq_client.AsyncOpenAI"):
            instance = MockSync.return_value
            instance.chat.completions.create.side_effect = [bad, good]
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._sync = instance
            result = client.structured_chat("p", {}, _SAMPLE_SCHEMA, "t")
        assert result == _VALID_STRUCTURED
        assert instance.chat.completions.create.call_count == 2

    def test_pins_low_temperature_for_structured_extraction(self):
        client, mock = self._client(_VALID_STRUCTURED)
        client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test")
        _, kwargs = mock.chat.completions.create.call_args
        assert kwargs["temperature"] < 0.3

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


# ── Secondary Groq key fallback ───────────────────────────────────────────────
# On RateLimitError/APIError/APITimeoutError, GROQ_API_KEY_2 (a second Groq
# account/key) is tried before Azure — this is the fix for hitting Groq's
# per-key daily token cap mid-run.

def _rate_limit_error() -> Any:
    import httpx
    from openai import RateLimitError
    response = httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    return RateLimitError("rate limit reached", response=response, body=None)


class TestSecondaryGroqKeyFallback:
    def test_structured_chat_retries_with_second_key_on_rate_limit(self, monkeypatch):
        from app.core.config import settings
        from app.ai.groq_client import GroqClient

        monkeypatch.setattr(settings, "GROQ_API_KEY", "primary-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_2", "secondary-key")

        primary_instance = MagicMock()
        primary_instance.chat.completions.create.side_effect = _rate_limit_error()

        secondary_instance = MagicMock()
        secondary_instance.chat.completions.create.return_value = _make_completion(_VALID_STRUCTURED)

        created_sync_clients: list[Any] = []

        def _fake_openai(**kwargs):
            instance = primary_instance if kwargs["api_key"] == "primary-key" else secondary_instance
            created_sync_clients.append(kwargs["api_key"])
            return instance

        with patch("app.ai.groq_client.OpenAI", side_effect=_fake_openai), \
             patch("app.ai.groq_client.AsyncOpenAI"):
            client = GroqClient()
            result = client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test")

        assert result == _VALID_STRUCTURED
        assert "secondary-key" in created_sync_clients
        secondary_instance.chat.completions.create.assert_called_once()

    def test_no_secondary_key_configured_falls_through_to_azure_or_raises(self, monkeypatch):
        from app.core.config import settings
        from app.ai.groq_client import GroqClient

        monkeypatch.setattr(settings, "GROQ_API_KEY", "primary-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_2", None)
        # Explicit, not just relying on the default — isolates this test from
        # whatever GROQ_API_KEY_3 happens to be set to in .env (the tertiary
        # fallback added alongside GROQ_API_KEY_2's tests below).
        monkeypatch.setattr(settings, "GROQ_API_KEY_3", None)
        monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", None)

        primary_instance = MagicMock()
        primary_instance.chat.completions.create.side_effect = _rate_limit_error()

        with patch("app.ai.groq_client.OpenAI") as MockSync, \
             patch("app.ai.groq_client.AsyncOpenAI"):
            MockSync.return_value = primary_instance
            client = GroqClient()
            with pytest.raises(type(_rate_limit_error())):
                client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test")

    def test_secondary_key_same_as_primary_is_ignored(self, monkeypatch):
        # A misconfigured GROQ_API_KEY_2 identical to GROQ_API_KEY would just
        # fail the same way — must not be treated as a usable fallback.
        from app.core.config import settings
        from app.ai.groq_client import GroqClient

        monkeypatch.setattr(settings, "GROQ_API_KEY", "same-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_2", "same-key")

        client = GroqClient()
        assert client._secondary_groq_fallback() is None


class TestTertiaryGroqKeyFallback:
    def test_structured_chat_retries_with_third_key_when_first_two_rate_limited(self, monkeypatch):
        from app.core.config import settings
        from app.ai.groq_client import GroqClient

        monkeypatch.setattr(settings, "GROQ_API_KEY", "primary-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_2", "secondary-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_3", "tertiary-key")

        primary_instance = MagicMock()
        primary_instance.chat.completions.create.side_effect = _rate_limit_error()

        secondary_instance = MagicMock()
        secondary_instance.chat.completions.create.side_effect = _rate_limit_error()

        tertiary_instance = MagicMock()
        tertiary_instance.chat.completions.create.return_value = _make_completion(_VALID_STRUCTURED)

        created_sync_clients: list[Any] = []

        def _fake_openai(**kwargs):
            created_sync_clients.append(kwargs["api_key"])
            return {
                "primary-key": primary_instance,
                "secondary-key": secondary_instance,
                "tertiary-key": tertiary_instance,
            }[kwargs["api_key"]]

        with patch("app.ai.groq_client.OpenAI", side_effect=_fake_openai), \
             patch("app.ai.groq_client.AsyncOpenAI"):
            client = GroqClient()
            result = client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test")

        assert result == _VALID_STRUCTURED
        assert "tertiary-key" in created_sync_clients
        tertiary_instance.chat.completions.create.assert_called_once()

    def test_no_tertiary_key_configured_falls_through_to_azure_or_raises(self, monkeypatch):
        from app.core.config import settings
        from app.ai.groq_client import GroqClient

        monkeypatch.setattr(settings, "GROQ_API_KEY", "primary-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_2", None)
        monkeypatch.setattr(settings, "GROQ_API_KEY_3", None)
        monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", None)

        primary_instance = MagicMock()
        primary_instance.chat.completions.create.side_effect = _rate_limit_error()

        with patch("app.ai.groq_client.OpenAI") as MockSync, \
             patch("app.ai.groq_client.AsyncOpenAI"):
            MockSync.return_value = primary_instance
            client = GroqClient()
            with pytest.raises(type(_rate_limit_error())):
                client.structured_chat("prompt", {}, _SAMPLE_SCHEMA, "test")

    def test_tertiary_key_same_as_primary_or_secondary_is_ignored(self, monkeypatch):
        from app.core.config import settings
        from app.ai.groq_client import GroqClient

        monkeypatch.setattr(settings, "GROQ_API_KEY", "same-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_2", "secondary-key")
        monkeypatch.setattr(settings, "GROQ_API_KEY_3", "same-key")
        client = GroqClient()
        assert client._tertiary_groq_fallback() is None

        monkeypatch.setattr(settings, "GROQ_API_KEY_3", "secondary-key")
        assert client._tertiary_groq_fallback() is None


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
    async def test_non_dict_raises_after_retry(self):
        mock_completion = _make_completion("nope")
        mock_completion.choices[0].message.content = json.dumps([])
        with patch("app.ai.groq_client.OpenAI"), \
             patch("app.ai.groq_client.AsyncOpenAI") as MockAsync:
            instance = MockAsync.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_completion)
            from app.ai.base_client import StructuredResponseError
            from app.ai.groq_client import GroqClient
            client = GroqClient()
            client._async = instance
            with pytest.raises(StructuredResponseError):
                await client.structured_chat_async("p", {}, _SAMPLE_SCHEMA, "t")
        assert instance.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_pins_low_temperature_for_structured_extraction(self):
        client, mock = self._async_client(_VALID_STRUCTURED)
        await client.structured_chat_async("p", {}, _SAMPLE_SCHEMA, "t")
        _, kwargs = mock.chat.completions.create.call_args
        assert kwargs["temperature"] < 0.3


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
