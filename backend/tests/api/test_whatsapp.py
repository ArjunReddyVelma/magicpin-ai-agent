import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError

from backend.app.core.config import settings
from backend.app.core import dependencies
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


def test_whatsapp_account_tenant_isolation_and_no_credential_leak(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    # Merchant 1
    m1_resp = client.post(
        "/v1/auth/register",
        json={
            "email": f"m1_wa_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Merchant One",
            "business_name": "Store One",
            "category": "Retail",
        },
    )
    assert m1_resp.status_code == 201
    csrf1 = m1_resp.json()["csrf_token"]

    save_resp = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf1},
        json={
            "phone_number_id": "phone-isolated-1",
            "business_account_id": "biz-iso-1",
            "access_token": "EAAX_valid_token_at_least_20_chars",
        },
    )
    assert save_resp.status_code == 200
    save_data = save_resp.json()
    assert save_data["connected"] is True
    assert save_data["phone_number_id"] == "phone-isolated-1"
    # Never return access token
    assert "access_token" not in save_data
    assert "access_token_encrypted" not in save_data

    # Merchant 1 GET account
    get_resp = client.get("/v1/whatsapp/account")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["connected"] is True
    assert "access_token" not in get_data
    assert "access_token_encrypted" not in get_data

    # Merchant 2
    client.cookies.clear()
    m2_resp = client.post(
        "/v1/auth/register",
        json={
            "email": f"m2_wa_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Merchant Two",
            "business_name": "Store Two",
            "category": "Retail",
        },
    )
    assert m2_resp.status_code == 201
    csrf2 = m2_resp.json()["csrf_token"]

    # Merchant 2 has no account
    m2_acct = client.get("/v1/whatsapp/account").json()
    assert m2_acct["connected"] is False

    # Merchant 2 cannot hijack Merchant 1's phone number
    hijack_resp = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf2},
        json={
            "phone_number_id": "phone-isolated-1",
            "access_token": "EAAX_another_valid_token_20_chars",
        },
    )
    assert hijack_resp.status_code == 409
    assert hijack_resp.json()["error"]["code"] == "PHONE_NUMBER_ALREADY_LINKED"


def test_whatsapp_inbox_and_send_tenant_isolation(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    # Setup Merchant 1
    m1_resp = client.post(
        "/v1/auth/register",
        json={
            "email": f"m1_inbox_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Inbox Merchant 1",
            "business_name": "Inbox Store 1",
            "category": "Retail",
        },
    )
    assert m1_resp.status_code == 201
    csrf1 = m1_resp.json()["csrf_token"]
    phone_id = f"phone-iso-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf1},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    # Deliver message to Merchant 1
    provider_id = f"wamid.iso_{uuid.uuid4().hex[:8]}"
    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "biz-1",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_id},
                    "contacts": [{"wa_id": "918888888888", "profile": {"name": "Customer"}}],
                    "messages": [{"from": "918888888888", "id": provider_id, "type": "text", "text": {"body": "Secret info"}}],
                },
                "field": "messages",
            }],
        }],
    })
    sig = "sha256=" + hmac.new("test-app-secret".encode(), payload.encode(), hashlib.sha256).hexdigest()
    client.post("/v1/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})

    # Merchant 1 sees the message
    m1_inbox = client.get("/v1/whatsapp/messages").json()
    assert len(m1_inbox["items"]) >= 1
    m1_msg_id = m1_inbox["items"][0]["id"]

    # Merchant 2 registers and checks inbox
    client.cookies.clear()
    m2_resp = client.post(
        "/v1/auth/register",
        json={
            "email": f"m2_inbox_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Inbox Merchant 2",
            "business_name": "Inbox Store 2",
            "category": "Retail",
        },
    )
    assert m2_resp.status_code == 201
    csrf2 = m2_resp.json()["csrf_token"]

    # Merchant 2 inbox is empty (tenant isolation)
    m2_inbox = client.get("/v1/whatsapp/messages").json()
    assert len(m2_inbox["items"]) == 0

    # Merchant 2 cannot send a reply to Merchant 1's message (returns 404)
    cross_send = client.post(
        f"/v1/whatsapp/messages/{m1_msg_id}/send",
        headers={"X-CSRF-Token": csrf2},
        json={"reply_text": "Unauthorized reply attempt"},
    )
    assert cross_send.status_code == 404
    assert cross_send.json()["error"]["code"] == "WHATSAPP_MESSAGE_NOT_FOUND"


def test_whatsapp_encryption_configuration_failures(client, monkeypatch):
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"enc_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Enc Merchant",
            "business_name": "Enc Store",
            "category": "Retail",
        },
    )
    csrf = reg.json()["csrf_token"]

    # 1. Encryption not configured
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "")
    r1 = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": "phone-enc-1", "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )
    assert r1.status_code == 503
    assert r1.json()["error"]["code"] == "WHATSAPP_ENCRYPTION_NOT_CONFIGURED"

    # 2. Encryption key invalid
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "invalid-key-not-fernet")
    r2 = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": "phone-enc-1", "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )
    assert r2.status_code == 503
    assert r2.json()["error"]["code"] == "WHATSAPP_ENCRYPTION_KEY_INVALID"


