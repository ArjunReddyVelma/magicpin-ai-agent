import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.dependencies import get_db, get_current_merchant, get_llm_provider, verify_csrf
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.whatsapp import WhatsAppAccount, WhatsAppMessage
from backend.app.ai.context_retriever import ContextRetriever

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Business"])


def _cipher() -> Fernet:
    if not settings.WHATSAPP_ENCRYPTION_KEY:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "WHATSAPP_ENCRYPTION_NOT_CONFIGURED", "message": "Server-side WhatsApp encryption is not configured."}},
        )
    try:
        return Fernet(settings.WHATSAPP_ENCRYPTION_KEY.encode())
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "WHATSAPP_ENCRYPTION_KEY_INVALID", "message": "WhatsApp encryption key is invalid."}},
        ) from exc


class AccountSetup(BaseModel):
    phone_number_id: str = Field(min_length=1, max_length=80)
    business_account_id: Optional[str] = Field(default=None, max_length=80)
    access_token: str = Field(min_length=20, max_length=4096)

    @field_validator("phone_number_id")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Phone number ID cannot be empty.")
        return s

    @field_validator("business_account_id")
    @classmethod
    def validate_business_account(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            return s if s else None
        return None

    @field_validator("access_token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 20:
            raise ValueError("Access token must be at least 20 characters.")
        return s


class SendReply(BaseModel):
    reply_text: str = Field(min_length=1, max_length=4096)
    force: bool = Field(default=False)

    @field_validator("reply_text")
    @classmethod
    def validate_reply(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Reply text cannot be empty or whitespace only.")
        return s


def _account_status(account: Optional[WhatsAppAccount]) -> dict:
    return {
        "connected": bool(account),
        "phone_number_id": account.phone_number_id if account else None,
        "business_account_id": account.business_account_id if account else None,
        "created_at": account.created_at.isoformat() if account else None,
    }


@router.get("/account")
def get_account(merchant: MerchantProfile = Depends(get_current_merchant), db: Session = Depends(get_db)):
    account = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.merchant_id == merchant.id))
    return _account_status(account)


@router.put("/account")
def save_account(
    req: AccountSetup,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
):
    cipher = _cipher()
    encrypted = cipher.encrypt(req.access_token.encode()).decode()
    account = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.merchant_id == merchant.id))
    linked = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == req.phone_number_id))
    if linked and linked.merchant_id != merchant.id:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "PHONE_NUMBER_ALREADY_LINKED", "message": "This WhatsApp phone number is already linked to another merchant."}},
        )
    if account:
        account.phone_number_id = req.phone_number_id
        account.business_account_id = req.business_account_id
        account.access_token_encrypted = encrypted
    else:
        account = WhatsAppAccount(
            merchant_id=merchant.id,
            phone_number_id=req.phone_number_id,
            business_account_id=req.business_account_id,
            access_token_encrypted=encrypted,
        )
        db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "WHATSAPP_ACCOUNT_CONFLICT", "message": "The WhatsApp number is already linked."}},
        )
    db.refresh(account)
    return _account_status(account)


@router.get("/messages")
def list_messages(
    merchant: MerchantProfile = Depends(get_current_merchant),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    stmt = (
        select(WhatsAppMessage)
        .where(WhatsAppMessage.merchant_id == merchant.id)
        .order_by(WhatsAppMessage.received_at.desc(), WhatsAppMessage.id.desc())
    )
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [
            {
                "id": str(m.id),
                "customer_wa_id": m.customer_wa_id,
                "customer_name": m.customer_name,
                "inbound_text": m.inbound_text,
                "suggested_reply": m.suggested_reply,
                "status": m.status,
                "last_error": m.last_error,
                "received_at": m.received_at.isoformat(),
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            }
            for m in items
        ]
    }


