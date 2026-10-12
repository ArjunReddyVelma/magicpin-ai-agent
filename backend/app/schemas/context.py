import uuid
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field

ContextItemType = Literal["faq", "policy", "business_fact", "service", "operating_info"]


class ContextItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    merchant_id: uuid.UUID
    item_type: str
    title: str
    content: str
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ContextCreateRequest(BaseModel):
    item_type: ContextItemType
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    is_active: bool = True


class ContextUpdateRequest(BaseModel):
    item_type: Optional[ContextItemType] = None
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None
    expected_version: Optional[int] = None


class ContextListResponse(BaseModel):
    items: List[ContextItemResponse]
    total: int
    page: int
    page_size: int
