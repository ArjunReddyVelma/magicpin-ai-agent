import uuid
import re
from typing import List, Set, Dict
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.context_item import ContextItem

STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "is", "are", "was", "were", "what",
    "how", "can", "do", "does", "in", "on", "at", "to", "for", "of",
    "with", "about", "our", "your", "my", "i", "we", "you", "it", "this",
    "that", "there", "have", "has", "had", "will", "would", "could", "should",
    "also", "any", "some", "tell", "please", "like", "get"
}

# Restrained domain-specific synonym expansions to bridge conversational customer phrasing
# with merchant context titles, categories, and policy content without external dependencies.
SYNONYM_MAP: Dict[str, Set[str]] = {
    # Operating hours & schedule
    "close": {"close", "closing", "closed", "hours", "timings", "schedule", "operating_info", "open", "am", "pm"},
    "closing": {"close", "closing", "closed", "hours", "timings", "schedule", "operating_info", "open", "am", "pm"},
    "open": {"open", "opening", "hours", "timings", "schedule", "operating_info", "close", "am", "pm"},
    "opening": {"open", "opening", "hours", "timings", "schedule", "operating_info", "close", "am", "pm"},
    "hours": {"hours", "operating_info", "timings", "schedule", "open", "close", "daily", "am", "pm"},
    "timings": {"hours", "timings", "operating_info", "schedule", "open", "close"},
    "schedule": {"hours", "schedule", "timings", "operating_info", "open", "close"},
    "time": {"hours", "timings", "schedule", "operating_info", "open", "close", "am", "pm"},
    # Beverages & drinks
    "latte": {"espresso", "coffee", "beverage", "drink"},
    "cappuccino": {"espresso", "coffee", "beverage", "drink"},
    "espresso": {"espresso", "coffee", "beverage", "drink"},
    "coffee": {"coffee", "espresso", "beverage", "drink"},
    "beverage": {"beverage", "drink", "coffee", "espresso", "tea"},
    "drink": {"drink", "beverage", "coffee", "espresso", "tea"},
    "drinks": {"drink", "beverage", "coffee", "espresso", "tea"},
    "milk": {"milk", "dairy", "plant-based"},
    "dairy": {"dairy", "milk"},
    # Food, bakery & dietary
    "pastry": {"pastry", "pastries", "bakery", "baked", "food", "snack"},
    "pastries": {"pastry", "pastries", "bakery", "baked", "food", "snack"},
    "croissant": {"pastry", "pastries", "bakery", "baked"},
    "bakery": {"bakery", "pastry", "pastries", "baked", "food"},
    "baked": {"baked", "bakery", "pastry", "pastries"},
    "dish": {"dish", "dishes", "menu", "food", "eat", "order"},
    "dishes": {"dish", "dishes", "menu", "food", "eat", "order"},
    "food": {"food", "dish", "dishes", "menu", "eat", "snack", "pastries"},
    "snack": {"snack", "snacks", "food", "pastries", "bakery"},
    "snacks": {"snack", "snacks", "food", "pastries", "bakery"},
    "menu": {"menu", "dishes", "dish", "food", "drink", "espresso", "pastries"},
    "vegan": {"vegan", "plant-based", "pastries", "food", "dietary"},
    "gluten": {"gluten-free", "gluten", "celiac", "pastries", "food", "dietary"},
    "celiac": {"gluten-free", "gluten", "pastries", "dietary"},
    # Discounts & promotions
    "discount": {"discount", "discounts", "coupon", "coupons", "promo", "deal", "offer"},
    "discounts": {"discount", "discounts", "coupon", "promo", "deal"},
    "coupon": {"coupon", "coupons", "discount", "promo", "deal"},
    "coupons": {"coupon", "coupons", "discount", "promo", "deal"},
    "promo": {"promo", "promotion", "discount", "coupon", "deal"},
    "deal": {"deal", "deals", "offer", "discount", "promo"},
    # Pricing
    "price": {"price", "charge", "cost", "fee", "rate", "additional", "extra"},
    "cost": {"cost", "charge", "price", "fee", "rate", "additional", "extra"},
    "charge": {"charge", "cost", "price", "fee", "additional", "extra", "surcharge"},
    "extra": {"extra", "additional", "charge", "cost", "price"},
    "additional": {"additional", "extra", "charge", "cost", "price"},
    # Delivery & Shipping
    "delivery": {"delivery", "deliver", "shipping", "takeaway", "pickup"},
    "deliver": {"delivery", "deliver", "shipping", "takeaway", "pickup"},
    "shipping": {"shipping", "delivery", "courier"},
    # Refunds & Returns
    "refund": {"refund", "refunds", "return", "cancellation", "exchange"},
    "return": {"return", "returns", "refund", "exchange"},
    "cancellation": {"cancellation", "cancel", "refund", "return"},
}


