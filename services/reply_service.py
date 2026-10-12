from email import message
import re

from services.llm_service import LLMService
from services.memory_manager import MemoryManager


class ReplyService:

    AUTO_REPLY_PHRASES = [
        "thank you for contacting",
        "thank you for your message",
        "we have received your message",
        "our team will get back to you",
        "we will get back to you shortly",
        "automated response",
        "automated assistant",
        "currently unavailable",
        "office hours",
    ]

    STOP_PHRASES = [
        "not interested",
        "no thanks",
        "don't want",
        "do not want",
        "stop",
        "remove me",
        "unsubscribe",
        "leave me alone",
    ]

    ACTION_PHRASES = [
        "let's do it",
        "lets do it",
        "go ahead",
        "yes, do it",
        "yes do it",
        "i want to join",
        "i want to start",
        "sign me up",
        "send it",
        "send me",
        "proceed",
        "i want to join magicpin",
    ]
    WAIT_PHRASES = [
    "call me later",
    "message me later",
    "talk later",
    "speak later",
    "can we talk later",
    "let's talk later",
    "lets talk later",
    "tomorrow",
    "not right now",
    "busy right now",
    "busy at the moment",
    "i'm busy",
    "im busy",
    "give me some time",
    "give me time",
    "can we discuss this later",
    ]

    def __init__(self):
        self.llm_service = LLMService()
        self.memory_manager = MemoryManager()

    def reply(
        self,
        conversation_id: str,
        merchant_id: str,
        message: str,
        turn_number: int,
    ):

        conversation = self.memory_manager.get_conversation(
            conversation_id
        )

        if conversation is None:
            raise ValueError(
                "Conversation not found."
            )

        if conversation.merchant_id != merchant_id:
            raise ValueError(
                "Merchant ID does not match the conversation."
            )

        normalized = self._normalize(message)

        # --------------------------------------------------
        # Save merchant reply
        # --------------------------------------------------

        self.memory_manager.add_message(
            session_id=conversation_id,
            role="merchant",
            content=message,
        )

        # --------------------------------------------------
        # STOP
        # --------------------------------------------------

        if self._contains_phrase(
            normalized,
            self.STOP_PHRASES,
        ):

            return {
                "action": "end",
                "body": None,
                "cta": None,
                "wait_seconds": None,
                "rationale": (
                    "Merchant explicitly declined "
                    "or requested that the conversation stop."
                ),
            }

        # --------------------------------------------------
        # AUTO-REPLY
        # --------------------------------------------------

        if self._is_auto_reply(
            conversation_id,
            normalized,
        ):

            return {
                "action": "end",
                "body": None,
                "cta": None,
                "wait_seconds": None,
                "rationale": (
                    "Automated or repeated reply detected; "
                    "ending the conversation to avoid "
                    "repeated unsolicited messaging."
                ),
            }
        # --------------------------------------------------
        # WAIT
        # --------------------------------------------------

        if self._contains_phrase(
            normalized,
            self.WAIT_PHRASES,
        ):

            return {
                "action": "wait",
                "body": None,
                "cta": None,
                "wait_seconds": self._determine_wait_seconds(
                    normalized
                ),
                "rationale": (
                    "Merchant requested to continue "
                    "the conversation later."
                ),
            }
        # --------------------------------------------------
        # ACTION INTENT
        # --------------------------------------------------

        if self._contains_phrase(
            normalized,
            self.ACTION_PHRASES,
        ):

            response = (
                "Absolutely — let's get that started. "
                "I'll take you through the next step."
            )

            self.memory_manager.add_message(
                session_id=conversation_id,
                role="assistant",
                content=response,
            )

            return {
                "action": "send",
                "body": response,
                "cta": "open_ended",
                "wait_seconds": None,
                "rationale": (
                    "Merchant expressed clear action intent, "
                    "so the conversation transitions directly "
                    "to the next step."
                ),
            }

        # --------------------------------------------------
        # NORMAL CONVERSATION
        # --------------------------------------------------

        result = self._compose_reply(
            message=message,
            turn_number=turn_number,
        )

        if result["action"] == "send":
            self.memory_manager.add_message(
                session_id=conversation_id,
                role="assistant",
                content=result["body"],
            )

        return result
    def _determine_wait_seconds(
        self,
        message: str,
    ) -> int:

        if "tomorrow" in message:
            return 86400

        if (
            "later" in message
            or "some time" in message
        ):
            return 3600

        return 3600
    
    def _compose_reply(
        self,
        message: str,
        turn_number: int,
    ):

        prompt = f"""
You are Vera, Magicpin's merchant engagement assistant.

The merchant replied:

{message}

Conversation turn:
{turn_number}

Respond naturally and concisely.

Rules:
- Stay on the current conversation topic.
- Do not restart the pitch.
- Do not repeat the previous message.
- Do not fabricate prices, dates, statistics,
  discounts, or offers.
- Ask at most one question.
- Use a peer-to-peer merchant tone.
- If the merchant is interested, move toward
  the next concrete step.
- If the merchant is uncertain, answer briefly
  and ask one useful question.
- Return only the response text.
"""

        response = self.llm_service.generate(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a concise and helpful "
                        "Magicpin merchant engagement assistant."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
        ).strip()

        response = (
            response
            .strip('"')
            .strip("'")
            .strip()
        )

        return {
            "action": "send",
            "body": response,
            "cta": "open_ended",
            "wait_seconds": None,
            "rationale": (
                "Merchant engaged with the conversation; "
                "responding with a concise relevant next step."
            ),
        }

    def _is_auto_reply(
        self,
        conversation_id: str,
        normalized_message: str,
    ):

        if self._contains_phrase(
            normalized_message,
            self.AUTO_REPLY_PHRASES,
        ):
            return True

        conversation = (
            self.memory_manager.get_conversation(
                conversation_id
            )
        )

        if conversation is None:
            return False

        matching_messages = 0

        for message in conversation.messages:

            if (
                message.role == "merchant"
                and self._normalize(
                    message.content
                ) == normalized_message
            ):
                matching_messages += 1

        return matching_messages >= 2

    def _contains_phrase(
        self,
        message: str,
        phrases,
    ):

        return any(
            phrase in message
            for phrase in phrases
        )

    def _normalize(
        self,
        text: str,
    ):

        text = text.lower().strip()

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text