from typing import Dict, Literal
from pydantic import BaseModel, Field


class HealthzResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyzResponse(BaseModel):
    status: Literal["ready"] = "ready"
    checks: Dict[str, str] = Field(default_factory=lambda: {"database": "ok"})


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
