from typing import Dict, Optional, Tuple

from models.context import ContextRecord


VALID_SCOPES = {
    "category",
    "merchant",
    "customer",
    "trigger",
}


class InMemoryContextStore:

    def __init__(self):
        # {
        #     "category": {
        #         "dentists": ContextRecord(...)
        #     },
        #     "merchant": {
        #         "m_001": ContextRecord(...)
        #     },
        #     ...
        # }
        self.contexts: Dict[str, Dict[str, ContextRecord]] = {
            scope: {}
            for scope in VALID_SCOPES
        }

    def save(
        self,
        record: ContextRecord,
    ) -> Tuple[str, Optional[int]]:
        """
        Save a context record.

        Returns:
            ("created", None)
            ("updated", None)
            ("duplicate", current_version)
            ("stale", current_version)
        """

        if record.scope not in VALID_SCOPES:
            raise ValueError(
                f"Invalid context scope: {record.scope}"
            )

        scope_store = self.contexts[record.scope]

        existing = scope_store.get(record.context_id)

        # First version
        if existing is None:
            scope_store[record.context_id] = record
            return "created", None

        # Same version = idempotent no-op
        if record.version == existing.version:
            return "duplicate", existing.version

        # Older version = reject
        if record.version < existing.version:
            return "stale", existing.version

        # Newer version = replace
        scope_store[record.context_id] = record

        return "updated", None

    def get(
        self,
        scope: str,
        context_id: str,
    ) -> Optional[ContextRecord]:

        if scope not in VALID_SCOPES:
            return None

        return self.contexts[scope].get(context_id)

    def count(self, scope: str) -> int:

        if scope not in VALID_SCOPES:
            return 0

        return len(self.contexts[scope])

    def counts(self) -> Dict[str, int]:

        return {
            scope: len(records)
            for scope, records in self.contexts.items()
        }

    def delete(
        self,
        scope: str,
        context_id: str,
    ) -> None:

        if scope in VALID_SCOPES:
            self.contexts[scope].pop(
                context_id,
                None,
            )


# Shared singleton instance
context_store = InMemoryContextStore()