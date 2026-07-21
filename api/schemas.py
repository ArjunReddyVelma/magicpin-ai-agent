from pydantic import BaseModel
from typing import Any


class ContextRequest(BaseModel):
    merchant_id: str
    context: dict[str, Any]