def test_whatsapp_send_success_and_already_sent(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "live")
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"send_ok_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Send Merchant",
            "business_name": "Send Store",
            "category": "Retail",
        },
    )
    csrf = reg.json()["csrf_token"]
    phone_id = f"phone-send-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    prov_id = f"wamid.send_test_{uuid.uuid4().hex[:8]}"
    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "biz-1",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_id},
                    "contacts": [{"wa_id": "917777777777", "profile": {"name": "Customer"}}],
                    "messages": [{"from": "917777777777", "id": prov_id, "type": "text", "text": {"body": "Store hours?"}}],
                },
                "field": "messages",
            }],
        }],
    })
    sig = "sha256=" + hmac.new("test-app-secret".encode(), payload.encode(), hashlib.sha256).hexdigest()
    client.post("/v1/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})

    inbox = client.get("/v1/whatsapp/messages").json()
    msg_id = inbox["items"][0]["id"]

    # Mock Meta API successful response
    def mock_post(self, url, headers=None, json=None):
        return httpx.Response(
            status_code=200,
            json={"messaging_product": "whatsapp", "contacts": [{"input": "917777777777", "wa_id": "917777777777"}], "messages": [{"id": "wamid.meta_sent_999"}]},
            request=httpx.Request("POST", url),
        )
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    send_resp = client.post(
        f"/v1/whatsapp/messages/{msg_id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "We are open 9am to 9pm daily!"},
    )
    assert send_resp.status_code == 200
    assert send_resp.json()["status"] == "sent"
    assert send_resp.json()["sent_at"] is not None

    # Sending again on already-sent message must return 409 ALREADY_SENT
    second_send = client.post(
        f"/v1/whatsapp/messages/{msg_id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "We are open 9am to 9pm daily!"},
    )
    assert second_send.status_code == 409
    assert second_send.json()["error"]["code"] == "ALREADY_SENT"


def test_whatsapp_send_in_progress_concurrency_lock(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"send_prog_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Progress Merchant",
            "business_name": "Progress Store",
            "category": "Retail",
        },
    )
    csrf = reg.json()["csrf_token"]
    phone_id = f"phone-prog-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    prov_id = f"wamid.prog_{uuid.uuid4().hex[:8]}"
    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "biz-1",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_id},
                    "contacts": [{"wa_id": "917777777777"}],
                    "messages": [{"from": "917777777777", "id": prov_id, "type": "text", "text": {"body": "Hi"}}],
                },
                "field": "messages",
            }],
        }],
    })
    sig = "sha256=" + hmac.new("test-app-secret".encode(), payload.encode(), hashlib.sha256).hexdigest()
    client.post("/v1/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})

    inbox = client.get("/v1/whatsapp/messages").json()
    msg_id = inbox["items"][0]["id"]

    # Manually mark as sending
    db_msg = db_session.get(WhatsAppMessage, uuid.UUID(msg_id))
    db_msg.status = "sending"
    db_session.commit()

    resp = client.post(
        f"/v1/whatsapp/messages/{msg_id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Concurrent attempt"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SEND_IN_PROGRESS"


def test_whatsapp_send_meta_rejection_captures_error(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "live")
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"send_meta_err_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Err Merchant",
            "business_name": "Err Store",
            "category": "Retail",
        },
    )
    csrf = reg.json()["csrf_token"]
    phone_id = f"phone-err-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    prov_id = f"wamid.meta_err_{uuid.uuid4().hex[:8]}"
    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "biz-1",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_id},
                    "contacts": [{"wa_id": "917777777777"}],
                    "messages": [{"from": "917777777777", "id": prov_id, "type": "text", "text": {"body": "Old message"}}],
                },
                "field": "messages",
            }],
        }],
    })
    sig = "sha256=" + hmac.new("test-app-secret".encode(), payload.encode(), hashlib.sha256).hexdigest()
    client.post("/v1/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})

    inbox = client.get("/v1/whatsapp/messages").json()
    msg_id = inbox["items"][0]["id"]

    # Mock Meta API rejection (e.g. 24h window closed)
    def mock_post_err(self, url, headers=None, json=None):
        return httpx.Response(
            status_code=400,
            json={"error": {"code": 131047, "message": "Message failed to send because customer window is closed"}},
            request=httpx.Request("POST", url),
        )
    monkeypatch.setattr(httpx.Client, "post", mock_post_err)

    send_resp = client.post(
        f"/v1/whatsapp/messages/{msg_id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Late reply"},
    )
    assert send_resp.status_code == 502
    assert send_resp.json()["error"]["code"] == "WHATSAPP_SEND_FAILED"

    # Verify message state in DB
    db_session.expire_all()
    db_msg = db_session.get(WhatsAppMessage, uuid.UUID(msg_id))
    assert db_msg.status == "send_failed"
    assert "131047" in db_msg.last_error


