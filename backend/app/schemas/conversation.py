import uuid
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    merchant_id: uuid.UUID
    title: str
    status: str
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ConversationCreateRequest(BaseModel):
    title: str = Field("New Conversation", min_length=1, max_length=200)


class ConversationUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    status: Optional[Literal["active", "archived"]] = None


class ConversationListResponse(BaseModel):
    items: List[ConversationResponse]
    total: int
    page: int
    page_size: int
