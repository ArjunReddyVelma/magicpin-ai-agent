import time
import uuid
from typing import Optional
from datetime import datetime, timezone
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import MerchantProfile
from backend.app.repositories import (
    UserRepository,
    MerchantRepository,
    ContextRepository,
    ConversationRepository,
    MessageRepository,
    ActionRepository,
)


def test_user_repository_crud_and_normalization(db_session: Session):
    repo = UserRepository(db_session)
    email = "Merchant.Test@Domain.COM"
    user = repo.create(full_name="Alice Owner", email=email, password_hash="hash123")

    assert user.id is not None
    assert user.email == "merchant.test@domain.com"

    # Lookup normalized
    found = repo.get_by_email("   MERCHANT.TEST@domain.com  ")
    assert found is not None
    assert found.id == user.id

    # Duplicate rejection
    with pytest.raises(IntegrityError):
        repo.create(full_name="Duplicate", email="merchant.test@domain.com", password_hash="hash456")
    db_session.rollback()


def test_merchant_repository_crud(db_session: Session, test_user):
    repo = MerchantRepository(db_session)
    profile = repo.create(
        user_id=test_user.id,
        business_name="Green Spices",
        category="Grocery",
        location="MG Road",
    )
    assert profile.id is not None
    assert profile.business_name == "Green Spices"
    assert profile.timezone == "Asia/Kolkata"

    # Lookup by user
    by_user = repo.get_by_user_id(test_user.id)
    assert by_user is not None
    assert by_user.id == profile.id

    # Update
    updated = repo.update(profile.id, business_name="Green Spices Supermarket")
    assert updated.business_name == "Green Spices Supermarket"


def test_context_repository_crud_and_optimistic_concurrency(
    db_session: Session, test_merchant: MerchantProfile
):
    repo = ContextRepository(db_session)

    # 1. Create context items
    item1 = repo.create(
        merchant_id=test_merchant.id,
        item_type="policy",
        title="Refund Policy",
        content="Refunds within 7 days with original receipt.",
    )
    assert item1.version == 1

    item2 = repo.create(
        merchant_id=test_merchant.id,
        item_type="faq",
        title="Store Hours",
        content="Open 9 AM to 10 PM daily.",
    )

    # 2. List with filtering and pagination
    items, total = repo.list_items(merchant_id=test_merchant.id, item_type="policy")
    assert total == 1
    assert items[0].id == item1.id

    all_items, all_total = repo.list_items(merchant_id=test_merchant.id)
    assert all_total == 2

    # 3. Optimistic Concurrency Update - Success on matching version
    updated, is_conflict = repo.update_with_version(
        merchant_id=test_merchant.id,
        context_id=item1.id,
        expected_version=1,
        content="Updated refund policy text.",
    )
    assert not is_conflict
    assert updated is not None
    assert updated.version == 2
    assert updated.content == "Updated refund policy text."

    # 4. Optimistic Concurrency Update - Conflict on stale version
    stale_item, is_conflict = repo.update_with_version(
        merchant_id=test_merchant.id,
        context_id=item1.id,
        expected_version=1,  # Stale! Current version is 2
        content="Concurrent update attempt.",
    )
    assert is_conflict is True
    assert stale_item.version == 2
    assert stale_item.content == "Updated refund policy text."  # unchanged

    # 5. Delete
    deleted = repo.delete(merchant_id=test_merchant.id, context_id=item2.id)
    assert deleted is True
    assert repo.get_by_id(test_merchant.id, item2.id) is None


def test_conversation_repository_and_deterministic_order(
    db_session: Session, test_merchant: MerchantProfile
):
    repo = ConversationRepository(db_session)

    c1 = repo.create(merchant_id=test_merchant.id, title="Support Chat A")
    c2 = repo.create(merchant_id=test_merchant.id, title="Support Chat B")

    items, total = repo.list_conversations(merchant_id=test_merchant.id)
    assert total == 2
    assert len(items) == 2

    # Search filter
    filtered, f_total = repo.list_conversations(merchant_id=test_merchant.id, query="Chat A")
    assert f_total == 1
    assert filtered[0].id == c1.id

    # Update status to archived
    archived = repo.update(test_merchant.id, c1.id, status="archived")
    assert archived.status == "archived"

    # Filter by status
    active_items, a_total = repo.list_conversations(merchant_id=test_merchant.id, status="active")
    assert a_total == 1
    assert active_items[0].id == c2.id


