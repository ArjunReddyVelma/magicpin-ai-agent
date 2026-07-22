from pathlib import Path

from services.context_manager import ContextManager
from services.memory_manager import MemoryManager


class PromptBuilder:
    """
    Builds OpenAI-compatible chat messages.
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
        latest_user_message: str,
    ):
        """
        Returns a list of OpenAI-compatible messages.
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
        context = self.context_manager.get_context(
            merchant_id
        )

        if context:

            context_text = "\n".join(
                f"{key}: {value}"
                for key, value in context.items()
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

        # Latest User Message
        messages.append(
            {
                "role": "user",
                "content": latest_user_message,
            }
        )

        return messages