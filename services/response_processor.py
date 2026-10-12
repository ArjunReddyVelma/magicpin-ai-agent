class ResponseProcessor:
    """
    Post-processes LLM responses before sending them to clients.
    """

    def process(self, response: str) -> str:
        return response.strip()