def test_message_repository_and_history_window(
    db_session: Session, test_merchant: MerchantProfile
):
    conv_repo = ConversationRepository(db_session)
    msg_repo = MessageRepository(db_session)

    conv = conv_repo.create(merchant_id=test_merchant.id, title="Test Conversation")

    # Add sequence of messages
    m1 = msg_repo.create(conv.id, role="user", content="Hello, what are your hours?")
    time.sleep(0.01)
    m2 = msg_repo.create(conv.id, role="assistant", content="We are open 9 AM to 10 PM.")
    time.sleep(0.01)
    m3 = msg_repo.create(conv.id, role="user", content="Do you offer discounts?")

    # List messages
    msgs, total = msg_repo.list_messages(conv.id)
    assert total == 3
    # Deterministic chronological order
    assert [m.id for m in msgs] == [m1.id, m2.id, m3.id]

    # Bounded history window (last 2)
    recent = msg_repo.get_recent_history(conv.id, limit=2)
    assert len(recent) == 2
    assert [m.id for m in recent] == [m2.id, m3.id]

    # Failed message marking
    failed = msg_repo.mark_failed(conv.id, m3.id)
    assert failed.status == "failed"


def test_action_repository_state_transitions(
    db_session: Session, test_merchant: MerchantProfile
):
    repo = ActionRepository(db_session)

    action = repo.create(
        merchant_id=test_merchant.id,
        action_type="reply_draft",
        title="Customer Delay Response",
        description="Draft reply apologizing for 10-minute order delay.",
    )
    assert action.status == "pending"
    assert repo.count_pending(test_merchant.id) == 1

    # Valid transition to approved
    approved, ok = repo.transition_status(test_merchant.id, action.id, "approved")
    assert ok is True
    assert approved.status == "approved"
    assert approved.reviewed_at is not None
    assert repo.count_pending(test_merchant.id) == 0

    # Invalid transition (cannot transition already approved action)
    _, invalid_ok = repo.transition_status(test_merchant.id, action.id, "dismissed")
    assert invalid_ok is False


def test_merchant_isolation(
    db_session: Session, test_merchant: MerchantProfile, second_merchant: MerchantProfile
):
    """
    SECURITY TEST: Proves that Merchant B cannot access or modify Merchant A's
    context items, conversations, or actions by ID substitution.
    """
    ctx_repo = ContextRepository(db_session)
    conv_repo = ConversationRepository(db_session)
    action_repo = ActionRepository(db_session)

    # Merchant A creates resources
    item_a = ctx_repo.create(test_merchant.id, "policy", "Secret Policy A", "Confidential text A")
    conv_a = conv_repo.create(test_merchant.id, "Private Conversation A")
    action_a = action_repo.create(test_merchant.id, "recommendation", "Action A", "Private rec A")

    # Merchant B attempts to read Merchant A's resources
    assert ctx_repo.get_by_id(second_merchant.id, item_a.id) is None
    assert conv_repo.get_by_id(second_merchant.id, conv_a.id) is None
    assert action_repo.get_by_id(second_merchant.id, action_a.id) is None

    # Merchant B attempts to update Merchant A's context item
    updated, conflict = ctx_repo.update_with_version(
        merchant_id=second_merchant.id,
        context_id=item_a.id,
        expected_version=1,
        content="Malicious edit by B",
    )
    assert updated is None

    # Merchant B attempts to approve Merchant A's action
    _, approved = action_repo.transition_status(second_merchant.id, action_a.id, "approved")
    assert approved is False

    # Ensure Merchant A's data was not modified
    intact_item = ctx_repo.get_by_id(test_merchant.id, item_a.id)
    assert intact_item.content == "Confidential text A"
    intact_action = action_repo.get_by_id(test_merchant.id, action_a.id)
    assert intact_action.status == "pending"