class ContextRetriever:
    """
    Retrieves and ranks active merchant context items for grounded prompt composition.
    Enforces merchant isolation and active-only filtering.
    Supports multi-clause query decomposition and domain synonym matching.
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
        relevance to the user's query using clause-aware scoring and synonym matching.
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

        # 1. Split query into distinct sub-clauses for multi-part intent coverage
        raw_clauses = re.split(
            r"(?:[?!.;\n]+|\b(?:and|also|plus|as well as|or|but)\b)",
            query,
            flags=re.IGNORECASE,
        )
        clauses = [c.strip() for c in raw_clauses if len(c.strip()) > 2]
        if not clauses:
            clauses = [query.strip()]

        # 2. Extract tokens and bigrams per clause
        clause_token_lists: List[List[str]] = []
        clause_bigrams: List[List[str]] = []
        all_query_tokens: List[str] = []
        for clause in clauses:
            tokens = [
                t.lower()
                for t in re.findall(r"\w+", clause)
                if len(t) > 2 and t.lower() not in STOPWORDS
            ]
            if tokens:
                clause_token_lists.append(tokens)
                all_query_tokens.extend(tokens)
                # Form consecutive bigrams
                bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]
                clause_bigrams.append(bigrams)
            else:
                clause_bigrams.append([])

        if not all_query_tokens:
            # Query has no content words; fallback to top active items
            return self._bound_items(items[: self.max_items])

        # Helper to compute score for an item against tokens and bigrams
        def score_item(item: ContextItem, tokens: List[str], bigrams: List[str]) -> int:
            score = 0
            title_lower = item.title.lower()
            content_lower = item.content.lower()
            type_lower = item.item_type.lower()

            # Bigram exact matches provide strong domain affinity (e.g. 'almond milk' vs 'almond pastries')
            for bg in bigrams:
                if bg in title_lower:
                    score += 8
                if bg in content_lower:
                    score += 6

            for token in tokens:
                # Direct token match
                if token in title_lower:
                    score += 4
                if token in type_lower:
                    score += 3
                if token in content_lower:
                    score += 2

                # Synonym match
                synonyms = SYNONYM_MAP.get(token, set())
                for syn in synonyms:
                    if syn != token:
                        if syn in title_lower:
                            score += 2
                        if syn in type_lower:
                            score += 2
                        if syn in content_lower:
                            score += 1
            return score

        selected_ids: Set[uuid.UUID] = set()
        selected_items: List[ContextItem] = []

        # 3. For each clause, select the top-scoring item if score > 0 (prevents topic starvation)
        for idx, c_tokens in enumerate(clause_token_lists):
            c_bg = clause_bigrams[idx] if idx < len(clause_bigrams) else []
            scored = [(score_item(item, c_tokens, c_bg), item) for item in items]
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored and scored[0][0] > 0:
                best_item = scored[0][1]
                if best_item.id not in selected_ids:
                    selected_ids.add(best_item.id)
                    selected_items.append(best_item)
                    if len(selected_items) >= self.max_items:
                        break

        # 4. Fill remaining slots only with items having substantial overall score (>= 4)
        if len(selected_items) < self.max_items:
            all_bigrams = [f"{all_query_tokens[i]} {all_query_tokens[i+1]}" for i in range(len(all_query_tokens) - 1)]
            overall_scored = [(score_item(item, all_query_tokens, all_bigrams), item) for item in items]
            overall_scored.sort(key=lambda x: x[0], reverse=True)
            for score, item in overall_scored:
                if score >= 4 and item.id not in selected_ids:
                    selected_ids.add(item.id)
                    selected_items.append(item)
                    if len(selected_items) >= self.max_items:
                        break

        # 5. If no items had positive score at all, fallback to top active general items
        if not selected_items:
            selected_items = items[: self.max_items]

        return self._bound_items(selected_items)

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
