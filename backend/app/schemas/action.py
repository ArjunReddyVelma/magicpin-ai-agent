import uuid
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


class ActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    merchant_id: uuid.UUID
    conversation_id: Optional[uuid.UUID] = None
    action_type: str
    title: str
    description: str
    payload: Optional[Any] = None
    status: str
    created_by: str
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ActionListResponse(BaseModel):
    items: List[ActionResponse]
    total: int
    page: int
    page_size: int
