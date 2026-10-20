import os
import pytest

from backend.app.ai.groq_provider import GroqProvider
from backend.app.core.config import settings


@pytest.mark.skipif(
    os.getenv("RUN_GROQ_SMOKE") != "1",
    reason="Opt-in live Groq smoke test. Set RUN_GROQ_SMOKE=1 to execute against live API.",
)
def test_live_groq_smoke():
    """
    Opt-in live smoke test verifying real Groq API connectivity and completions.
    Only executed when RUN_GROQ_SMOKE=1 is explicitly set by the operator.
    Never exposes API keys or authorization headers in test output.
    """
    api_key = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or settings.LLM_API_KEY
    if not api_key or not api_key.strip():
        pytest.fail("RUN_GROQ_SMOKE=1 was requested, but neither LLM_API_KEY nor GROQ_API_KEY is configured.")

    model = os.getenv("LLM_MODEL") or settings.LLM_MODEL
    provider = GroqProvider(api_key=api_key, model=model, timeout_seconds=20, max_retries=1)
    response = provider.generate_response(
        system_prompt="You are a helpful customer support assistant. Reply concisely in one word.",
        messages=[{"role": "user", "content": "Ping"}],
        max_tokens=100,
    )

    assert response is not None
    assert response.provider == "groq"
    assert response.content is not None
    assert len(response.content.strip()) > 0