def test_whatsapp_send_timeout_marks_ambiguous_and_requires_force(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "live")
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"send_time_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Time Merchant",
            "business_name": "Time Store",
            "category": "Retail",
        },
    )
    csrf = reg.json()["csrf_token"]
    phone_id = f"phone-time-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    prov_id = f"wamid.timeout_{uuid.uuid4().hex[:8]}"
    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "biz-1",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_id},
                    "contacts": [{"wa_id": "917777777777"}],
                    "messages": [{"from": "917777777777", "id": prov_id, "type": "text", "text": {"body": "Order query"}}],
                },
                "field": "messages",
            }],
        }],
    })
    sig = "sha256=" + hmac.new("test-app-secret".encode(), payload.encode(), hashlib.sha256).hexdigest()
    client.post("/v1/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})

    inbox = client.get("/v1/whatsapp/messages").json()
    msg_id = inbox["items"][0]["id"]

    # 1. Simulate network timeout
    def mock_timeout(self, url, headers=None, json=None):
        raise httpx.ReadTimeout("Timeout waiting for Meta response", request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.Client, "post", mock_timeout)

    send_resp = client.post(
        f"/v1/whatsapp/messages/{msg_id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "First attempt that times out"},
    )
    assert send_resp.status_code == 504
    assert send_resp.json()["error"]["code"] == "WHATSAPP_TIMEOUT"

    # Verify message is marked send_ambiguous in DB
    db_session.expire_all()
    db_msg = db_session.get(WhatsAppMessage, uuid.UUID(msg_id))
    assert db_msg.status == "send_ambiguous"
    assert "timeout" in db_msg.last_error.lower()

    # 2. Retrying without force=True must return 409 SEND_AMBIGUOUS
    retry_without_force = client.post(
        f"/v1/whatsapp/messages/{msg_id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Second attempt without force"},
    )
    assert retry_without_force.status_code == 409
    assert retry_without_force.json()["error"]["code"] == "SEND_AMBIGUOUS"

    # 3. Retrying with force=True succeeds once Meta responds
    def mock_post_ok(self, url, headers=None, json=None):
        return httpx.Response(
            status_code=200,
            json={"messages": [{"id": "wamid.force_retry_ok_123"}]},
            request=httpx.Request("POST", url),
        )
    monkeypatch.setattr(httpx.Client, "post", mock_post_ok)

    retry_with_force = client.post(
        f"/v1/whatsapp/messages/{msg_id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Confirmed retry attempt", "force": True},
    )
    assert retry_with_force.status_code == 200
    assert retry_with_force.json()["status"] == "sent"


