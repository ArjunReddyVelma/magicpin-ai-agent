import re
import pytest
from backend.app.ai.mock_provider import MockLLMProvider
from backend.app.ai.provider import LLMResponse

CAFE_PROMPT = """You are drafting a reviewable customer support reply for The Daily Roast Cafe.
OPERATING RULES:
1. This is a draft proposal for the merchant to review and edit. You cannot and will not send any message directly to the customer.
2. Ground your reply strictly in the provided merchant context.
3. Never invent prices, availability, delivery timelines, policies, or promises not in the context.
4. If context does not have the answer, politely ask a clarifying question or advise contacting the store directly.
5. Keep the reply concise (1-3 sentences) and courteous.

<merchant_context>
We offer oat milk and almond milk for all espresso drinks for an additional ₹30. Certified gluten-free almond pastries are baked fresh daily. Customers should ask staff about current availability.
</merchant_context>"""


# ---------------------------------------------------------------------------
# 1. Question about oat milk availability when policy explicitly mentions it
# ---------------------------------------------------------------------------
def test_oat_milk_availability():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Do you have oat milk?"}],
    )
    assert isinstance(resp, LLMResponse)
    content = resp.content.lower()
    assert "oat milk" in content
    assert "espresso" in content
    assert "₹30" in resp.content or "30" in content


# ---------------------------------------------------------------------------
# 2. Question about the additional ₹30 charge
# ---------------------------------------------------------------------------
def test_oat_milk_surcharge():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Is there an additional charge for oat milk?"}],
    )
    content = resp.content
    assert "₹30" in content or "30" in content
    assert "additional" in content.lower() or "charge" in content.lower()


# ---------------------------------------------------------------------------
# 3. Question about certified gluten-free almond pastries
# ---------------------------------------------------------------------------
def test_gluten_free_pastries():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Do you have gluten-free almond pastries?"}],
    )
    content = resp.content.lower()
    assert "certified gluten-free almond pastries" in content or "gluten-free" in content
    assert "fresh daily" in content or "baked" in content
    assert "staff" in content or "availability" in content


# ---------------------------------------------------------------------------
# 4. Multi-part question covering oat milk and pastries (Acceptance Scenario 1)
# ---------------------------------------------------------------------------
def test_multipart_oat_milk_and_vegan_pastries():
    provider = MockLLMProvider()
    query = "Hi! Do you have oat milk for cappuccino, and do you serve vegan pastries?"
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    content = resp.content
    c_lower = content.lower()

    # Must mention oat milk for cappuccino / espresso and ₹30 charge
    assert "oat milk" in c_lower
    assert "cappuccino" in c_lower or "espresso" in c_lower
    assert "₹30" in content or "30" in content

    # Must mention certified gluten-free almond pastries
    assert "gluten-free" in c_lower or "almond pastries" in c_lower

    # CRITICAL HONESTY GUARD: Must NOT claim pastries are vegan!
    assert "do not confirm" in c_lower or "not confirm" in c_lower or "not specified" in c_lower
    assert not ("we offer vegan pastries" in c_lower)
    assert not ("pastries are vegan" in c_lower and "not" not in c_lower)

    # Must recommend asking staff for current availability
    assert "ask" in c_lower and "staff" in c_lower


# ---------------------------------------------------------------------------
# 5. Question about opening hours when no hours are provided
# ---------------------------------------------------------------------------
def test_opening_hours_missing():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "What time do you open tomorrow morning?"}],
    )
    c_lower = resp.content.lower()
    assert "do not specify" in c_lower or "not covered" in c_lower or "do not have" in c_lower
    assert "opening" in c_lower or "hours" in c_lower
    # Must NOT invent specific times
    assert not re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", c_lower)


# ---------------------------------------------------------------------------
# 6. Question about refunds when no refund policy exists
# ---------------------------------------------------------------------------
def test_refund_policy_missing():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Can I get a full refund if I change my mind?"}],
    )
    c_lower = resp.content.lower()
    assert "do not specify" in c_lower or "not covered" in c_lower or "do not have" in c_lower
    assert "refund" in c_lower or "cancellation" in c_lower
    # Must NOT make unauthorized promises
    assert "i have refunded" not in c_lower
    assert "refund will be processed" not in c_lower


