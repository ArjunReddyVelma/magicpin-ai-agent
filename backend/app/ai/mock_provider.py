from typing import Optional, List, Dict, Any
from backend.app.ai.provider import (
    LLMProvider,
    LLMResponse,
    LLMProviderError,
    LLMTimeoutError,
)


class MockLLMProvider(LLMProvider):
    """
    Controllable in-memory LLM provider for unit, integration,
    and failure-path testing without network access or live API keys.
    """

    def __init__(
        self,
        default_response: str = "This is a grounded response based on your merchant context.",
        model: str = "mock-llama-3.3-70b",
    ):
        self.default_response = default_response
        self.model = model
        self.provider_name = "mock"
        self.should_raise: Optional[Exception] = None
        self.calls: List[Dict[str, Any]] = []
        self.canned_responses: List[str] = []

    def set_should_raise(self, exc: Optional[Exception]) -> None:
        self.should_raise = exc

    def enqueue_response(self, text: str) -> None:
        self.canned_responses.append(text)

    def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.calls.append({
            "system_prompt": system_prompt,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })

        if self.should_raise is not None:
            raise self.should_raise

        if self.canned_responses:
            content = self.canned_responses.pop(0)
        else:
            content = self.default_response

        return LLMResponse(
            content=content,
            provider=self.provider_name,
            model=self.model,
            input_tokens=len(system_prompt) // 4 + sum(len(m.get("content", "")) // 4 for m in messages),
            output_tokens=len(content) // 4,
            raw_metadata={"mock": True, "call_index": len(self.calls)},
        )
