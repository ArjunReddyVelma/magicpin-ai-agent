from datetime import datetime
from models import conversation
from services.context_manager import ContextManager
from services.llm_service import LLMService
from services.memory_manager import MemoryManager
from storage.engagement_store import engagement_store


class EngagementPlanner:

    def __init__(self):
        self.context_manager = ContextManager()
        self.llm_service = LLMService()
        self.memory_manager = MemoryManager()

    def plan(
        self,
        now: str,
        available_triggers: list[str],
    ):

        actions = []

        for trigger_id in available_triggers:

            trigger = self.context_manager.get_context(
                "trigger",
                trigger_id,
            )

            if trigger is None:
                continue

            trigger_data = trigger.payload

            # -------------------------------------------------
            # Expiration check
            # -------------------------------------------------

            if self._is_expired(
                trigger_data,
                now,
            ):
                continue

            suppression_key = trigger_data.get(
                "suppression_key"
            )

            if not suppression_key:
                suppression_key = (
                    f"trigger:{trigger_id}"
                )

            # -------------------------------------------------
            # Suppression check
            # -------------------------------------------------

            if engagement_store.has_been_sent(
                suppression_key
            ):
                continue

            # -------------------------------------------------
            # Determine target
            # -------------------------------------------------

            merchant_id = trigger_data.get(
                "merchant_id"
            )

            customer_id = trigger_data.get(
                "customer_id"
            )

            if not merchant_id:
                continue

            merchant = self.context_manager.get_context(
                "merchant",
                merchant_id,
            )

            if merchant is None:
                continue

            # -------------------------------------------------
            # Category
            # -------------------------------------------------

            category_slug = merchant.payload.get(
                "category_slug"
            )

            category = None

            if category_slug:
                category = self.context_manager.get_context(
                    "category",
                    category_slug,
                )

            if category is None:
                continue

            # -------------------------------------------------
            # Customer context
            # -------------------------------------------------

            customer = None

            if customer_id:
                customer = self.context_manager.get_context(
                    "customer",
                    customer_id,
                )

            # -------------------------------------------------
            # Compose message
            # -------------------------------------------------

            body = self._compose_message(
                category=category.payload,
                merchant=merchant.payload,
                trigger=trigger_data,
                customer=customer.payload if customer else None,
            )

            if not body:
                continue

            # -------------------------------------------------
            # Determine recipient
            # -------------------------------------------------

            if customer:
                send_as = "merchant_on_behalf"
            else:
                send_as = "vera"

            conversation = self.memory_manager.create_conversation(
                merchant_id=merchant_id
            )

            conversation_id = conversation.session_id

            self.memory_manager.add_message(
                session_id=conversation_id,
                role="assistant",
                content=body,
            )
            
            template_name = (
                "vera_customer_v1"
                if customer
                else "vera_merchant_v1"
            )

            template_params = self._template_params(
                merchant.payload,
                customer.payload if customer else None,
            )

            cta = self._determine_cta(
                trigger_data
            )

            rationale = self._build_rationale(
                trigger_data,
                merchant.payload,
            )

            action = {
                "conversation_id": conversation_id,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "send_as": send_as,
                "trigger_id": trigger_id,
                "template_name": template_name,
                "template_params": template_params,
                "body": body,
                "cta": cta,
                "suppression_key": suppression_key,
                "rationale": rationale,
            }

            actions.append(action)

            engagement_store.mark_sent(
                suppression_key
            )

        return actions

    def _compose_message(
        self,
        category,
        merchant,
        trigger,
        customer=None,
    ):

        merchant_name = (
            merchant.get("identity", {})
            .get("owner_first_name")
            or merchant.get("identity", {})
            .get("name")
            or "there"
        )

        category_name = category.get(
            "display_name",
            category.get("slug", ""),
        )

        trigger_kind = trigger.get(
            "kind",
            "update",
        )

        trigger_payload = trigger.get(
            "payload",
            {},
        )

        customer_name = None

        if customer:
            customer_name = (
                customer.get("identity", {})
                .get("name")
            )

        prompt = f"""
You are Vera, Magicpin's merchant engagement assistant.

Write ONE concise WhatsApp message.

Merchant:
{merchant_name}

Category:
{category_name}

Trigger:
{trigger_kind}

Trigger data:
{trigger_payload}

Customer:
{customer_name or "None"}

Merchant data:
{merchant}

Category data:
{category}

Rules:
- Use only facts provided above.
- Never fabricate numbers, prices, dates, or offers.
- Be specific and useful.
- Match the business category.
- Use a peer-to-peer tone for merchants.
- Avoid generic "10% off" style marketing.
- Keep the message concise.
- Give the recipient a clear reason to respond.
- Do not mention internal fields such as suppression_key.
- Return only the message body.
"""

        response = self.llm_service.generate(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a precise Magicpin "
                        "engagement copywriter."
                        "Return only the message text. "
                        "Do not wrap the message in quotation marks."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
        ).strip()
        return response.strip('"').strip("'").strip()
    
    def _template_params(
        self,
        merchant,
        customer,
    ):

        params = []

        if customer:
            name = (
                customer.get("identity", {})
                .get("name")
            )

            if name:
                params.append(name)

        owner = (
            merchant.get("identity", {})
            .get("owner_first_name")
        )

        if owner:
            params.append(owner)

        return params

    def _determine_cta(
        self,
        trigger,
    ):

        kind = trigger.get("kind", "")

        action_triggers = {
            "recall_due",
            "customer_lapsed_soft",
            "customer_lapsed_hard",
            "perf_dip",
            "renewal_due",
            "unplanned_slot_open",
        }

        if kind in action_triggers:
            return "YES/STOP"

        return "open_ended"

    def _build_rationale(
        self,
        trigger,
        merchant,
    ):

        kind = trigger.get(
            "kind",
            "unknown",
        )

        merchant_name = (
            merchant.get("identity", {})
            .get("name", "merchant")
        )

        return (
            f"Triggered by {kind} for "
            f"{merchant_name}; message uses "
            "current merchant and trigger context."
        )

    def _is_expired(
        self,
        trigger,
        now,
    ):

        expires_at = trigger.get(
            "expires_at"
        )

        if not expires_at:
            return False

        try:
            expiry = datetime.fromisoformat(
                expires_at.replace(
                    "Z",
                    "+00:00",
                )
            )

            current = datetime.fromisoformat(
                now.replace(
                    "Z",
                    "+00:00",
                )
            )

            return current >= expiry

        except ValueError:
            return False