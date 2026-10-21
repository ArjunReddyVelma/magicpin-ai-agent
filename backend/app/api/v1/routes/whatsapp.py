import hashlib, hmac, json, uuid
from datetime import datetime, timezone
from typing import Optional
import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
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
        raise HTTPException(status_code=503, detail={"error":{"code":"WHATSAPP_ENCRYPTION_NOT_CONFIGURED","message":"Server-side WhatsApp encryption is not configured."}})
    try: return Fernet(settings.WHATSAPP_ENCRYPTION_KEY.encode())
    except Exception as exc: raise HTTPException(status_code=503, detail={"error":{"code":"WHATSAPP_ENCRYPTION_KEY_INVALID","message":"WhatsApp encryption key is invalid."}}) from exc

class AccountSetup(BaseModel):
    phone_number_id: str = Field(min_length=1, max_length=80)
    business_account_id: Optional[str] = Field(default=None, max_length=80)
    access_token: str = Field(min_length=20, max_length=4096)
class SendReply(BaseModel):
    reply_text: str = Field(min_length=1, max_length=4096)

def _account_status(account):
    return {"connected": bool(account), "phone_number_id": account.phone_number_id if account else None, "business_account_id": account.business_account_id if account else None, "created_at": account.created_at.isoformat() if account else None}

@router.get("/account")
def get_account(merchant: MerchantProfile = Depends(get_current_merchant), db: Session = Depends(get_db)):
    account = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.merchant_id == merchant.id))
    return _account_status(account)

@router.put("/account")
def save_account(req: AccountSetup, merchant: MerchantProfile = Depends(get_current_merchant), _: None = Depends(verify_csrf), db: Session = Depends(get_db)):
    encrypted = _cipher().encrypt(req.access_token.encode()).decode()
    account = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.merchant_id == merchant.id))
    linked = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id == req.phone_number_id))
    if linked and linked.merchant_id != merchant.id:
        raise HTTPException(status_code=409, detail={"error":{"code":"PHONE_NUMBER_ALREADY_LINKED","message":"This WhatsApp phone number is already linked to another merchant."}})
    if account:
        account.phone_number_id, account.business_account_id, account.access_token_encrypted = req.phone_number_id, req.business_account_id, encrypted
    else:
        account = WhatsAppAccount(merchant_id=merchant.id, phone_number_id=req.phone_number_id, business_account_id=req.business_account_id, access_token_encrypted=encrypted)
        db.add(account)
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(status_code=409, detail={"error":{"code":"WHATSAPP_ACCOUNT_CONFLICT","message":"The WhatsApp number is already linked."}})
    db.refresh(account)
    return _account_status(account)

@router.get("/messages")
def list_messages(merchant: MerchantProfile = Depends(get_current_merchant), db: Session = Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    stmt = select(WhatsAppMessage).where(WhatsAppMessage.merchant_id == merchant.id).order_by(WhatsAppMessage.received_at.desc())
    items = db.scalars(stmt.offset((page-1)*page_size).limit(page_size)).all()
    return {"items":[{"id":str(m.id),"customer_wa_id":m.customer_wa_id,"customer_name":m.customer_name,"inbound_text":m.inbound_text,"suggested_reply":m.suggested_reply,"status":m.status,"last_error":m.last_error,"received_at":m.received_at.isoformat(),"sent_at":m.sent_at.isoformat() if m.sent_at else None} for m in items]}

@router.post("/messages/{message_id}/send")
def send_reply(message_id: uuid.UUID, req: SendReply, merchant: MerchantProfile = Depends(get_current_merchant), _: None = Depends(verify_csrf), db: Session = Depends(get_db)):
    message = db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.id == message_id, WhatsAppMessage.merchant_id == merchant.id))
    if not message: raise HTTPException(status_code=404, detail={"error":{"code":"WHATSAPP_MESSAGE_NOT_FOUND","message":"WhatsApp message not found."}})
    if message.status == "sent": raise HTTPException(status_code=409, detail={"error":{"code":"ALREADY_SENT","message":"This reply has already been sent."}})
    account = db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.merchant_id == merchant.id, WhatsAppAccount.phone_number_id == message.phone_number_id))
    if not account: raise HTTPException(status_code=409, detail={"error":{"code":"WHATSAPP_ACCOUNT_MISSING","message":"Connect a WhatsApp account before sending."}})
    try:
        token = _cipher().decrypt(account.access_token_encrypted.encode()).decode()
        version = settings.WHATSAPP_GRAPH_API_VERSION
        with httpx.Client(timeout=15.0) as client:
            response = client.post(f"https://graph.facebook.com/{version}/{account.phone_number_id}/messages", headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"}, json={"messaging_product":"whatsapp","recipient_type":"individual","to":message.customer_wa_id,"type":"text","text":{"preview_url":False,"body":req.reply_text}})
        if response.is_error:
            message.status="send_failed"; message.last_error=f"Meta API returned HTTP {response.status_code}"; db.commit()
            raise HTTPException(status_code=502, detail={"error":{"code":"WHATSAPP_SEND_FAILED","message":"Meta rejected the message. Check the connection and retry."}})
        payload=response.json(); sent=(payload.get("messages") or [{}])[0].get("id")
        if not sent: raise ValueError("Meta response did not include a message ID")
        message.status="sent"; message.suggested_reply=req.reply_text; message.sent_provider_message_id=sent; message.sent_at=datetime.now(timezone.utc); message.last_error=None
        db.commit(); return {"id":str(message.id),"status":message.status,"sent_at":message.sent_at.isoformat()}
    except HTTPException: raise
    except (httpx.HTTPError, ValueError, InvalidToken):
        db.rollback(); message=db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.id==message_id, WhatsAppMessage.merchant_id==merchant.id))
        if message: message.status="send_failed"; message.last_error="WhatsApp send request failed; verify the account configuration before retrying."; db.commit()
        raise HTTPException(status_code=502, detail={"error":{"code":"WHATSAPP_SEND_FAILED","message":"Could not send through WhatsApp. Check configuration and retry."}})

