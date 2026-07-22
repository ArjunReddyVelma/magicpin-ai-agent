from openai import OpenAI

from config import GROQ_API_KEY


class LLMService:
    """
    Handles communication with the Groq API.
    """

    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is missing. Check your .env file."
            )

        self.client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    def generate(self, messages):

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
        )

        return response.choices[0].message.content