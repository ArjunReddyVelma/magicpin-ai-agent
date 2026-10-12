import uuid
import re
from typing import List, Set
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.context_item import ContextItem

STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "is", "are", "was", "were", "what",
    "how", "can", "do", "does", "in", "on", "at", "to", "for", "of",
    "with", "about", "our", "your", "my", "i", "we", "you", "it", "this"
}


class ContextRetriever:
    """
    Retrieves and ranks active merchant context items for grounded prompt composition.
    Enforces merchant isolation and active-only filtering.
    """

    def __init__(self, max_items: int = 5, max_total_chars: int = 4000):
        self.max_items = max_items
        self.max_total_chars = max_total_chars

    def retrieve_relevant_context(
        self,
        merchant_id: uuid.UUID,
        query: str,
        db: Session,
    ) -> List[ContextItem]:
        """
        Retrieves active context items for the given merchant and ranks them by
        relevance to the user's query using token matching.
        """
        stmt = (
            select(ContextItem)
            .where(
                ContextItem.merchant_id == merchant_id,
                ContextItem.is_active.is_(True),
            )
            .order_by(ContextItem.created_at.desc())
        )
        items = list(db.scalars(stmt).all())
        if not items:
            return []

        # Tokenize query
        clean_tokens = [
            t.lower()
            for t in re.findall(r"\w+", query)
            if len(t) > 2 and t.lower() not in STOPWORDS
        ]

        if not clean_tokens:
            # Return most recent active items up to max_items
            return self._bound_items(items[: self.max_items])

        # Score items
        scored_items = []
        for item in items:
            score = 0
            title_lower = item.title.lower()
            content_lower = item.content.lower()
            type_lower = item.item_type.lower()

            for token in clean_tokens:
                if token in title_lower:
                    score += 3
                if token in type_lower:
                    score += 2
                if token in content_lower:
                    score += 1

            scored_items.append((score, item))

        # Sort by score descending, preserving recent order for ties
        scored_items.sort(key=lambda x: x[0], reverse=True)

        # Select items: prefer items with score > 0, fallback to general items
        selected = []
        for score, item in scored_items:
            if score > 0:
                selected.append(item)
            if len(selected) >= self.max_items:
                break

        # If no items had positive score, supply top active general items
        if not selected:
            selected = items[: self.max_items]

        return self._bound_items(selected)

    def _bound_items(self, items: List[ContextItem]) -> List[ContextItem]:
        bounded = []
        current_chars = 0
        for item in items:
            item_chars = len(item.title) + len(item.content)
            if current_chars + item_chars > self.max_total_chars and bounded:
                break
            bounded.append(item)
            current_chars += item_chars
        return bounded