def test_whatsapp_ai_draft_failure_fallback(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    # Monkeypatch LLM provider to raise error
    class BrokenLLMProvider:
        def generate_response(self, *args, **kwargs):
            raise RuntimeError("Groq/LLM service is offline")
    monkeypatch.setattr("backend.app.api.v1.routes.whatsapp.get_llm_provider", lambda: BrokenLLMProvider())

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"ai_fail_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "AI Merchant",
            "business_name": "AI Store",
            "category": "Retail",
        },
    )
    csrf = reg.json()["csrf_token"]
    phone_id = f"phone-ai-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    prov_id = f"wamid.ai_fail_{uuid.uuid4().hex[:8]}"
    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "biz-1",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": phone_id},
                    "contacts": [{"wa_id": "917777777777"}],
                    "messages": [{"from": "917777777777", "id": prov_id, "type": "text", "text": {"body": "Need pricing"}}],
                },
                "field": "messages",
            }],
        }],
    })
    sig = "sha256=" + hmac.new("test-app-secret".encode(), payload.encode(), hashlib.sha256).hexdigest()

    # Webhook still returns 200 without error
    resp = client.post("/v1/whatsapp/webhook", content=payload, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200

    # Message is saved with safe fallback draft and status needs_review
    inbox = client.get("/v1/whatsapp/messages").json()
    assert len(inbox["items"]) == 1
    item = inbox["items"][0]
    assert item["status"] == "needs_review"
    assert "Thank you for contacting us" in item["suggested_reply"]


def test_whatsapp_validation_rejects_empty_reply_and_bad_account(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"val_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Val Merchant",
            "business_name": "Val Store",
            "category": "Retail",
        },
    )
    csrf = reg.json()["csrf_token"]

    # Whitespace only phone_number_id
    r1 = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": "   ", "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )
    assert r1.status_code == 422

    # Short token
    r2 = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": "valid-phone", "access_token": "too-short"},
    )
    assert r2.status_code == 422

    # Valid account setup
    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": "valid-phone-123", "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    # Whitespace-only reply
    r3 = client.post(
        f"/v1/whatsapp/messages/{uuid.uuid4()}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "    "},
    )
    assert r3.status_code == 422


def test_whatsapp_stale_sending_recovered_to_send_ambiguous_in_list_messages(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"stale_list_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Stale List Merchant",
            "business_name": "Stale List Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201
    csrf = reg.json()["csrf_token"]
    merchant_id = uuid.UUID(reg.json()["merchant"]["id"])
    phone_id = f"phone-stale-list-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    # Insert a message stuck in 'sending' older than 120s (e.g. 180s ago)
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=180)
    msg = WhatsAppMessage(
        merchant_id=merchant_id,
        phone_number_id=phone_id,
        provider_message_id=f"wamid.stale_list_{uuid.uuid4().hex[:8]}",
        customer_wa_id="919876543211",
        customer_name="Stuck Customer",
        inbound_text="Help needed",
        suggested_reply="Draft reply",
        status="sending",
    )
    db_session.add(msg)
    db_session.commit()

    # Manually backdate updated_at to simulate process crash 3 minutes ago
    msg.updated_at = stale_time
    db_session.commit()

    # Listing messages should recover the stuck message to send_ambiguous
    inbox_resp = client.get("/v1/whatsapp/messages")
    assert inbox_resp.status_code == 200
    items = inbox_resp.json()["items"]
    assert len(items) == 1
    recovered = items[0]
    assert recovered["id"] == str(msg.id)
    assert recovered["status"] == "send_ambiguous"
    assert "interrupted by a server restart or timeout" in recovered["last_error"]

    # Verify persisted in database
    db_session.expire_all()
    reloaded = db_session.get(WhatsAppMessage, msg.id)
    assert reloaded.status == "send_ambiguous"


def test_whatsapp_stale_sending_recovered_in_send_reply_and_requires_force(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "live")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"stale_send_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Stale Send Merchant",
            "business_name": "Stale Send Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201
    csrf = reg.json()["csrf_token"]
    merchant_id = uuid.UUID(reg.json()["merchant"]["id"])
    phone_id = f"phone-stale-send-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    # Insert message stuck in 'sending' older than 120s
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=200)
    msg = WhatsAppMessage(
        merchant_id=merchant_id,
        phone_number_id=phone_id,
        provider_message_id=f"wamid.stale_send_{uuid.uuid4().hex[:8]}",
        customer_wa_id="919876543212",
        customer_name="Retry Customer",
        inbound_text="Need assistance",
        suggested_reply="Ready to reply",
        status="sending",
    )
    db_session.add(msg)
    db_session.commit()

    msg.updated_at = stale_time
    db_session.commit()

    # Sending without force=True must recover from 'sending' to 'send_ambiguous' and return 409 SEND_AMBIGUOUS
    retry_no_force = client.post(
        f"/v1/whatsapp/messages/{msg.id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Retrying after crash"},
    )
    assert retry_no_force.status_code == 409
    assert retry_no_force.json()["error"]["code"] == "SEND_AMBIGUOUS"

    db_session.expire_all()
    reloaded = db_session.get(WhatsAppMessage, msg.id)
    assert reloaded.status == "send_ambiguous"

    # Retrying with force=True succeeds once Meta responds
    def mock_meta_send(self, url, headers=None, json=None):
        return httpx.Response(
            status_code=200,
            json={"messages": [{"id": "wamid.recovered_send_ok_456"}]},
            request=httpx.Request("POST", url),
        )
    monkeypatch.setattr(httpx.Client, "post", mock_meta_send)

    retry_with_force = client.post(
        f"/v1/whatsapp/messages/{msg.id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Retrying with explicit confirmation", "force": True},
    )
    assert retry_with_force.status_code == 200
    assert retry_with_force.json()["status"] == "sent"

    db_session.expire_all()
    final_msg = db_session.get(WhatsAppMessage, msg.id)
    assert final_msg.status == "sent"
    assert final_msg.sent_provider_message_id == "wamid.recovered_send_ok_456"


