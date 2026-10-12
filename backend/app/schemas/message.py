import uuid
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


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