# ---------------------------------------------------------------------------
# 7. Empty merchant context
# ---------------------------------------------------------------------------
def test_empty_merchant_context():
    empty_prompt = """You are drafting a reviewable customer support reply for Central Store.
<merchant_context>
(No relevant merchant context configured)
</merchant_context>"""
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=empty_prompt,
        messages=[{"role": "user", "content": "Do you sell coffee?"}],
    )
    c_lower = resp.content.lower()
    assert "do not currently have configured store policies" in c_lower or "staff" in c_lower
    assert "central store" in c_lower


# ---------------------------------------------------------------------------
# 8. Product or discount not mentioned in policy (Acceptance Scenario 2)
# ---------------------------------------------------------------------------
def test_unsupported_closing_time_and_discount():
    provider = MockLLMProvider()
    query = "What time do you close, and can I get a 50% discount?"
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    c_lower = resp.content.lower()
    # Must not invent closing time or 50% discount
    assert "do not specify" in c_lower or "do not have" in c_lower or "not covered" in c_lower
    assert "closing" in c_lower or "hours" in c_lower
    assert "50%" in c_lower or "discount" in c_lower
    assert "staff" in c_lower


# ---------------------------------------------------------------------------
# 9. Context that explicitly contradicts a common assumption
# ---------------------------------------------------------------------------
def test_contradiction_handling():
    contra_prompt = """You are drafting a reviewable customer support reply for Espresso Bar.
<merchant_context>
We do not offer decaf coffee under any circumstances. All espresso drinks use full-caffeine arabica beans.
</merchant_context>"""
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=contra_prompt,
        messages=[{"role": "user", "content": "Can I order a decaf iced latte?"}],
    )
    c_lower = resp.content.lower()
    assert "do not offer decaf" in c_lower or "full-caffeine" in c_lower


# ---------------------------------------------------------------------------
# 10. Question containing unrelated or irrelevant wording
# ---------------------------------------------------------------------------
def test_unrelated_wording():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "What is the capital of Australia?"}],
    )
    c_lower = resp.content.lower()
    assert "not covered in our store policies" in c_lower or "do not have" in c_lower
    assert "staff" in c_lower


# ---------------------------------------------------------------------------
# 11. Preservation of existing provider response contract
# ---------------------------------------------------------------------------
def test_provider_contract_preservation():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Do you have oat milk?"}],
        max_tokens=200,
        temperature=0.2,
    )
    assert isinstance(resp, LLMResponse)
    assert resp.provider == "mock"
    assert resp.model == "mock-llama-3.3-70b"
    assert resp.content and len(resp.content) > 0
    assert resp.input_tokens is not None and resp.input_tokens > 0
    assert resp.output_tokens is not None and resp.output_tokens > 0
    assert resp.raw_metadata.get("mock") is True
    assert resp.raw_metadata.get("call_index") == 1


# ---------------------------------------------------------------------------
# 12. Regression coverage: explicit default_response and canned responses
# ---------------------------------------------------------------------------
def test_explicit_default_and_canned_regression():
    # Explicit default response
    custom_provider = MockLLMProvider(default_response="Custom static response")
    resp1 = custom_provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Do you have oat milk?"}],
    )
    assert resp1.content == "Custom static response"

    # Enqueued canned response overrides dynamic generation
    custom_provider.enqueue_response("Enqueued priority answer")
    resp2 = custom_provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Do you have oat milk?"}],
    )
    assert resp2.content == "Enqueued priority answer"


# ---------------------------------------------------------------------------
# 13. Broad menu inquiry: "do you have anyother dishes"
# ---------------------------------------------------------------------------
def test_broad_menu_anyother_dishes():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "do you have anyother dishes"}],
    )
    c_lower = resp.content.lower()
    # Must summarize known offerings
    assert "espresso" in c_lower or "oat milk" in c_lower or "almond milk" in c_lower
    assert "gluten-free" in c_lower or "almond pastries" in c_lower
    assert "₹30" in resp.content or "30" in c_lower
    # Must distinguish known items from unknown full menu
    assert "do not list any additional dishes" in c_lower or "full menu" in c_lower
    assert "staff" in c_lower
    # Strictly avoid inventing unmentioned dishes
    assert not any(dish in c_lower for dish in ["sandwich", "salad", "pizza", "pasta", "soup", "burger"])
    # Strictly avoid unsupported vegan claims
    assert "pastries are vegan" not in c_lower and "vegan" not in c_lower