def test_whatsapp_active_sending_not_recovered_as_stale(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"active_send_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Active Send Merchant",
            "business_name": "Active Send Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201
    csrf = reg.json()["csrf_token"]
    merchant_id = uuid.UUID(reg.json()["merchant"]["id"])
    phone_id = f"phone-active-send-{uuid.uuid4().hex[:6]}"

    client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )

    # Insert a message actively sending (only 10 seconds ago)
    recent_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    msg = WhatsAppMessage(
        merchant_id=merchant_id,
        phone_number_id=phone_id,
        provider_message_id=f"wamid.active_send_{uuid.uuid4().hex[:8]}",
        customer_wa_id="919876543213",
        customer_name="Active Customer",
        inbound_text="Still sending",
        suggested_reply="Please wait",
        status="sending",
    )
    db_session.add(msg)
    db_session.commit()

    msg.updated_at = recent_time
    db_session.commit()

    # Sending should still return 409 SEND_IN_PROGRESS (active concurrency lock)
    send_resp = client.post(
        f"/v1/whatsapp/messages/{msg.id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Concurrent attempt"},
    )
    assert send_resp.status_code == 409
    assert send_resp.json()["error"]["code"] == "SEND_IN_PROGRESS"

    # Inbox listing should still report 'sending'
    inbox_resp = client.get("/v1/whatsapp/messages")
    assert inbox_resp.status_code == 200
    items = inbox_resp.json()["items"]
    assert items[0]["status"] == "sending"


def test_whatsapp_account_reports_mode(client, monkeypatch):
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_mode_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Mode Test Merchant",
            "business_name": "Mode Test Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201

    monkeypatch.setattr(settings, "WHATSAPP_MODE", "live")
    resp_live = client.get("/v1/whatsapp/account")
    assert resp_live.status_code == 200
    assert resp_live.json()["mode"] == "live"

    monkeypatch.setattr(settings, "WHATSAPP_MODE", "mock")
    resp_mock = client.get("/v1/whatsapp/account")
    assert resp_mock.status_code == 200
    assert resp_mock.json()["mode"] == "mock"