@router.post("/messages/{message_id}/send")
def send_reply(
    message_id: uuid.UUID,
    req: SendReply,
    merchant: MerchantProfile = Depends(get_current_merchant),
    _: None = Depends(verify_csrf),
    db: Session = Depends(get_db),
):
    message = db.scalar(
        select(WhatsAppMessage)
        .where(
            WhatsAppMessage.id == message_id,
            WhatsAppMessage.merchant_id == merchant.id,
        )
        .with_for_update()
    )
    if not message:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "WHATSAPP_MESSAGE_NOT_FOUND", "message": "WhatsApp message not found."}},
        )

    if message.status == "sent":
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "ALREADY_SENT", "message": "This reply has already been sent."}},
        )

    if message.status == "sending":
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "SEND_IN_PROGRESS", "message": "This reply is currently being sent."}},
        )

    if message.status == "send_ambiguous" and not req.force:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "SEND_AMBIGUOUS",
                    "message": "Previous send timed out and outcome is unconfirmed. Check customer chat before confirming retry.",
                }
            },
        )

    account = db.scalar(
        select(WhatsAppAccount).where(
            WhatsAppAccount.merchant_id == merchant.id,
            WhatsAppAccount.phone_number_id == message.phone_number_id,
        )
    )
    if not account:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "WHATSAPP_ACCOUNT_MISSING", "message": "Connect a WhatsApp account before sending."}},
        )

    try:
        token = _cipher().decrypt(account.access_token_encrypted.encode()).decode()
    except (InvalidToken, Exception):
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "WHATSAPP_CREDENTIAL_ERROR", "message": "Could not decrypt WhatsApp credentials."}},
        )

    # Transition to sending and commit immediately to lock out concurrent requests
    message.status = "sending"
    db.commit()

    version = settings.WHATSAPP_GRAPH_API_VERSION
    url = f"https://graph.facebook.com/{version}/{account.phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": message.customer_wa_id,
        "type": "text",
        "text": {"preview_url": False, "body": req.reply_text},
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, headers=headers, json=payload)

        if response.is_error:
            err_msg = f"Meta API returned HTTP {response.status_code}"
            try:
                err_data = response.json().get("error", {})
                meta_code = err_data.get("code")
                meta_text = err_data.get("message")
                if meta_text:
                    err_msg = f"Meta error ({meta_code}): {meta_text}" if meta_code else f"Meta error: {meta_text}"
            except Exception:
                pass

            clean_err = err_msg[:300]
            msg = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.id == message_id))
            if msg:
                msg.status = "send_failed"
                msg.last_error = clean_err
                db.commit()
            raise HTTPException(
                status_code=502,
                detail={"error": {"code": "WHATSAPP_SEND_FAILED", "message": clean_err}},
            )

        resp_json = response.json()
        sent_messages = resp_json.get("messages") or []
        sent_id = sent_messages[0].get("id") if sent_messages else None
        if not sent_id:
            msg = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.id == message_id))
            if msg:
                msg.status = "send_failed"
                msg.last_error = "Meta response did not include a message ID."
                db.commit()
            raise HTTPException(
                status_code=502,
                detail={"error": {"code": "WHATSAPP_SEND_FAILED", "message": "Meta accepted request but returned no message ID."}},
            )

        msg = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.id == message_id))
        if msg:
            msg.status = "sent"
            msg.suggested_reply = req.reply_text
            msg.sent_provider_message_id = sent_id
            msg.sent_at = datetime.now(timezone.utc)
            msg.last_error = None
            db.commit()
            return {"id": str(msg.id), "status": msg.status, "sent_at": msg.sent_at.isoformat()}
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "DATABASE_ERROR", "message": "Message state update failed."}},
        )

    except HTTPException:
        raise
    except httpx.TimeoutException:
        db.rollback()
        msg = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.id == message_id))
        if msg:
            msg.status = "send_ambiguous"
            msg.last_error = "Network timeout waiting for Meta response. Delivery is unconfirmed; verify customer chat before retrying."
            db.commit()
        raise HTTPException(
            status_code=504,
            detail={
                "error": {
                    "code": "WHATSAPP_TIMEOUT",
                    "message": "Meta API request timed out. Message delivery is unconfirmed; check customer chat before retrying.",
                }
            },
        )
    except httpx.RequestError:
        db.rollback()
        msg = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.id == message_id))
        if msg:
            msg.status = "send_failed"
            msg.last_error = "Network connection to Meta API failed."
            db.commit()
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "WHATSAPP_NETWORK_ERROR", "message": "Could not connect to WhatsApp Meta API."}},
        )
    except Exception:
        db.rollback()
        msg = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.id == message_id))
        if msg and msg.status == "sending":
            msg.status = "send_failed"
            msg.last_error = "Unexpected error occurred during message send."
            db.commit()
        raise


