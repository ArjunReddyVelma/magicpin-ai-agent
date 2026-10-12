from services.memory_manager import MemoryManager
from services.prompt_builder import PromptBuilder
from services.llm_service import LLMService
from services.response_processor import ResponseProcessor


class ChatService:
    """
    Coordinates the complete chat workflow.
    """

    def __init__(self):
        self.memory_manager = MemoryManager()
        self.prompt_builder = PromptBuilder()
        self.llm_service = LLMService()
        self.response_processor = ResponseProcessor()

    def chat(
        self,
        merchant_id: str,
        session_id: str,
        message: str,
    ):
        conversation = self.memory_manager.get_conversation(
            session_id
        )

        if conversation is None:
            raise ValueError("Conversation not found.")

        if conversation.merchant_id != merchant_id:
            raise ValueError("Merchant ID does not match the conversation.")

        # Save user message
        self.memory_manager.add_message(
            session_id=session_id,
            role="user",
            content=message,
        )

        # Build prompt
        messages = self.prompt_builder.build_messages(
            merchant_id=merchant_id,
            session_id=session_id,
        )

        # Generate response
        response = self.llm_service.generate(messages)

        # Process response
        response = self.response_processor.process(response)

        # Save assistant message
        self.memory_manager.add_message(
            session_id=session_id,
            role="assistant",
            content=response,
        )

        return response