@router.get("/webhook")
def verify_webhook(mode: Optional[str] = Query(None, alias="hub.mode"), verify_token: Optional[str] = Query(None, alias="hub.verify_token"), challenge: Optional[str] = Query(None, alias="hub.challenge")):
    if mode == "subscribe" and settings.WHATSAPP_VERIFY_TOKEN and hmac.compare_digest(verify_token or "", settings.WHATSAPP_VERIFY_TOKEN): return Response(content=challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Webhook verification failed")

@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body(); signature=request.headers.get("X-Hub-Signature-256", "")
    if not settings.WHATSAPP_APP_SECRET or not signature.startswith("sha256="): raise HTTPException(status_code=401, detail="Invalid webhook signature")
    expected="sha256="+hmac.new(settings.WHATSAPP_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected): raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try: payload=json.loads(raw)
    except json.JSONDecodeError: raise HTTPException(status_code=400, detail="Invalid JSON")
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value=change.get("value") or {}; phone_id=str((value.get("metadata") or {}).get("phone_number_id") or "")
            account=db.scalar(select(WhatsAppAccount).where(WhatsAppAccount.phone_number_id==phone_id)) if phone_id else None
            if not account: continue
            contacts={str(c.get("wa_id")): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            for incoming in value.get("messages", []):
                body=((incoming.get("text") or {}).get("body") or "").strip(); provider_id=incoming.get("id"); sender=incoming.get("from")
                if incoming.get("type") != "text" or not body or not provider_id or not sender: continue
                if db.scalar(select(WhatsAppMessage.id).where(WhatsAppMessage.provider_message_id==provider_id)): continue
                msg=WhatsAppMessage(merchant_id=account.merchant_id,phone_number_id=phone_id,provider_message_id=provider_id,customer_wa_id=str(sender),customer_name=contacts.get(str(sender)),inbound_text=body,suggested_reply="",status="needs_review")
                db.add(msg)
                try: db.commit()
                except IntegrityError: db.rollback(); continue
                try:
                    context=ContextRetriever().retrieve_relevant_context(merchant_id=account.merchant_id, query=body, db=db)
                    context_text="\n".join(f"- {item.title}: {item.content}" for item in context)
                    merchant_profile=db.get(MerchantProfile, account.merchant_id)
                    prompt=("Draft a concise, polite WhatsApp customer-support reply. Use only the supplied business context; never invent prices, policies, availability, or promises. If context is insufficient, ask a clarifying question. This is a draft only; never send a message.\n" + f"Business: {merchant_profile.business_name if merchant_profile else 'merchant'}\nContext:\n{context_text or '(No relevant merchant context provided)'}")
                    draft=get_llm_provider().generate_response(prompt,[{"role":"user","content":body}],max_tokens=240,temperature=0.3).content.strip()[:4096]
                    msg.suggested_reply=draft or "Thank you for contacting us. Could you please share a little more detail so we can help?"; db.commit()
                except Exception:
                    db.rollback(); msg=db.scalar(select(WhatsAppMessage).where(WhatsAppMessage.provider_message_id==provider_id))
                    if msg: msg.suggested_reply="Thank you for contacting us. Could you please share a little more detail so we can help?"; db.commit()
    return {"status":"ok"}
