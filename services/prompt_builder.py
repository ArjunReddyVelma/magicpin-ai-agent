from pathlib import Path

from services.context_manager import ContextManager
from services.memory_manager import MemoryManager


class PromptBuilder:
    """
    Builds chat messages that are sent to the LLM.
    """

    def __init__(self):
        self.context_manager = ContextManager()
        self.memory_manager = MemoryManager()

        prompt_file = Path("prompts/system_prompt.txt")

        self.system_prompt = prompt_file.read_text(
            encoding="utf-8"
        ).strip()

    def build_messages(
        self,
        merchant_id: str,
        session_id: str,
    ):
        """
        Build the conversation messages for the LLM.
        """

        messages = []

        # System Prompt
        messages.append(
            {
                "role": "system",
                "content": self.system_prompt,
            }
        )

        # Merchant Context
        context_record = self.context_manager.get_context(
            "merchant",
            merchant_id,
        )

        if context_record:

            context_text = "\n".join(
                f"{key}: {value}"
                for key, value in context_record.payload.items()
            )

            messages.append(
                {
                    "role": "system",
                    "content": f"Merchant Context:\n{context_text}",
                }
            )

        # Conversation History
        conversation = self.memory_manager.get_conversation(
            session_id
        )

        if conversation:

            for message in conversation.messages:

                messages.append(
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                )

        return messages