def test_whatsapp_mock_send_skips_meta_and_succeeds(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "mock")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_mock_send_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Mock Send Merchant",
            "business_name": "Mock Send Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201
    csrf = reg.json()["csrf_token"]
    merchant_id = uuid.UUID(reg.json()["merchant"]["id"])
    phone_id = f"phone-mock-send-{uuid.uuid4().hex[:6]}"

    # Account setup properly uses Fernet to encrypt token at rest
    account_setup_resp = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={"phone_number_id": phone_id, "access_token": "EAAX_valid_mock_token_at_least_20_chars"},
    )
    assert account_setup_resp.status_code == 200

    # Insert an inbound message awaiting merchant review
    msg = WhatsAppMessage(
        merchant_id=merchant_id,
        phone_number_id=phone_id,
        provider_message_id=f"wamid.sim_{uuid.uuid4().hex[:12]}",
        customer_wa_id="919876543210",
        customer_name="Mock Customer",
        inbound_text="Is this item currently in stock?",
        suggested_reply="Yes, it is in stock at our main branch.",
        status="needs_review",
    )
    db_session.add(msg)
    db_session.commit()

    # Spy and fail on HTTP boundary (httpx.Client.post, request, send, httpx.post)
    outbound_http_calls = []
    def record_and_fail_http(*args, **kwargs):
        outbound_http_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("Outbound HTTP request was unexpectedly attempted during mock send!")

    monkeypatch.setattr(httpx.Client, "post", record_and_fail_http)
    monkeypatch.setattr(httpx.Client, "request", record_and_fail_http)
    monkeypatch.setattr(httpx.Client, "send", record_and_fail_http)
    monkeypatch.setattr(httpx, "post", record_and_fail_http)

    # Spy and fail on cipher / token decryption boundary
    decryption_calls = []
    def record_and_fail_cipher(*args, **kwargs):
        decryption_calls.append(args)
        raise AssertionError("Token decryption / cipher construction was unexpectedly invoked during mock send!")

    monkeypatch.setattr("backend.app.api.v1.routes.whatsapp._cipher", record_and_fail_cipher)
    monkeypatch.setattr(Fernet, "decrypt", record_and_fail_cipher)

    # Approve and send reply in mock mode
    send_resp = client.post(
        f"/v1/whatsapp/messages/{msg.id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Yes, we have 5 units left in stock today."},
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["status"] == "sent"
    assert send_data["sent_at"] is not None

    # Exact boundary assertions proving zero HTTP and zero decryption invocations
    assert len(outbound_http_calls) == 0, f"Expected 0 outbound HTTP calls, got {len(outbound_http_calls)}"
    assert len(decryption_calls) == 0, f"Expected 0 token decryption calls, got {len(decryption_calls)}"

    # Verify message in database
    db_session.expire_all()
    updated = db_session.get(WhatsAppMessage, msg.id)
    assert updated.status == "sent"
    assert updated.suggested_reply == "Yes, we have 5 units left in stock today."
    assert updated.sent_provider_message_id.startswith("wamid.mock_")
    assert updated.sent_at is not None
    assert updated.last_error is None



def test_whatsapp_mock_send_skips_decryption(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "mock")
    # Deliberately clear encryption key to prove cipher/decryption is never called
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_mock_cipher_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "No Key Merchant",
            "business_name": "No Key Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201
    csrf = reg.json()["csrf_token"]
    merchant_id = uuid.UUID(reg.json()["merchant"]["id"])
    phone_id = f"phone-no-cipher-{uuid.uuid4().hex[:6]}"

    # Insert message directly without valid account/encryption
    msg = WhatsAppMessage(
        merchant_id=merchant_id,
        phone_number_id=phone_id,
        provider_message_id=f"wamid.sim_{uuid.uuid4().hex[:12]}",
        customer_wa_id="919876543210",
        customer_name="Cipher Test Customer",
        inbound_text="Checking cipher skip",
        suggested_reply="Ready to reply",
        status="needs_review",
    )
    db_session.add(msg)
    db_session.commit()

    # Sending in mock mode must succeed without attempting token decryption
    send_resp = client.post(
        f"/v1/whatsapp/messages/{msg.id}/send",
        headers={"X-CSRF-Token": csrf},
        json={"reply_text": "Decryption was safely bypassed in mock mode"},
    )
    assert send_resp.status_code == 200
    assert send_resp.json()["status"] == "sent"


def test_whatsapp_simulate_inbound_creates_message_and_grounded_ai_draft(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "mock")
    monkeypatch.setattr(settings, "WHATSAPP_ENCRYPTION_KEY", "u6N77xV0B1B6bKkCkJy3qQ8eM2fD4aX9tG7hP5rS1v8=")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_sim_inbound_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Sim Inbound Merchant",
            "business_name": "Sim Inbound Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201
    csrf = reg.json()["csrf_token"]
    merchant_id = uuid.UUID(reg.json()["merchant"]["id"])

    # Connect WhatsApp account for merchant
    acc_resp = client.put(
        "/v1/whatsapp/account",
        headers={"X-CSRF-Token": csrf},
        json={
            "phone_number_id": "phone-sim-1",
            "access_token": "EAAX_valid_mock_token_at_least_20_chars",
        },
    )
    assert acc_resp.status_code == 200

    # Simulate inbound customer message
    sim_resp = client.post(
        "/v1/whatsapp/mock/simulate-inbound",
        headers={"X-CSRF-Token": csrf},
        json={
            "customer_wa_id": "919876543210",
            "customer_name": "Ravi Kumar",
            "message_text": "Do you offer home delivery in Indiranagar?",
        },
    )
    assert sim_resp.status_code == 201
    sim_data = sim_resp.json()

    assert sim_data["customer_wa_id"] == "919876543210"
    assert sim_data["customer_name"] == "Ravi Kumar"
    assert sim_data["inbound_text"] == "Do you offer home delivery in Indiranagar?"
    assert sim_data["status"] == "needs_review"
    assert sim_data["provider_message_id"].startswith("wamid.sim_")
    # Grounded AI draft suggestion must be present and not auto-sent
    assert sim_data["suggested_reply"] is not None
    assert len(sim_data["suggested_reply"]) > 0

    # Verify message in inbox listing
    inbox_resp = client.get("/v1/whatsapp/messages")
    assert inbox_resp.status_code == 200
    items = inbox_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == sim_data["id"]
    assert items[0]["status"] == "needs_review"

    # Verify directly in DB
    created_id = uuid.UUID(sim_data["id"])
    db_msg = db_session.get(WhatsAppMessage, created_id)
    assert db_msg is not None
    assert db_msg.merchant_id == merchant_id
    assert db_msg.status == "needs_review"


