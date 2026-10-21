import hashlib
import hmac
import json
import uuid
import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.core.config import settings
from backend.app.models.whatsapp import WhatsAppMessage


def test_whatsapp_webhook_verification_challenge(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "test-verify-token")
    response = client.get(
        "/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "challenge-value",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge-value"


def test_whatsapp_webhook_verification_rejects_wrong_token(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "test-verify-token")
    response = client.get(
        "/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "challenge-value",
        },
    )
    assert response.status_code == 403


def test_whatsapp_webhook_rejects_invalid_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    response = client.post(
        "/v1/whatsapp/webhook",
        content=json.dumps({"object": "whatsapp_business_account"}),
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )
    assert response.status_code == 401


def test_whatsapp_webhook_rejects_missing_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    response = client.post(
        "/v1/whatsapp/webhook",
        json={"object": "whatsapp_business_account"},
    )
    assert response.status_code == 401


def test_whatsapp_message_provider_message_id_database_uniqueness(db_session, client):
    reg_resp = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_unique_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "WA Merchant",
            "business_name": "WA Store",
            "category": "Retail",
        },
    )
    assert reg_resp.status_code == 201
    merchant_id = uuid.UUID(reg_resp.json()["merchant"]["id"])

    # First message with unique provider_message_id
    msg1 = WhatsAppMessage(
        merchant_id=merchant_id,
        phone_number_id="phone-1",
        provider_message_id="wamid.HBgLMTIzNDU2Nzg5",
        customer_wa_id="919876543210",
        inbound_text="First message",
    )
    db_session.add(msg1)
    db_session.flush()

    # Second message with identical provider_message_id must violate unique constraint
    msg2 = WhatsAppMessage(
        merchant_id=merchant_id,
        phone_number_id="phone-1",
        provider_message_id="wamid.HBgLMTIzNDU2Nzg5",
        customer_wa_id="919876543210",
        inbound_text="Duplicate message",
    )
    db_session.add(msg2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_whatsapp_webhook_idempotent_duplicate_processing(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    # Register merchant and connect account
    reg_resp = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_idem_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Idem Merchant",
            "business_name": "Idem Store",
            "category": "Retail",
        },
    )
    assert reg_resp.status_code == 201
    csrf_token = reg_resp.json()["csrf_token"]

    account_resp = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "phone_number_id": "phone-idem-1",
            "access_token": "EAAX_valid_mock_token_at_least_20_chars",
        },
    )
    assert account_resp.status_code == 200

    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "biz-1",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "phone-idem-1"},
                            "contacts": [{"wa_id": "919999999999", "profile": {"name": "Test Customer"}}],
                            "messages": [
                                {
                                    "from": "919999999999",
                                    "id": "wamid.idem_test_turn_1",
                                    "type": "text",
                                    "text": {"body": "Hello, need help!"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    })
    signature = "sha256=" + hmac.new("test-app-secret".encode(), payload.encode(), hashlib.sha256).hexdigest()

    # First delivery
    r1 = client.post("/v1/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})
    assert r1.status_code == 200

    # Second delivery (replay with same provider_message_id)
    r2 = client.post("/v1/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})
    assert r2.status_code == 200

    # Verify only 1 message exists in inbox
    inbox_resp = client.get("/v1/whatsapp/messages")
    assert inbox_resp.status_code == 200
    assert len(inbox_resp.json()["items"]) == 1