# ---------------------------------------------------------------------------
# 14. Broad menu inquiry: "what else can I order?"
# ---------------------------------------------------------------------------
def test_broad_menu_what_else_can_i_order():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "what else can I order?"}],
    )
    c_lower = resp.content.lower()
    assert "espresso" in c_lower or "oat milk" in c_lower
    assert "gluten-free" in c_lower or "almond pastries" in c_lower
    assert "do not list any additional dishes" in c_lower or "full menu" in c_lower
    assert "staff" in c_lower


# ---------------------------------------------------------------------------
# 15. Broad menu inquiry: "what food and drink options do you offer?"
# ---------------------------------------------------------------------------
def test_broad_menu_food_and_drink_options():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "what food and drink options do you offer?"}],
    )
    c_lower = resp.content.lower()
    assert "espresso" in c_lower
    assert "almond pastries" in c_lower or "gluten-free" in c_lower
    assert "staff" in c_lower


# ---------------------------------------------------------------------------
# 16. Synonym handling: "Do you offer plant-based milk?"
# ---------------------------------------------------------------------------
def test_synonym_plant_based_milk():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Do you offer plant-based milk?"}],
    )
    c_lower = resp.content.lower()
    assert "oat milk" in c_lower and "almond milk" in c_lower
    assert "₹30" in resp.content or "30" in c_lower
    # Must NOT mistakenly trigger a discount / 50% off clause because of the word "offer"
    assert "50%" not in c_lower
    assert "discount" not in c_lower


# ---------------------------------------------------------------------------
# 17. Synonym handling: "Are dairy-free alternatives available for coffee?"
# ---------------------------------------------------------------------------
def test_synonym_dairy_free_alternatives():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "Are dairy-free alternatives available for coffee?"}],
    )
    c_lower = resp.content.lower()
    assert "oat milk" in c_lower or "almond milk" in c_lower
    assert "espresso" in c_lower


# ---------------------------------------------------------------------------
# 18. Multi-part menu and missing hours: "what else can I order, and what time do you close?"
# ---------------------------------------------------------------------------
def test_multipart_menu_and_hours():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=CAFE_PROMPT,
        messages=[{"role": "user", "content": "what else can I order, and what time do you close?"}],
    )
    c_lower = resp.content.lower()
    # Summarizes known menu options
    assert "espresso" in c_lower or "oat milk" in c_lower
    assert "gluten-free" in c_lower or "almond pastries" in c_lower
    # Notes unconfigured hours
    assert "do not specify our opening or closing hours" in c_lower or "hours" in c_lower


# ---------------------------------------------------------------------------
# 19. Broad menu inquiry when context contains no menu items
# ---------------------------------------------------------------------------
def test_broad_menu_no_menu_in_context():
    non_food_prompt = """You are drafting a reviewable customer support reply for Tech Gear Hub.
<merchant_context>
All hardware purchases come with a 30-day warranty against manufacturing defects.
</merchant_context>"""
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=non_food_prompt,
        messages=[{"role": "user", "content": "what food and drink options do you offer?"}],
    )
    c_lower = resp.content.lower()
    assert "do not specify our food and drink menu" in c_lower or "staff" in c_lower
    assert "tech gear hub" in c_lower


# ===========================================================================
# Multi-Context Acceptance Suite (Tests A through E)
# ===========================================================================

MULTI_CONTEXT_CAFE_PROMPT = """You are drafting a reviewable customer support reply for The Daily Roast Cafe.
OPERATING RULES:
1. This is a draft proposal for the merchant to review and edit. You cannot and will not send any message directly to the customer.
2. Ground your reply strictly in the provided merchant context.
3. Never invent prices, availability, delivery timelines, policies, or promises not in the context.
4. If context does not have the answer, politely ask a clarifying question or advise contacting the store directly.
5. Keep the reply concise (1-3 sentences) and courteous.

<merchant_context>
- Beverage Options: We offer oat milk and almond milk for all espresso drinks for an additional ₹30.
- Bakery & Pastries: Certified gluten-free almond pastries are baked fresh daily. Customers should ask staff about current availability.
- Operating Hours: Opening hours are 8:00 AM to 8:00 PM daily.
</merchant_context>"""


