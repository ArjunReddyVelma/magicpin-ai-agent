import hashlib
import hmac
import json

from backend.app.core.config import settings


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
