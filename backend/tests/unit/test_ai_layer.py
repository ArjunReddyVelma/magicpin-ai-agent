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
from backend.app.ai.prompt_builder import PromptBuilder
from backend.app.ai.response_validator import ResponseValidator
from backend.app.ai.context_retriever import ContextRetriever
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.context_item import ContextItem
from backend.app.models.message import Message


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
