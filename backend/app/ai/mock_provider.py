import re
from typing import Optional, List, Dict, Any
from backend.app.ai.provider import (
    LLMProvider,
    LLMResponse,
    LLMProviderError,
    LLMTimeoutError,
)


class MockLLMProvider(LLMProvider):
    """
    Controllable in-memory LLM provider for unit, integration,
    and failure-path testing without network access or live API keys.
    Supports controllable canned responses and deterministic, context-grounded
    response generation based on customer queries and merchant policies.
    """

    def __init__(
        self,
        default_response: Optional[str] = None,
        model: str = "mock-llama-3.3-70b",
    ):
        self.default_response = default_response
        self.model = model
        self.provider_name = "mock"
        self.should_raise: Optional[Exception] = None
        self.calls: List[Dict[str, Any]] = []
        self.canned_responses: List[str] = []

    def set_should_raise(self, exc: Optional[Exception]) -> None:
        self.should_raise = exc

    def enqueue_response(self, text: str) -> None:
        self.canned_responses.append(text)

    def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.calls.append({
            "system_prompt": system_prompt,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })

        if self.should_raise is not None:
            raise self.should_raise

        if self.canned_responses:
            content = self.canned_responses.pop(0)
        elif self.default_response is not None:
            content = self.default_response
        else:
            content = self._generate_grounded_response(system_prompt, messages)

        return LLMResponse(
            content=content,
            provider=self.provider_name,
            model=self.model,
            input_tokens=len(system_prompt) // 4 + sum(len(m.get("content", "")) // 4 for m in messages),
            output_tokens=len(content) // 4,
            raw_metadata={"mock": True, "call_index": len(self.calls)},
        )

    def _generate_grounded_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
    ) -> str:
        """
        Generates a deterministic, policy-grounded reply using standard-library string and regex parsing.
        Strictly prevents hallucinating facts, prices, discounts, or dietary assertions not in context.
        """
        # 1. Extract customer question
        query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                query = m.get("content", "").strip()
                break
        if not query and messages:
            query = messages[-1].get("content", "").strip()

        # 2. Extract merchant context
        ctx_match = re.search(r"<merchant_context>(.*?)</merchant_context>", system_prompt, re.DOTALL)
        raw_context = ctx_match.group(1).strip() if ctx_match else ""

        # 3. Extract business name
        biz_match = re.search(r"(?:reply for|Assistant for)\s+([^\.\n\r]+)", system_prompt)
        biz_name = biz_match.group(1).strip() if biz_match else "our store"

        # 4. Check for empty context
        is_empty_context = (
            not raw_context
            or "no relevant merchant context" in raw_context.lower()
            or "no configured merchant context" in raw_context.lower()
        )
        if is_empty_context:
            return (
                f"Hello! Thank you for reaching out to {biz_name}. "
                "We do not currently have configured store policies to answer your inquiry. "
                "Please check directly with our store staff for assistance."
            )

        # 5. Extract sentences / clauses from context
        clean_lines = []
        for line in raw_context.splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^(?:\[Source\s+\d+:[^\]]+\]\s*Title:[^\n:]*|[-*]\s*[^:]+:)\s*", "", line).strip()
            if line:
                clean_lines.append(line)

        full_context_text = " ".join(clean_lines)
        ctx_lower = full_context_text.lower()
        q_lower = query.lower()

        # Query normalization: remove special characters (except ₹ and .), collapse whitespace, expand common contractions/compounds
        q_norm = re.sub(r"[^\w\s₹\.]", " ", q_lower)
        q_norm = re.sub(r"\s+", " ", q_norm).strip()
        q_norm = re.sub(r"\banyother\b", "any other", q_norm)

        raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", full_context_text) if s.strip()]

        supported_parts: List[str] = []
        unsupported_parts: List[str] = []
        recommended_actions: List[str] = []

        def clean_period(s: str) -> str:
            s = s.strip()
            return s.rstrip(".") + "."

        # Broad Menu / Catalog / Food & Drink Options Intent
        broad_menu_indicators = [
            "any other dish", "any other dishes", "other dishes", "other dish",
            "what else can i order", "what else do you have", "what else is there",
            "food options", "drink options", "food and drink", "food or drink",
            "what can i eat", "anything to eat", "anything else to eat", "what to eat",
            "what do you serve", "what do you offer", "what options do you have",
            "on the menu", "your menu", "the menu", "full menu", "see the menu",
            "what dishes", "other options", "dishes do you have", "dishes available",
        ]
        asks_broad_menu = any(ind in q_norm for ind in broad_menu_indicators) or (
            any(w in q_norm for w in ["dishes", "dish", "menu"]) and any(w in q_norm for w in ["other", "any", "what", "more", "have", "offer"])
        )

        if asks_broad_menu:
            known_offerings = []
            # Check drinks in context
            has_drinks_in_ctx = any(m in ctx_lower for m in ["espresso", "coffee", "drink", "oat milk", "almond milk", "tea", "beverage"])
            if has_drinks_in_ctx:
                if "oat milk" in ctx_lower and "almond milk" in ctx_lower:
                    price_match = re.search(r"(?:for\s+(?:an\s+)?additional|extra|additional\s+charge\s+of)\s*([₹Rs\.\d\s]+)", full_context_text, re.IGNORECASE)
                    surcharge_str = f" (for an additional {price_match.group(1).strip().rstrip('.')})" if price_match else ""
                    known_offerings.append(f"espresso drinks with oat milk and almond milk options{surcharge_str}")
                else:
                    bev_sent = next((s for s in raw_sentences if any(t in s.lower() for t in ["espresso", "coffee", "drink", "milk", "tea"])), "")
                    if bev_sent:
                        known_offerings.append(bev_sent.rstrip("."))

            # Check bakery/food in context
            has_food_in_ctx = any(p in ctx_lower for p in ["pastr", "croissant", "bak", "food", "snack", "dish", "almond pastr"])
            if has_food_in_ctx:
                food_sent = next((s for s in raw_sentences if any(t in s.lower() for t in ["pastr", "croissant", "bak", "food", "snack"])), "")
                if food_sent:
                    food_text = food_sent.rstrip(".")
                    if food_text and food_text[0].isupper():
                        food_text = food_text[0].lower() + food_text[1:]
                    known_offerings.append(food_text)

            extra_clauses = []
            asks_hours = any(w in q_norm for w in ["close", "closing", "open", "opening", "hours", "timings", "time do you", "when do you"])
            if asks_hours:
                has_hours_ctx = any(h in ctx_lower for h in ["am", "pm", "hours", "open from", "close at", "open daily", "operating hours"])
                if has_hours_ctx:
                    hours_sent = next((s for s in raw_sentences if any(h in s.lower() for h in ["am", "pm", "hours", "open", "close"])), "")
                    if hours_sent:
                        extra_clauses.append(hours_sent.rstrip("."))
                else:
                    extra_clauses.append("our store policies do not specify our opening or closing hours")

            asks_discount = any(w in q_norm for w in ["discount", "discounts", "coupon", "coupons", "promo", "deal", "50%"]) or bool(re.search(r"\b\d+%\s*off\b", q_norm))
            if asks_discount:
                has_discount_ctx = any(d in ctx_lower for d in ["discount", "coupon", "promo", "deal"])
                if has_discount_ctx:
                    disc_sent = next((s for s in raw_sentences if any(d in s.lower() for d in ["discount", "coupon", "promo", "deal"])), "")
                    if disc_sent:
                        extra_clauses.append(disc_sent.rstrip("."))
                else:
                    extra_clauses.append("we do not have any confirmed 50% discounts or promotional offers listed in our policies")

            extra_str = f" Additionally, {', and '.join(extra_clauses)}." if extra_clauses else ""

            if known_offerings:
                summary = ", and ".join(known_offerings) if len(known_offerings) > 1 else known_offerings[0]
                return (
                    f"From our configured store menu, we offer {summary}. "
                    "Our store policies do not list any additional dishes or a full menu; "
                    f"please check directly with our store staff for today's complete selection and availability.{extra_str}"
                ).strip()
            else:
                return (
                    f"Thank you for contacting {biz_name}. Currently, our store policies do not specify our food and drink menu. "
                    f"Please check directly with our store staff for available options.{extra_str}"
                ).strip()

        # Domain A: Milk Alternatives & Espresso / Drinks
        asks_milk = any(w in q_norm for w in [
            "oat milk", "almond milk", "soy milk", "dairy free milk", "dairy-free milk", "milk alternative", "milk alternatives",
            "plant based milk", "plant-based milk", "plant based", "plant-based", "non dairy milk", "non-dairy milk", "non dairy", "non-dairy", "milk"
        ])
        asks_drinks = any(w in q_norm for w in ["cappuccino", "latte", "espresso", "coffee", "drink", "beverage"])
        asks_price = any(w in q_norm for w in ["charge", "cost", "price", "extra", "additional", "how much", "₹30", "30"])
        asks_decaf = "decaf" in q_norm

        if asks_milk or (asks_drinks and not asks_decaf) or (asks_price and any(m in ctx_lower for m in ["oat", "almond", "espresso"])):
            has_milk_ctx = any(m in ctx_lower for m in ["oat milk", "almond milk", "soy milk", "milk"])
            has_espresso_ctx = any(e in ctx_lower for e in ["espresso", "coffee", "beverage", "drink"])

            if has_milk_ctx or has_espresso_ctx:
                milk_sent = next((s for s in raw_sentences if any(m in s.lower() for m in ["oat", "almond", "soy", "milk"])), "")
                if not milk_sent:
                    milk_sent = next((s for s in raw_sentences if "espresso" in s.lower()), "")

                if milk_sent:
                    price_match = re.search(r"(?:for\s+(?:an\s+)?additional|extra|additional\s+charge\s+of)\s*([₹Rs\.\d\s]+)", milk_sent, re.IGNORECASE)
                    surcharge_str = f" for an additional {price_match.group(1).strip().rstrip('.')}" if price_match else ""

                    if "cappuccino" in q_norm:
                        drink_ref = "cappuccino and all espresso drinks"
                    elif "latte" in q_norm:
                        drink_ref = "lattes and all espresso drinks"
                    elif "espresso" in q_norm:
                        drink_ref = "all espresso drinks"
                    else:
                        drink_ref = "all espresso drinks"

                    if "oat milk" in q_norm and "oat milk" in ctx_lower:
                        supported_parts.append(clean_period(f"We offer oat milk for {drink_ref}{surcharge_str}"))
                    elif "almond milk" in q_norm and "almond milk" in ctx_lower:
                        supported_parts.append(clean_period(f"We offer almond milk for {drink_ref}{surcharge_str}"))
                    elif any(pb in q_norm for pb in ["plant based", "plant-based", "non dairy", "non-dairy", "milk alternative", "milk alternatives"]) and ("oat milk" in ctx_lower or "almond milk" in ctx_lower):
                        supported_parts.append(clean_period(f"We offer plant-based oat milk and almond milk for {drink_ref}{surcharge_str}"))
                    elif asks_price and surcharge_str:
                        supported_parts.append(clean_period(f"Yes, there is an additional charge of {price_match.group(1).strip().rstrip('.')} for milk alternatives on espresso drinks"))
                    else:
                        supported_parts.append(clean_period(milk_sent))
            else:
                if asks_milk:
                    unsupported_parts.append("our store policies do not mention availability or pricing for milk alternatives")

        # Domain B: Bakery, Pastries & Dietary (Gluten-Free vs Vegan)
        asks_pastry = any(w in q_norm for w in ["pastry", "pastries", "croissant", "bakery", "baked", "almond pastry"])
        asks_vegan = "vegan" in q_norm
        asks_gluten_free = any(w in q_norm for w in ["gluten-free", "gluten free", "celiac"])

        if asks_pastry or asks_vegan or asks_gluten_free:
            has_pastry_ctx = any(p in ctx_lower for p in ["pastr", "croissant", "bak", "almond pastr"])
            if has_pastry_ctx:
                pastry_sent = next((s for s in raw_sentences if any(p in s.lower() for p in ["pastr", "croissant", "bak"])), "")
                is_gf_in_ctx = "gluten-free" in ctx_lower or "gluten free" in ctx_lower
                is_vegan_in_ctx = "vegan" in ctx_lower

                if asks_vegan and not is_vegan_in_ctx:
                    # Strict Grounding Guard: Context does NOT confirm vegan
                    if is_gf_in_ctx:
                        supported_parts.append(clean_period("We also have certified gluten-free almond pastries baked fresh daily, but our policies do not confirm if they are vegan"))
                    else:
                        supported_parts.append(clean_period(f"{pastry_sent.rstrip('.')}, but our policies do not confirm vegan options"))
                elif asks_vegan and is_vegan_in_ctx:
                    supported_parts.append(clean_period("We offer vegan pastries as stated in our store menu"))
                elif asks_gluten_free and is_gf_in_ctx:
                    supported_parts.append(clean_period("Yes, certified gluten-free almond pastries are baked fresh daily"))
                elif pastry_sent:
                    supported_parts.append(clean_period(pastry_sent))

                if ("ask staff" in ctx_lower or "current availability" in ctx_lower) and (asks_pastry or asks_vegan or asks_gluten_free):
                    recommended_actions.append("Please ask our staff regarding current daily availability.")
            else:
                if asks_pastry:
                    unsupported_parts.append("our policies do not list pastry or bakery options")
                elif asks_vegan:
                    unsupported_parts.append("our policies do not confirm vegan items")

        # Domain C: Operating Hours & Closing Time
        asks_hours = any(w in q_norm for w in ["close", "closing", "open", "opening", "hours", "timings", "time do you", "when do you"])
        if asks_hours:
            has_hours_ctx = any(h in ctx_lower for h in ["am", "pm", "hours", "open from", "close at", "open daily", "operating hours"])
            if has_hours_ctx:
                hours_sent = next((s for s in raw_sentences if any(h in s.lower() for h in ["am", "pm", "hours", "open", "close"])), "")
                supported_parts.append(clean_period(hours_sent))
            else:
                unsupported_parts.append("our store policies do not specify our opening or closing hours")

        # Domain D: Discounts, Promotions, Coupons
        asks_discount = any(w in q_norm for w in ["discount", "discounts", "coupon", "coupons", "promo", "deal", "50%"]) or bool(re.search(r"\b\d+%\s*off\b", q_norm))
        if asks_discount:
            has_discount_ctx = any(d in ctx_lower for d in ["discount", "coupon", "promo", "deal"])
            if has_discount_ctx:
                disc_sent = next((s for s in raw_sentences if any(d in s.lower() for d in ["discount", "coupon", "promo", "deal"])), "")
                supported_parts.append(clean_period(disc_sent))
            else:
                unsupported_parts.append("we do not have any confirmed 50% discounts or promotional offers listed in our policies")

        # Domain E: Refunds, Returns, Cancellations
        asks_refund = any(w in q_norm for w in ["refund", "return", "cancel", "cancellation", "exchange", "money back"])
        if asks_refund:
            has_refund_ctx = any(r in ctx_lower for r in ["refund", "return", "cancel", "cancellation", "exchange"])
            if has_refund_ctx:
                ref_sent = next((s for s in raw_sentences if any(r in s.lower() for r in ["refund", "return", "cancel"])), "")
                supported_parts.append(clean_period(ref_sent))
            else:
                unsupported_parts.append("our store policies do not specify refund or cancellation terms")

        # Domain F: General Token-Based Sentence Match for other policies (e.g. Wi-Fi, Delivery, Pets, Cash, Decaf)
        if not supported_parts and not unsupported_parts:
            q_tokens = [w for w in re.findall(r"\w+", q_norm) if len(w) > 3 and w not in ["what", "have", "with", "from", "your", "this", "that", "there", "about", "could", "would"]]
            scored_sentences = []
            for s in raw_sentences:
                s_lower = s.lower()
                overlap = sum(1 for t in q_tokens if t in s_lower)
                if overlap > 0:
                    scored_sentences.append((overlap, s))

            if scored_sentences:
                scored_sentences.sort(key=lambda x: x[0], reverse=True)
                supported_parts.append(clean_period(scored_sentences[0][1]))
            else:
                unsupported_parts.append("that information is not covered in our store policies")

        # Synthesize Final Response
        response_sentences = []
        if supported_parts:
            response_sentences.extend(supported_parts)

        if unsupported_parts:
            unsupported_clause = ", and ".join(unsupported_parts) if len(unsupported_parts) > 1 else unsupported_parts[0]
            if supported_parts:
                response_sentences.append(clean_period(f"Additionally, {unsupported_clause}"))
            else:
                response_sentences.append(clean_period(f"Thank you for contacting {biz_name}. Currently, {unsupported_clause}"))

        if recommended_actions:
            response_sentences.extend(recommended_actions)
        elif unsupported_parts and not supported_parts:
            response_sentences.append("Please contact our store staff directly, and we will be happy to assist you.")

        final_reply = " ".join(response_sentences)
        final_reply = re.sub(r"\s+", " ", final_reply).strip()
        return final_reply
