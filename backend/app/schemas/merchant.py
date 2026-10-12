import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_name: str
    category: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    created_at: datetime
    updated_at: datetime


class MerchantUpdateRequest(BaseModel):
    business_name: Optional[str] = Field(None, min_length=1, max_length=160)
    category: Optional[str] = Field(None, max_length=120)
    location: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    timezone: Optional[str] = Field(None, max_length=80)
