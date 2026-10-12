from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    raw_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    def __init__(self, message: str, status_code: int = 502, retryable: bool = True):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


class LLMTimeoutError(LLMProviderError):
    """Raised when an LLM provider request times out."""
    def __init__(self, message: str = "LLM request timed out"):
        super().__init__(message, status_code=504, retryable=True)


class LLMAuthenticationError(LLMProviderError):
    """Raised when LLM provider authentication fails (e.g. invalid API key)."""
    def __init__(self, message: str = "LLM provider authentication failed"):
        super().__init__(message, status_code=502, retryable=False)


class LLMRateLimitError(LLMProviderError):
    """Raised when LLM provider rate limits are exceeded."""
    def __init__(self, message: str = "LLM provider rate limit exceeded"):
        super().__init__(message, status_code=429, retryable=True)


class LLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Generates a completion response from the model.
        
        Args:
            system_prompt: Grounding system prompt with merchant context.
            messages: Bounded conversation history list of role/content dicts.
            max_tokens: Maximum tokens in generated completion.
            temperature: Sampling temperature.
            
        Returns:
            LLMResponse containing generated text and usage metrics.
        """
        pass