@router.get("/webhook")
def verify_webhook(
    mode: Optional[str] = Query(None, alias="hub.mode"),
    verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    if (
        mode == "subscribe"
        and settings.WHATSAPP_VERIFY_TOKEN
        and hmac.compare_digest(verify_token or "", settings.WHATSAPP_VERIFY_TOKEN)
    ):
        return Response(content=challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not settings.WHATSAPP_APP_SECRET or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    expected = "sha256=" + hmac.new(settings.WHATSAPP_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            phone_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
            account = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == phone_id)) if phone_id else None
            if not account:
                continue

            contacts = {str(c.get("wa_id")): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            for incoming in value.get("messages", []):
                body = ((incoming.get("text") or {}).get("body") or "").strip()
                provider_id = incoming.get("id")
                sender = incoming.get("from")
                if incoming.get("type") != "text" or not body or not provider_id or not sender:
                    continue

                if db.scalar(select(WhatsAppMessage.id).where(WhatsAppMessage.provider_message_id == provider_id)):
                    continue

                msg = WhatsAppMessage(
                    merchant_id=account.merchant_id,
                    phone_number_id=phone_id,
                    provider_message_id=provider_id,
                    customer_wa_id=str(sender),
                    customer_name=contacts.get(str(sender)),
                    inbound_text=body,
                    suggested_reply="",
                    status="needs_review",
                )
                db.add(msg)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    continue

                # Grounded AI Draft Generation
                try:
                    context = ContextRetriever().retrieve_relevant_context(merchant_id=account.merchant_id, query=body, db=db)
                    context_blocks = [f"- {item.title}: {item.content}" for item in context]
                    context_text = "\n".join(context_blocks)
                    merchant_profile = db.get(MerchantProfile, account.merchant_id)
                    biz_name = merchant_profile.business_name if merchant_profile else "the store"

                    prompt = (
                        f"You are drafting a reviewable WhatsApp customer support reply for {biz_name}.\n"
                        "OPERATING RULES:\n"
                        "1. This is a draft proposal for the merchant to review and edit. You cannot and will not send any message.\n"
                        "2. Ground your reply strictly in the provided merchant context.\n"
                        "3. Never invent prices, availability, delivery timelines, policies, or promises not in the context.\n"
                        "4. If context does not have the answer, politely ask a clarifying question or advise contacting the store.\n"
                        "5. Keep the reply concise (1-3 sentences) and courteous.\n\n"
                        f"<merchant_context>\n{context_text or '(No relevant merchant context configured)'}\n</merchant_context>"
                    )
                    draft = get_llm_provider().generate_response(
                        prompt,
                        [{"role": "user", "content": body}],
                        max_tokens=240,
                        temperature=0.3,
                    ).content.strip()[:4096]

                    msg.suggested_reply = draft or "Thank you for contacting us. Could you please share a little more detail so we can help?"
                    db.commit()
                except Exception:
                    db.rollback()
                    msg = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.provider_message_id == provider_id))
                    if msg:
                        msg.suggested_reply = "Thank you for contacting us. Could you please share a little more detail so we can help?"
                        db.commit()

    return {"status": "ok"}
