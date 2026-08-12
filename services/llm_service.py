from openai import OpenAI

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    LLM_TIMEOUT_SECONDS,
)


class LLMService:
    """
    Handles communication with the Groq API.
    """

    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is missing."
            )

        self.client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=LLM_TIMEOUT_SECONDS,
        )

    def generate(self, messages):
        response = self.client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.7,
        )

        return response.choices[0].message.content