# ---------------------------------------------------------------------------
# Test A: Single topic covered by one context item
# ---------------------------------------------------------------------------
def test_multicontext_test_a_single_topic_oat_milk():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=MULTI_CONTEXT_CAFE_PROMPT,
        messages=[{"role": "user", "content": "Do you offer oat milk?"}],
    )
    content = resp.content
    c_lower = content.lower()

    # Grounded in beverage context
    assert "oat milk" in c_lower
    assert "espresso" in c_lower
    assert "₹30" in content or "30" in content
    # Does not inject unrelated policies
    assert "pastries" not in c_lower
    assert "gluten-free" not in c_lower
    assert "8:00" not in c_lower
    assert "hours" not in c_lower


# ---------------------------------------------------------------------------
# Test B: Multi-topic inquiry covering two context items
# ---------------------------------------------------------------------------
def test_multicontext_test_b_beverage_and_dietary_pastries():
    provider = MockLLMProvider()
    resp = provider.generate_response(
        system_prompt=MULTI_CONTEXT_CAFE_PROMPT,
        messages=[{"role": "user", "content": "Can I get an oat milk cappuccino and are your pastries vegan?"}],
    )
    content = resp.content
    c_lower = content.lower()

    # Part 1: Oat milk cappuccino & surcharge
    assert "oat milk" in c_lower
    assert "cappuccino" in c_lower or "espresso" in c_lower
    assert "₹30" in content or "30" in content

    # Part 2: Certified gluten-free almond pastries & dietary guardrail
    assert "gluten-free" in c_lower or "almond pastries" in c_lower
    assert "do not confirm" in c_lower or "not confirm" in c_lower or "not specified" in c_lower
    assert not ("pastries are vegan" in c_lower and "not" not in c_lower)
    assert "ask" in c_lower and "staff" in c_lower


# ---------------------------------------------------------------------------
# Test C: Multi-topic inquiry combining operating hours and product options
# ---------------------------------------------------------------------------
def test_multicontext_test_c_closing_hours_and_almond_milk_latte():
    provider = MockLLMProvider()
    query = "What time do you close, and can I get almond milk in my latte?"
    resp = provider.generate_response(
        system_prompt=MULTI_CONTEXT_CAFE_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    content = resp.content
    c_lower = content.lower()

    # Topic 1: Closing time from operating hours context
    assert "8:00 pm" in c_lower or "8:00" in c_lower
    assert "close" in c_lower or "hours" in c_lower
    assert "daily" in c_lower

    # Topic 2: Almond milk for latte/espresso with ₹30 surcharge
    assert "almond milk" in c_lower
    assert "latte" in c_lower or "espresso" in c_lower
    assert "₹30" in content or "30" in content

    # Neither topic omitted
    assert len(c_lower.split(".")) >= 2


# ---------------------------------------------------------------------------
# Test D: Unsupported claims and non-existent discounts + delivery
# ---------------------------------------------------------------------------
def test_multicontext_test_d_unsupported_discount_and_delivery():
    provider = MockLLMProvider()
    query = "Do you have a 50% discount and free delivery?"
    resp = provider.generate_response(
        system_prompt=MULTI_CONTEXT_CAFE_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    content = resp.content
    c_lower = content.lower()

    # Grounded: neither offer is invented or assumed
    assert not ("we offer 50%" in c_lower)
    assert not ("free delivery is available" in c_lower)

    # Clearly explains context does not confirm 50% discount
    assert "50%" in c_lower or "discount" in c_lower
    assert "do not confirm" in c_lower or "not confirm" in c_lower or "do not have" in c_lower

    # Clearly explains context does not confirm free delivery
    assert "free delivery" in c_lower or "delivery" in c_lower

    # Directs to store staff
    assert "staff" in c_lower


# ---------------------------------------------------------------------------
# Test E: Missing context / unconfirmed topic handling
# ---------------------------------------------------------------------------
def test_multicontext_test_e_unmentioned_wifi_and_parking():
    provider = MockLLMProvider()
    query = "Do you have free Wi-Fi and parking?"
    resp = provider.generate_response(
        system_prompt=MULTI_CONTEXT_CAFE_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    content = resp.content
    c_lower = content.lower()

    # Acknowledges topic is not covered in store policies
    assert "not covered in our store policies" in c_lower or "do not currently have" in c_lower or "do not specify" in c_lower

    # Does not fabricate Wi-Fi or parking
    assert "free wi-fi is" not in c_lower
    assert "parking is available" not in c_lower

    # Directs customer to staff
    assert "staff" in c_lower
