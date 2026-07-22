from typing import Dict, Optional

from models.conversation import Conversation


class InMemoryConversationStore:
    """
    Stores conversations in memory.

    Later this implementation can be replaced by:
    - Redis
    - PostgreSQL
    - MongoDB

    without changing the MemoryManager.
    """

    def __init__(self):
        self._conversations: Dict[str, Conversation] = {}

    def save(self, conversation: Conversation) -> None:
        self._conversations[conversation.session_id] = conversation

    def get(self, session_id: str) -> Optional[Conversation]:
        return self._conversations.get(session_id)

    def delete(self, session_id: str) -> None:
        self._conversations.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        return session_id in self._conversations
    
# Shared singleton instance
conversation_store = InMemoryConversationStore()