def test_whatsapp_mock_endpoints_return_404_in_live_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "live")

    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_live_404_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Live Mode Merchant",
            "business_name": "Live Mode Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201
    csrf = reg.json()["csrf_token"]

    dummy_id = str(uuid.uuid4())

    sim_resp = client.post(
        "/v1/whatsapp/mock/simulate-inbound",
        headers={"X-CSRF-Token": csrf},
        json={
            "customer_wa_id": "919876543210",
            "customer_name": "Live Mode User",
            "message_text": "Testing 404 in live mode",
        },
    )
    assert sim_resp.status_code == 404

    status_resp = client.post(
        f"/v1/whatsapp/mock/messages/{dummy_id}/status",
        headers={"X-CSRF-Token": csrf},
        json={"status": "send_failed"},
    )
    assert status_resp.status_code == 404


def test_whatsapp_mock_endpoints_require_auth_and_csrf(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "mock")

    dummy_id = str(uuid.uuid4())

    # Unauthenticated requests return 401
    unauth_sim = client.post(
        "/v1/whatsapp/mock/simulate-inbound",
        json={
            "customer_wa_id": "919876543210",
            "customer_name": "Unauth User",
            "message_text": "No cookie",
        },
    )
    assert unauth_sim.status_code == 401

    unauth_status = client.post(
        f"/v1/whatsapp/mock/messages/{dummy_id}/status",
        json={"status": "send_failed"},
    )
    assert unauth_status.status_code == 401

    # Authenticate merchant
    reg = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_csrf_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "CSRF Merchant",
            "business_name": "CSRF Store",
            "category": "Retail",
        },
    )
    assert reg.status_code == 201

    # Missing CSRF returns 403
    no_csrf_sim = client.post(
        "/v1/whatsapp/mock/simulate-inbound",
        json={
            "customer_wa_id": "919876543210",
            "customer_name": "No CSRF User",
            "message_text": "Missing header",
        },
    )
    assert no_csrf_sim.status_code == 403

    no_csrf_status = client.post(
        f"/v1/whatsapp/mock/messages/{dummy_id}/status",
        json={"status": "send_failed"},
    )
    assert no_csrf_status.status_code == 403


