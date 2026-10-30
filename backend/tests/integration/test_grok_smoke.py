import os
import pytest

from backend.app.ai.grok_provider import GrokProvider
from backend.app.core.config import settings


@pytest.mark.skipif(
    os.getenv("RUN_GROK_SMOKE") != "1",
    reason="Opt-in live Grok smoke test. Set RUN_GROK_SMOKE=1 to execute against live xAI API.",
)
def test_live_grok_smoke():
    """
    Opt-in live smoke test verifying real xAI Grok API connectivity and completions.
    Only executed when RUN_GROK_SMOKE=1 is explicitly set by the operator.
    Never exposes API keys or authorization headers in test output.
    """
    api_key = (
        os.getenv("XAI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or getattr(settings, "XAI_API_KEY", "")
        or settings.LLM_API_KEY
    )
    if not api_key or not api_key.strip():
        pytest.fail("RUN_GROK_SMOKE=1 was requested, but neither XAI_API_KEY nor LLM_API_KEY is configured.")

    model = os.getenv("XAI_MODEL") or os.getenv("LLM_MODEL") or getattr(settings, "XAI_MODEL", "grok-2-latest")
    provider = GrokProvider(api_key=api_key, model=model, timeout_seconds=20, max_retries=1)
    response = provider.generate_response(
        system_prompt="You are a helpful customer support assistant. Reply concisely in one word.",
        messages=[{"role": "user", "content": "Ping"}],
        max_tokens=100,
    )

    assert response is not None
    assert response.provider == "grok"
    assert response.content is not None
    assert len(response.content.strip()) > 0
