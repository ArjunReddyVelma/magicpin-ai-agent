import time
from typing import Optional, List, Dict, Any
import httpx

from backend.app.ai.provider import (
    LLMProvider,
    LLMResponse,
    LLMProviderError,
    LLMTimeoutError,
    LLMAuthenticationError,
    LLMRateLimitError,
)
from backend.app.core.config import settings
from backend.app.core.logging import logger


class GroqProvider(LLMProvider):
    """
    Groq API provider adapter implementing the LLMProvider interface.
    Calls Groq's OpenAI-compatible chat completions endpoint with bounded retries,
    timeouts, and strict error translation.
    """

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        self.api_key = (api_key if api_key is not None else settings.LLM_API_KEY).strip()
        self.model = model or settings.LLM_MODEL
        self.timeout_seconds = timeout_seconds or settings.LLM_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else settings.LLM_MAX_RETRIES
        self.provider_name = "groq"

    def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        if not self.api_key:
            raise LLMAuthenticationError(
                "Groq API key is missing or not configured. Set LLM_API_KEY (or GROQ_API_KEY) in your environment."
            )

        payload_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            payload_messages.append({
                "role": m.get("role", "user"),
                "content": m.get("content", ""),
            })

        payload = {
            "model": self.model,
            "messages": payload_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        url = f"{self.BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "magicpin-ai-agent/1.0",
        }

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=float(self.timeout_seconds)) as client:
                    response = client.post(url, json=payload, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise LLMProviderError("Groq returned empty choices in completion response")

                    message_obj = choices[0].get("message", {})
                    content = message_obj.get("content", "")
                    usage = data.get("usage", {})

                    return LLMResponse(
                        content=content,
                        provider=self.provider_name,
                        model=self.model,
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                        raw_metadata={"groq_id": data.get("id")},
                    )

                if response.status_code == 401:
                    raise LLMAuthenticationError("Groq authentication failed: invalid API key")
                elif response.status_code == 429:
                    raise LLMRateLimitError("Groq rate limit exceeded. Please retry later.")
                elif 500 <= response.status_code < 600:
                    last_error = LLMProviderError(
                        f"Groq upstream server error: HTTP {response.status_code}",
                        status_code=502,
                        retryable=True,
                    )
                else:
                    error_detail = ""
                    try:
                        err_json = response.json()
                        if isinstance(err_json, dict) and "error" in err_json:
                            err_info = err_json["error"]
                            if isinstance(err_info, dict):
                                error_detail = err_info.get("message") or str(err_info)
                            else:
                                error_detail = str(err_info)
                    except Exception:
                        error_detail = response.text[:200] if response.text else ""

                    msg = (
                        f"Groq API call failed: HTTP {response.status_code} - {error_detail}"
                        if error_detail
                        else f"Groq API call failed: HTTP {response.status_code}"
                    )
                    raise LLMProviderError(
                        msg,
                        status_code=502,
                        retryable=False,
                    )

            except httpx.TimeoutException as exc:
                last_error = LLMTimeoutError(f"Groq API timed out after {self.timeout_seconds}s")
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = LLMProviderError(f"Network error connecting to Groq: {str(exc)}", status_code=502)
            except (LLMAuthenticationError, LLMRateLimitError):
                raise
            except Exception as exc:
                last_error = exc

            # Backoff before retrying transient error
            if attempt < self.max_retries:
                time.sleep(0.5 * (2 ** attempt))

        # Exhausted retries
        if isinstance(last_error, LLMProviderError):
            raise last_error
        raise LLMProviderError(f"Groq completion failed: {last_error}")
