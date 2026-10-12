from datetime import datetime, timezone
from uuid import uuid4

from models.context import ContextRecord
from storage.context_store import context_store


VALID_SCOPES = {
    "category",
    "merchant",
    "customer",
    "trigger",
}


class ContextManager:

    def __init__(self):
        self.store = context_store

    def save_context(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict,
        delivered_at: str,
    ):
        if scope not in VALID_SCOPES:
            raise ValueError(
                f"Invalid context scope: {scope}"
            )

        record = ContextRecord(
            scope=scope,
            context_id=context_id,
            version=version,
            payload=payload,
            delivered_at=delivered_at,
        )

        return self.store.save(record)

    def get_context(
        self,
        scope: str,
        context_id: str,
    ):
        return self.store.get(
            scope,
            context_id,
        )

    def get_counts(self):
        return self.store.counts()

    def generate_ack_id(self):
        return f"ack_{uuid4().hex[:12]}"

    def current_timestamp(self):
        return datetime.now(
            timezone.utc
        ).isoformat().replace("+00:00", "Z")