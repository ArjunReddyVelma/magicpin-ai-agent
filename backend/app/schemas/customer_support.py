import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PublicMerchantProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    merchant_id: uuid.UUID
    business_name: str
    category: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class CreateCustomerSessionRequest(BaseModel):
    merchant_id: uuid.UUID
    customer_name: Optional[str] = Field(None, max_length=120)

    @field_validator("customer_name")
    @classmethod
    def clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            return s if s else None
        return None


class CreateCustomerSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    customer_token: str
    status: str
    created_at: datetime


class CustomerInquiryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Customer message cannot be empty or only whitespace.")
        return s


class CustomerInquiryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    customer_text: str
    status: str
    created_at: datetime


class CustomerHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_text: str
    reply: Optional[str] = None
    status: str
    delivered_at: Optional[datetime] = None
    created_at: datetime


class CustomerHistoryResponse(BaseModel):
    session_id: uuid.UUID
    items: List[CustomerHistoryItem]
    total: int


class MerchantSupportMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    merchant_id: uuid.UUID
    customer_name: Optional[str] = None
    customer_text: str
    suggested_reply: Optional[str] = None
    approved_reply: Optional[str] = None
    status: str
    ai_status: str
    ai_error: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class MerchantSupportListResponse(BaseModel):
    items: List[MerchantSupportMessageResponse]
    total: int
    page: int
    page_size: int


class MerchantEditReplyRequest(BaseModel):
    suggested_reply: str = Field(min_length=1, max_length=4096)

    @field_validator("suggested_reply")
    @classmethod
    def validate_reply(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Reply text cannot be empty or only whitespace.")
        return s


class DeliverReplyRequest(BaseModel):
    reply_text: Optional[str] = Field(None, max_length=4096)

    @field_validator("reply_text")
    @classmethod
    def validate_reply(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Reply text cannot be empty or whitespace only.")
            return s
        return None
