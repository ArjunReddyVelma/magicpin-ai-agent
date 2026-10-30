import uuid
from unittest.mock import MagicMock, patch
import pytest

from backend.app.ai.provider import (
    LLMResponse,
    LLMProviderError,
    LLMTimeoutError,
    LLMAuthenticationError,
    LLMRateLimitError,
)
from backend.app.ai.mock_provider import MockLLMProvider
from backend.app.ai.groq_provider import GroqProvider
from backend.app.ai.grok_provider import GrokProvider
from backend.app.core.dependencies import get_llm_provider
from backend.app.ai.prompt_builder import PromptBuilder
from backend.app.ai.response_validator import ResponseValidator
from backend.app.ai.context_retriever import ContextRetriever
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.context_item import ContextItem
from backend.app.models.message import Message
from backend.app.services.chat_service import ChatService


def test_mock_llm_provider_behavior():
    provider = MockLLMProvider(default_response="Mocked reply")
    resp = provider.generate_response(
        system_prompt="System rules",
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert resp.content == "Mocked reply"
    assert resp.provider == "mock"
    assert len(provider.calls) == 1

    # Canned queue
    provider.enqueue_response("Next reply")
    resp2 = provider.generate_response("Sys", [{"role": "user", "content": "Query"}])
    assert resp2.content == "Next reply"

    # Simulated error
    provider.set_should_raise(LLMTimeoutError("Simulated timeout"))
    with pytest.raises(LLMTimeoutError):
        provider.generate_response("Sys", [])


def test_prompt_builder_grounding_and_untrusted_boundary():
    builder = PromptBuilder()
    merchant = MerchantProfile(
        id=uuid.uuid4(),
        business_name="Spice Garden",
        category="Restaurant",
        location="Indiranagar, Bengaluru",
        timezone="Asia/Kolkata",
    )
    item1 = ContextItem(
        id=uuid.uuid4(),
        merchant_id=merchant.id,
        item_type="policy",
        title="Cancellation Policy",
        content="Orders can be cancelled within 5 minutes of placing.",
        version=1,
    )
    item2 = ContextItem(
        id=uuid.uuid4(),
        merchant_id=merchant.id,
        item_type="faq",
        title="Delivery Hours",
        content="We deliver from 11 AM to 11 PM daily.",
        version=2,
    )

    system_prompt = builder.build_system_prompt(merchant, [item1, item2])

    assert "Spice Garden" in system_prompt
    assert "Restaurant" in system_prompt
    assert "Orders can be cancelled within 5 minutes" in system_prompt
    assert "We deliver from 11 AM to 11 PM" in system_prompt
    assert "<merchant_context>" in system_prompt
    assert "NON-EXECUTABLE ACTIONS" in system_prompt
    assert "MISSING INFORMATION" in system_prompt

    # Test history payload
    m1 = Message(role="user", content="Hi", status="complete")
    m2 = Message(role="assistant", content="Hello!", status="complete")
    m_failed = Message(role="user", content="Bad", status="failed")

    payload = builder.build_messages_payload([m1, m2, m_failed], "What is the policy?")
    assert len(payload) == 3  # m1, m2, and current query
    assert payload[0] == {"role": "user", "content": "Hi"}
    assert payload[1] == {"role": "assistant", "content": "Hello!"}
    assert payload[2] == {"role": "user", "content": "What is the policy?"}


def test_response_validator_safeguards():
    validator = ResponseValidator()

    # Valid response
    cleaned, is_valid = validator.validate("Here is our refund policy details.")
    assert is_valid is True
    assert "Here is our refund policy details." in cleaned

    # Empty response
    _, is_valid_empty = validator.validate("   ")
    assert is_valid_empty is False

    # Forbidden execution claim
    claimed = "I have refunded 500 rupees to the customer's wallet."
    cleaned_claimed, is_valid_claimed = validator.validate(claimed)
    assert is_valid_claimed is True
    assert "Note: Suggested responses and drafts are for review only" in cleaned_claimed

    # Length boundary
    long_text = "A" * 5000
    cleaned_long, _ = validator.validate(long_text)
    assert len(cleaned_long) <= 4000


def test_groq_provider_missing_key():
    provider = GroqProvider(api_key="")
    with pytest.raises(LLMAuthenticationError):
        provider.generate_response("Sys", [{"role": "user", "content": "Hi"}])


@patch("httpx.Client")
def test_groq_provider_success(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "chatcmpl-123",
        "choices": [{"message": {"content": "This is a Groq response"}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20},
    }
    mock_client.post.return_value = mock_resp

    provider = GroqProvider(api_key="gsk_valid_key")
    res = provider.generate_response("System prompt", [{"role": "user", "content": "Hello"}])

    assert res.content == "This is a Groq response"
    assert res.provider == "groq"
    assert res.input_tokens == 50
    assert res.output_tokens == 20


@patch("httpx.Client")
def test_groq_provider_error_payload_extraction(mock_client_cls):
    """
    Regression test: Verifies that when Groq returns an HTTP 4xx error with a detailed JSON body
    (such as a 404 model_not_found error), the error message is preserved in LLMProviderError.
    """
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.json.return_value = {
        "error": {
            "message": "The model `llama-3.3-70b-versatile` does not exist or you do not have access to it.",
            "type": "invalid_request_error",
            "code": "model_not_found",
        }
    }
    mock_client.post.return_value = mock_resp

    provider = GroqProvider(api_key="gsk_valid_key", model="llama-3.3-70b-versatile")
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_response("System prompt", [{"role": "user", "content": "Hello"}])

    assert exc_info.value.status_code == 502
    assert exc_info.value.retryable is False
    assert "HTTP 404" in str(exc_info.value)
    assert "The model `llama-3.3-70b-versatile` does not exist" in str(exc_info.value)


def test_groq_provider_default_model_alignment():
    """
    Verifies that GroqProvider defaults to settings.LLM_MODEL ('openai/gpt-oss-120b').
    """
    provider = GroqProvider(api_key="gsk_test")
    assert provider.model == "openai/gpt-oss-120b"


def test_grok_provider_missing_key():
    provider = GrokProvider(api_key="")
    with pytest.raises(LLMAuthenticationError) as exc_info:
        provider.generate_response("Sys", [{"role": "user", "content": "Hi"}])
    assert "xAI Grok API key is missing" in str(exc_info.value)


@patch("httpx.Client")
def test_grok_provider_success(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "chatcmpl-grok-123",
        "choices": [{"message": {"content": "This is a Grok response"}}],
        "usage": {"prompt_tokens": 42, "completion_tokens": 18},
    }
    mock_client.post.return_value = mock_resp

    provider = GrokProvider(api_key="xai-valid-key")
    res = provider.generate_response("System prompt", [{"role": "user", "content": "Hello"}])

    assert res.content == "This is a Grok response"
    assert res.provider == "grok"
    assert res.model == "grok-2-latest"
    assert res.input_tokens == 42
    assert res.output_tokens == 18
    assert res.raw_metadata == {"xai_id": "chatcmpl-grok-123"}


@patch("httpx.Client")
def test_grok_provider_error_payload_extraction(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.json.return_value = {
        "error": {
            "message": "The model `grok-invalid` does not exist.",
            "type": "invalid_request_error",
        }
    }
    mock_client.post.return_value = mock_resp

    provider = GrokProvider(api_key="xai-valid-key", model="grok-invalid")
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_response("System prompt", [{"role": "user", "content": "Hello"}])

    assert exc_info.value.status_code == 502
    assert exc_info.value.retryable is False
    assert "HTTP 404" in str(exc_info.value)
    assert "The model `grok-invalid` does not exist" in str(exc_info.value)


@patch("httpx.Client")
def test_grok_provider_auth_error(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_client.post.return_value = mock_resp

    provider = GrokProvider(api_key="xai-invalid-key")
    with pytest.raises(LLMAuthenticationError) as exc_info:
        provider.generate_response("System prompt", [{"role": "user", "content": "Hello"}])
    assert "authentication failed" in str(exc_info.value)


@patch("httpx.Client")
def test_grok_provider_rate_limit_error(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_client.post.return_value = mock_resp

    provider = GrokProvider(api_key="xai-valid-key")
    with pytest.raises(LLMRateLimitError) as exc_info:
        provider.generate_response("System prompt", [{"role": "user", "content": "Hello"}])
    assert "rate limit exceeded" in str(exc_info.value)


def test_grok_provider_default_model_alignment():
    provider = GrokProvider(api_key="xai-test")
    assert provider.model == "grok-2-latest"


def test_get_llm_provider_resolves_grok(monkeypatch):
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "grok")
    provider = get_llm_provider()
    assert isinstance(provider, GrokProvider)
    assert provider.provider_name == "grok"


def test_chat_service_draft_eligibility_classification():
    """
    Verifies conservative and deterministic draft eligibility for customer support turns.
    """
    valid_assistant_reply = "Dear customer, we apologize for the issue and will replace your item promptly."
    error_fallback = "I apologize, but I could not generate a response. Please check your context items."

    # Qualifying customer-support requests
    assert ChatService._is_draft_eligible(
        "A customer received a damaged product. What should we tell them?",
        valid_assistant_reply,
    ) is True
    assert ChatService._is_draft_eligible(
        "A customer's food was cold; write a message to them.",
        valid_assistant_reply,
    ) is True
    assert ChatService._is_draft_eligible(
        "A customer's order is late. Draft a reply using our policy.",
        valid_assistant_reply,
    ) is True

    # Informational or non-drafting queries must NOT qualify
    assert ChatService._is_draft_eligible(
        "What are our delivery hours?",
        valid_assistant_reply,
    ) is False
    assert ChatService._is_draft_eligible(
        "A customer is asking for our return policy details.",
        valid_assistant_reply,
    ) is False
    assert ChatService._is_draft_eligible(
        "Our customer orders had typos so we had to rewrite them.",
        valid_assistant_reply,
    ) is False
    assert ChatService._is_draft_eligible(
        "Hello, how does the AI assistant work?",
        valid_assistant_reply,
    ) is False

    # Short user content or error assistant content must NOT qualify
    assert ChatService._is_draft_eligible(
        "Hi",
        valid_assistant_reply,
    ) is False
    assert ChatService._is_draft_eligible(
        "A customer received a damaged product. What should we tell them?",
        error_fallback,
    ) is False
