import hashlib
import hmac
import json
import uuid
import httpx
import pytest
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
