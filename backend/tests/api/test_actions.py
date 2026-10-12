import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.app.repositories.action_repository import ActionRepository
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.user import User


def _register_merchant(client: TestClient, name: str = "Action Owner"):
    email = f"act_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "business_name": f"{name} Store",
        },
    )
    assert r.status_code == 201
    return r.json()


def test_actions_unauthenticated(client: TestClient):
    r = client.get("/v1/actions")
    assert r.status_code == 401


def test_actions_list_and_filter(client: TestClient, db_session: Session):
    auth_data = _register_merchant(client, "List Owner")
    merchant_id = uuid.UUID(auth_data["merchant"]["id"])

    # Seed 3 actions directly using repository
    repo = ActionRepository(db_session)
    a1 = repo.create(merchant_id, "reply_draft", "Order Delay Reply", "Draft apologizing for delay.")
    a2 = repo.create(merchant_id, "recommendation", "Combo Offer", "Suggest running a festival combo.")
    a3 = repo.create(merchant_id, "summary", "Weekly Summary", "Summary of customer questions.")

    # Mark a2 as approved
    repo.transition_status(merchant_id, a2.id, "approved")

    # 1. List all actions
    r_all = client.get("/v1/actions")
    assert r_all.status_code == 200
    data_all = r_all.json()
    assert data_all["total"] == 3
    assert len(data_all["items"]) == 3

    # 2. Filter by status: pending
    r_pending = client.get("/v1/actions?status=pending")
    assert r_pending.status_code == 200
    data_pending = r_pending.json()
    assert data_pending["total"] == 2
    for item in data_pending["items"]:
        assert item["status"] == "pending"

    # 3. Filter by status: approved
    r_approved = client.get("/v1/actions?status=approved")
    assert r_approved.status_code == 200
    data_approved = r_approved.json()
    assert data_approved["total"] == 1
    assert data_approved["items"][0]["id"] == str(a2.id)

    # 4. Invalid status filter returns 400
    r_invalid = client.get("/v1/actions?status=unknown_status")
    assert r_invalid.status_code == 400
    assert r_invalid.json()["error"]["code"] == "INVALID_STATUS"

    # 5. Pagination test
    r_page = client.get("/v1/actions?page=1&page_size=2")
    assert r_page.status_code == 200
    data_page = r_page.json()
    assert len(data_page["items"]) == 2
    assert data_page["total"] == 3


def test_actions_get_by_id(client: TestClient, db_session: Session):
    auth_data = _register_merchant(client, "Get Owner")
    merchant_id = uuid.UUID(auth_data["merchant"]["id"])

    repo = ActionRepository(db_session)
    action = repo.create(merchant_id, "follow_up", "Payment Check", "Check if UPI payment cleared.")

    # Valid get
    r = client.get(f"/v1/actions/{action.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == str(action.id)
    assert data["title"] == "Payment Check"
    assert data["action_type"] == "follow_up"

    # Non-existent ID returns 404
    r_404 = client.get(f"/v1/actions/{uuid.uuid4()}")
    assert r_404.status_code == 404
    assert r_404.json()["error"]["code"] == "ACTION_NOT_FOUND"


def test_actions_approve_and_state_machine(client: TestClient, db_session: Session):
    auth_data = _register_merchant(client, "Approve Owner")
    merchant_id = uuid.UUID(auth_data["merchant"]["id"])
    csrf = auth_data["csrf_token"]

    repo = ActionRepository(db_session)
    action = repo.create(merchant_id, "reply_draft", "Review Draft", "Customer requested vegan option.")

    # 1. State-changing POST requires CSRF
    r_no_csrf = client.post(f"/v1/actions/{action.id}/approve")
    assert r_no_csrf.status_code == 403

    # 2. Valid approval transition
    r_approve = client.post(
        f"/v1/actions/{action.id}/approve",
        headers={"X-CSRF-Token": csrf},
    )
    assert r_approve.status_code == 200
    approved_data = r_approve.json()
    assert approved_data["status"] == "approved"
    assert approved_data["reviewed_at"] is not None

    # 3. Repeated approval returns 409
    r_repeat = client.post(
        f"/v1/actions/{action.id}/approve",
        headers={"X-CSRF-Token": csrf},
    )
    assert r_repeat.status_code == 409
    assert r_repeat.json()["error"]["code"] == "INVALID_ACTION_STATE"

    # 4. Attempting to dismiss an approved action returns 409
    r_dismiss_after_approve = client.post(
        f"/v1/actions/{action.id}/dismiss",
        headers={"X-CSRF-Token": csrf},
    )
    assert r_dismiss_after_approve.status_code == 409
    assert r_dismiss_after_approve.json()["error"]["code"] == "INVALID_ACTION_STATE"


def test_actions_dismiss_lifecycle(client: TestClient, db_session: Session):
    auth_data = _register_merchant(client, "Dismiss Owner")
    merchant_id = uuid.UUID(auth_data["merchant"]["id"])
    csrf = auth_data["csrf_token"]

    repo = ActionRepository(db_session)
    action = repo.create(merchant_id, "recommendation", "Dismiss Target", "Discount recommendation.")

    # 1. Dismiss action
    r_dismiss = client.post(
        f"/v1/actions/{action.id}/dismiss",
        headers={"X-CSRF-Token": csrf},
    )
    assert r_dismiss.status_code == 200
    dismissed_data = r_dismiss.json()
    assert dismissed_data["status"] == "dismissed"
    assert dismissed_data["reviewed_at"] is not None

    # 2. Attempting to approve a dismissed action returns 409
    r_approve_after_dismiss = client.post(
        f"/v1/actions/{action.id}/approve",
        headers={"X-CSRF-Token": csrf},
    )
    assert r_approve_after_dismiss.status_code == 409
    assert r_approve_after_dismiss.json()["error"]["code"] == "INVALID_ACTION_STATE"


def test_actions_tenant_isolation(client: TestClient, db_session: Session):
    # Register Merchant A
    auth_a = _register_merchant(client, "Merchant A")
    merchant_a_id = uuid.UUID(auth_a["merchant"]["id"])

    # Create action for Merchant A
    repo = ActionRepository(db_session)
    action_a = repo.create(merchant_a_id, "reply_draft", "Secret Action A", "Private response A.")

    # Register and authenticate as Merchant B
    auth_b = _register_merchant(client, "Merchant B")
    csrf_b = auth_b["csrf_token"]

    # Merchant B tries to GET Merchant A's action -> 404
    r_get = client.get(f"/v1/actions/{action_a.id}")
    assert r_get.status_code == 404
    assert r_get.json()["error"]["code"] == "ACTION_NOT_FOUND"

    # Merchant B tries to approve Merchant A's action -> 404
    r_approve = client.post(
        f"/v1/actions/{action_a.id}/approve",
        headers={"X-CSRF-Token": csrf_b},
    )
    assert r_approve.status_code == 404
    assert r_approve.json()["error"]["code"] == "ACTION_NOT_FOUND"

    # Merchant B tries to dismiss Merchant A's action -> 404
    r_dismiss = client.post(
        f"/v1/actions/{action_a.id}/dismiss",
        headers={"X-CSRF-Token": csrf_b},
    )
    assert r_dismiss.status_code == 404
    assert r_dismiss.json()["error"]["code"] == "ACTION_NOT_FOUND"
