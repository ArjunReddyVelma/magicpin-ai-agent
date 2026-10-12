import re
from typing import Tuple


class ResponseValidator:
    """
    Validates model outputs, enforces maximum response length,
    and guards against unauthorized external action claims.
    """

    MAX_RESPONSE_LENGTH = 4000

    FORBIDDEN_EXECUTION_PATTERNS = [
        re.compile(r"\b(i\s+have\s+(sent|dispatched|issued|refunded|charged))\b", re.IGNORECASE),
        re.compile(r"\b(message\s+has\s+been\s+sent)\b", re.IGNORECASE),
        re.compile(r"\b(refund\s+has\s+been\s+processed)\b", re.IGNORECASE),
    ]

    DISCLAIMER = "\n\n*(Note: Suggested responses and drafts are for review only; no external messages or transactions are performed automatically.)*"

    def validate(self, text: str) -> Tuple[str, bool]:
        """
        Validates generated response.
        Returns:
            (sanitized_text, is_valid)
        """
        if not text or not text.strip():
            return "I apologize, but I could not generate a response. Please rephrase or try again.", False

        cleaned = text.strip().replace("\x00", "")

        # Enforce max length
        if len(cleaned) > self.MAX_RESPONSE_LENGTH:
            cleaned = cleaned[: self.MAX_RESPONSE_LENGTH]

        # Check for claims of external execution
        has_forbidden_claim = any(
            pattern.search(cleaned) for pattern in self.FORBIDDEN_EXECUTION_PATTERNS
        )
        if has_forbidden_claim and self.DISCLAIMER not in cleaned:
            cleaned += self.DISCLAIMER

        return cleaned, True
