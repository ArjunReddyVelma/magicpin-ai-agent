from dataclasses import dataclass
from typing import Any


@dataclass
class ContextRecord:
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str