from typing import Any, Dict

from pydantic import BaseModel, Field


class ContextPushRequest(BaseModel):
    scope: str = Field(min_length=1)

    context_id: str = Field(
        min_length=1
    )

    version: int = Field(
        ge=1
    )

    payload: Dict[str, Any]

    delivered_at: str


class ContextPushResponse(BaseModel):
    accepted: bool
    ack_id: str
    stored_at: str


class StaleContextResponse(BaseModel):
    accepted: bool
    reason: str
    current_version: int