def test_whatsapp_mock_status_update_and_tenant_isolation(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "mock")

    # Register Merchant A
    email_a = f"wa_merchant_a_{uuid.uuid4().hex[:8]}@example.com"
    reg_a = client.post(
        "/v1/auth/register",
        json={
            "email": email_a,
            "password": "Password123!",
            "full_name": "Merchant A",
            "business_name": "Store A",
            "category": "Retail",
        },
    )
    assert reg_a.status_code == 201
    csrf_a = reg_a.json()["csrf_token"]
    merchant_a_id = uuid.UUID(reg_a.json()["merchant"]["id"])

    # Register Merchant B
    reg_b = client.post(
        "/v1/auth/register",
        json={
            "email": f"wa_merchant_b_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
            "full_name": "Merchant B",
            "business_name": "Store B",
            "category": "Retail",
        },
    )
    assert reg_b.status_code == 201
    csrf_b = reg_b.json()["csrf_token"]

    # Insert message for Merchant A
    msg_a = WhatsAppMessage(
        merchant_id=merchant_a_id,
        phone_number_id="phone-a-1",
        provider_message_id=f"wamid.sim_{uuid.uuid4().hex[:12]}",
        customer_wa_id="919876543210",
        customer_name="Customer A",
        inbound_text="Hello from Store A",
        suggested_reply="Reply for Store A",
        status="sent",
    )
    db_session.add(msg_a)
    db_session.commit()

    # Merchant B (currently logged in) attempts to modify Merchant A's message status
    unauthorized_status = client.post(
        f"/v1/whatsapp/mock/messages/{msg_a.id}/status",
        headers={"X-CSRF-Token": csrf_b},
        json={"status": "send_failed", "last_error": "Tampering attempt"},
    )
    assert unauthorized_status.status_code == 404
    assert unauthorized_status.json()["error"]["code"] == "WHATSAPP_MESSAGE_NOT_FOUND"

    # Re-login as Merchant A
    login_a = client.post(
        "/v1/auth/login",
        json={
            "email": email_a,
            "password": "Password123!",
        },
    )
    assert login_a.status_code == 200
    csrf_a_fresh = login_a.json()["csrf_token"]

    # Merchant A transitions message to send_failed with last_error
    status_failed = client.post(
        f"/v1/whatsapp/mock/messages/{msg_a.id}/status",
        headers={"X-CSRF-Token": csrf_a_fresh},
        json={"status": "send_failed", "last_error": "Simulated timeout error"},
    )
    assert status_failed.status_code == 200
    assert status_failed.json()["status"] == "send_failed"
    assert status_failed.json()["last_error"] == "Simulated timeout error"

    db_session.expire_all()
    updated_msg = db_session.get(WhatsAppMessage, msg_a.id)
    assert updated_msg.status == "send_failed"
    assert updated_msg.last_error == "Simulated timeout error"

    # Merchant A transitions message to send_ambiguous
    status_ambiguous = client.post(
        f"/v1/whatsapp/mock/messages/{msg_a.id}/status",
        headers={"X-CSRF-Token": csrf_a_fresh},
        json={"status": "send_ambiguous"},
    )
    assert status_ambiguous.status_code == 200
    assert status_ambiguous.json()["status"] == "send_ambiguous"

    # Reject invalid status transition
    status_invalid = client.post(
        f"/v1/whatsapp/mock/messages/{msg_a.id}/status",
        headers={"X-CSRF-Token": csrf_a_fresh},
        json={"status": "invalid_status_value"},
    )
    assert status_invalid.status_code == 422

    # Reject attempt to fabricate 'sent' status directly via mock status endpoint
    status_reject_sent = client.post(
        f"/v1/whatsapp/mock/messages/{msg_a.id}/status",
        headers={"X-CSRF-Token": csrf_a_fresh},
        json={"status": "sent"},
    )
    assert status_reject_sent.status_code == 422

    # Reject attempt to transition to 'needs_review' via mock status endpoint
    status_reject_needs_review = client.post(
        f"/v1/whatsapp/mock/messages/{msg_a.id}/status",
        headers={"X-CSRF-Token": csrf_a_fresh},
        json={"status": "needs_review"},
    )
    assert status_reject_needs_review.status_code == 422

    # Insert an unapproved needs_review message for Merchant A
    msg_unapproved = WhatsAppMessage(
        merchant_id=merchant_a_id,
        phone_number_id="phone-a-1",
        provider_message_id=f"wamid.sim_{uuid.uuid4().hex[:12]}",
        customer_wa_id="919876543210",
        customer_name="Customer A",
        inbound_text="Unapproved inquiry",
        suggested_reply="Proposed draft",
        status="needs_review",
    )
    db_session.add(msg_unapproved)
    db_session.commit()

    # Reject attempt to mutate delivery status on an unapproved needs_review message
    status_reject_unapproved = client.post(
        f"/v1/whatsapp/mock/messages/{msg_unapproved.id}/status",
        headers={"X-CSRF-Token": csrf_a_fresh},
        json={"status": "send_failed"},
    )
    assert status_reject_unapproved.status_code == 409
    assert status_reject_unapproved.json()["error"]["code"] == "INVALID_MESSAGE_STATE"



def test_whatsapp_webhook_still_requires_signature_in_mock_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_MODE", "mock")
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-app-secret")

    # Missing signature returns 401
    missing_sig = client.post(
        "/v1/whatsapp/webhook",
        json={"object": "whatsapp_business_account"},
    )
    assert missing_sig.status_code == 401

    # Invalid signature returns 401
    invalid_sig = client.post(
        "/v1/whatsapp/webhook",
        content=json.dumps({"object": "whatsapp_business_account"}),
        headers={"X-Hub-Signature-256": "sha256=bad_signature"},
    )
    assert invalid_sig.status_code == 401
