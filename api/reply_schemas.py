from typing import Optional

from pydantic import BaseModel, Field


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str = Field(min_length=1)
    received_at: str
    turn_number: int = Field(ge=1)


class ReplyResponse(BaseModel):
    action: str
    body: Optional[str] = None
    cta: Optional[str] = None
    wait_seconds: Optional[int] = None
    rationale: str