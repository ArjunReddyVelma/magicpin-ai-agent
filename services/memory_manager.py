from datetime import datetime
from uuid import uuid4

from config import MAX_HISTORY_MESSAGES
from models.conversation import Conversation, Message
from storage.conversation_store import conversation_store


class MemoryManager:
    """
    Business logic for managing conversation memory.
    """

    def __init__(self):
        self.store = conversation_store

    def create_conversation(self, merchant_id: str) -> Conversation:
        conversation = Conversation(
            session_id=str(uuid4()),
            merchant_id=merchant_id,
        )
        self.store.save(conversation)
        return conversation

    def get_conversation(self, session_id: str):
        return self.store.get(session_id)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> Conversation:

        conversation = self.store.get(session_id)

        if conversation is None:
            raise ValueError(f"Conversation {session_id} not found.")

        conversation.messages.append(
            Message(
                role=role,
                content=content,
            )
        )

        if len(conversation.messages) > MAX_HISTORY_MESSAGES:
            conversation.messages = conversation.messages[-MAX_HISTORY_MESSAGES:]

        conversation.updated_at = datetime.utcnow()

        self.store.save(conversation)

        return conversation

    def delete_conversation(self, session_id: str):
        self.store.delete(session_id)