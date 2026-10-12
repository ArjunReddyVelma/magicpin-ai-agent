import uuid
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict, Field


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    status: str
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    context_metadata: Optional[Any] = None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: List[MessageResponse]
    total: int
    page: int
    page_size: int


class MessageCreateRequest(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The message content from the user",
    )
    idempotency_key: Optional[str] = Field(
        None,
        max_length=120,
        description="Optional client idempotency key to prevent duplicate sends",
    )
    retry_message_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional ID of a previously failed user message to safely re-attempt",
    )


class ContextUsedItem(BaseModel):
    context_id: uuid.UUID
    title: str
    item_type: str
    version: int


class ChatResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    context_used: List[ContextUsedItem] = Field(default_factory=list)

