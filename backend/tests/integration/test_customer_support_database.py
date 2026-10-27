import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.user import User
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.customer_support import (
    CustomerSupportSession,
    CustomerSupportMessage,
)


def _create_merchant(db: Session, business_name: str = "Test Store") -> MerchantProfile:
    user = User(
        full_name="Merchant Owner",
        email=f"owner_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="argon2id_dummy_hash",
        is_active=True,
    )
    db.add(user)
    db.flush()

    merchant = MerchantProfile(
        user_id=user.id,
        business_name=business_name,
        category="Retail",
        location="Bangalore",
        timezone="Asia/Kolkata",
    )
    db.add(merchant)
    db.flush()
    return merchant


def test_customer_support_schema_indexes_and_constraints(db_session: Session):
    """
    Verifies that all expected indexes and foreign key constraints exist
    on customer_support_sessions and customer_support_messages tables.
    """
    bind = db_session.get_bind()
    inspector = inspect(bind)

    # 1. Verify tables exist
    table_names = set(inspector.get_table_names())
    assert "customer_support_sessions" in table_names
    assert "customer_support_messages" in table_names

    # 2. Verify sessions indexes
    session_indexes = {ix["name"]: ix for ix in inspector.get_indexes("customer_support_sessions")}
    assert "ix_customer_support_sessions_merchant_id" in session_indexes
    assert "ix_customer_support_sessions_customer_token_hash" in session_indexes
    assert session_indexes["ix_customer_support_sessions_customer_token_hash"]["unique"] is True
    assert "ix_customer_support_sessions_merchant_updated" in session_indexes

    # 3. Verify messages indexes
    message_indexes = {ix["name"]: ix for ix in inspector.get_indexes("customer_support_messages")}
    assert "ix_customer_support_messages_session_id" in message_indexes
    assert "ix_customer_support_messages_merchant_id" in message_indexes
    assert "ix_csm_session_created" in message_indexes
    assert "ix_csm_merchant_status_created" in message_indexes

    # 4. Verify composite foreign key on customer_support_messages
    fks = inspector.get_foreign_keys("customer_support_messages")
    composite_fk = next(
        (
            fk for fk in fks
            if set(fk["constrained_columns"]) == {"session_id", "merchant_id"}
            and set(fk["referred_columns"]) == {"id", "merchant_id"}
            and fk["referred_table"] == "customer_support_sessions"
        ),
        None,
    )
    assert composite_fk is not None, f"Composite FK (session_id, merchant_id) missing in {fks}"
    assert composite_fk.get("options", {}).get("ondelete") == "CASCADE"


def test_create_session_and_messages_with_valid_foreign_keys(db_session: Session):
    """
    Verifies creating a customer session and child message with valid foreign keys,
    verifying relationships and default values.
    """
    merchant = _create_merchant(db_session, "Artisan Roasters")
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hash

    session = CustomerSupportSession(
        merchant_id=merchant.id,
        customer_token_hash=token_hash,
        customer_name="Aarav Sharma",
        status="active",
    )
    db_session.add(session)
    db_session.flush()

    assert session.id is not None
    assert session.status == "active"
    assert session.created_at is not None
    assert session.updated_at is not None

    message = CustomerSupportMessage(
        session_id=session.id,
        merchant_id=merchant.id,
        customer_text="Do you have cold brew in stock today?",
        suggested_reply="Yes, our Colombian cold brew is freshly prepared.",
        status="needs_review",
        ai_status="completed",
    )
    db_session.add(message)
    db_session.flush()

    assert message.id is not None
    assert message.status == "needs_review"
    assert message.ai_status == "completed"
    assert message.approved_reply is None
    assert message.reviewed_at is None
    assert message.delivered_at is None

    # Verify bidirectional ORM relationship navigation
    db_session.refresh(session)
    assert len(session.messages) == 1
    assert session.messages[0].id == message.id
    assert message.session.id == session.id
    assert message.merchant.id == merchant.id


def test_session_invalid_status_rejected_by_check_constraint(db_session: Session):
    """
    Verifies that invalid session status values are rejected by ck_customer_support_sessions_status.
    """
    merchant = _create_merchant(db_session, "Status Test Cafe")
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex

    bad_session = CustomerSupportSession(
        merchant_id=merchant.id,
        customer_token_hash=token_hash,
        customer_name="Test User",
        status="invalid_status",
    )
    db_session.add(bad_session)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_message_invalid_status_rejected_by_check_constraint(db_session: Session):
    """
    Verifies that invalid message status values are rejected by ck_customer_support_messages_status.
    """
    merchant = _create_merchant(db_session, "Message Status Store")
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex

    session = CustomerSupportSession(
        merchant_id=merchant.id,
        customer_token_hash=token_hash,
        status="active",
    )
    db_session.add(session)
    db_session.flush()

    bad_message = CustomerSupportMessage(
        session_id=session.id,
        merchant_id=merchant.id,
        customer_text="What are your hours?",
        status="archived",  # Invalid for support messages
        ai_status="pending",
    )
    db_session.add(bad_message)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_message_invalid_ai_status_rejected_by_check_constraint(db_session: Session):
    """
    Verifies that invalid ai_status values are rejected by ck_customer_support_messages_ai_status.
    """
    merchant = _create_merchant(db_session, "AI Status Store")
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex

    session = CustomerSupportSession(
        merchant_id=merchant.id,
        customer_token_hash=token_hash,
        status="active",
    )
    db_session.add(session)
    db_session.flush()

    bad_ai_message = CustomerSupportMessage(
        session_id=session.id,
        merchant_id=merchant.id,
        customer_text="Can I get a discount?",
        status="needs_review",
        ai_status="hallucinating",  # Invalid
    )
    db_session.add(bad_ai_message)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_message_empty_text_rejected_by_check_constraint(db_session: Session):
    """
    Verifies that empty or whitespace-only customer inquiry text is rejected by
    ck_customer_support_messages_customer_text_not_empty constraint.
    """
    merchant = _create_merchant(db_session, "Empty Content Store")
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex

    session = CustomerSupportSession(
        merchant_id=merchant.id,
        customer_token_hash=token_hash,
        status="active",
    )
    db_session.add(session)
    db_session.flush()

    empty_message = CustomerSupportMessage(
        session_id=session.id,
        merchant_id=merchant.id,
        customer_text="    ",  # Only spaces
        status="needs_review",
        ai_status="pending",
    )
    db_session.add(empty_message)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_merchant_session_mismatch_rejected_by_composite_foreign_key(db_session: Session):
    """
    CRITICAL TENANT INTEGRITY TEST:
    Verifies that assigning a message to Session 1 (owned by Merchant 1) but specifying
    Merchant 2 is rejected at the database level by the composite foreign key
    fk_customer_support_messages_session_merchant.
    """
    merchant_1 = _create_merchant(db_session, "Merchant One")
    merchant_2 = _create_merchant(db_session, "Merchant Two")

    session_1 = CustomerSupportSession(
        merchant_id=merchant_1.id,
        customer_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        status="active",
    )
    db_session.add(session_1)
    db_session.flush()

    # Attempt to insert message referencing session_1.id, but claiming merchant_2.id
    mismatched_message = CustomerSupportMessage(
        session_id=session_1.id,
        merchant_id=merchant_2.id,  # MISMATCH: session_1 belongs to merchant_1!
        customer_text="Cross-merchant attack probe",
        status="needs_review",
        ai_status="pending",
    )
    db_session.add(mismatched_message)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    db_session.rollback()

    err_str = str(exc_info.value).lower()
    assert (
        "fk_customer_support_messages_session_merchant" in err_str
        or "foreign key" in err_str
    ), f"Expected composite foreign key violation, got: {exc_info.value}"


def test_ai_failure_representation_while_inquiry_remains_needs_review(db_session: Session):
    """
    Verifies that AI provider failure is represented independently via ai_status='failed'
    and ai_error without causing the inquiry to disappear, become delivered, or become dismissed.
    """
    merchant = _create_merchant(db_session, "Resilience Store")
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex

    session = CustomerSupportSession(
        merchant_id=merchant.id,
        customer_token_hash=token_hash,
        customer_name="Priya Patel",
        status="active",
    )
    db_session.add(session)
    db_session.flush()

    # Simulate AI provider timeout / failure
    failed_ai_message = CustomerSupportMessage(
        session_id=session.id,
        merchant_id=merchant.id,
        customer_text="Is table reservation required on Friday evening?",
        suggested_reply=None,
        status="needs_review",  # Retained in review queue for merchant manual reply
        ai_status="failed",     # Provider failure recorded
        ai_error="Provider timeout after 30 seconds; upstream service unavailable",
    )
    db_session.add(failed_ai_message)
    db_session.flush()

    # Query from database to verify persistence
    queried = db_session.scalar(
        select(CustomerSupportMessage).where(CustomerSupportMessage.id == failed_ai_message.id)
    )
    assert queried is not None
    assert queried.status == "needs_review"
    assert queried.ai_status == "failed"
    assert "upstream service unavailable" in queried.ai_error
    assert queried.customer_text == "Is table reservation required on Friday evening?"
    assert queried.approved_reply is None

    # Simulate merchant subsequently reviewing and manually answering the customer inquiry
    now = datetime.now(timezone.utc)
    queried.approved_reply = "Reservations are recommended for parties of 4 or more on Friday evenings."
    queried.status = "delivered"
    queried.reviewed_at = now
    queried.delivered_at = now
    db_session.flush()

    db_session.refresh(queried)
    assert queried.status == "delivered"
    assert queried.approved_reply is not None
    assert queried.delivered_at is not None
    # Historical failure record is preserved for auditing
    assert queried.ai_status == "failed"


def test_cascade_delete_on_merchant_profile_removal(db_session: Session):
    """
    Verifies that deleting a merchant profile cascades and removes all associated
    customer support sessions and messages automatically.
    """
    merchant = _create_merchant(db_session, "Ephemeral Merchant")
    token_hash = uuid.uuid4().hex + uuid.uuid4().hex

    session = CustomerSupportSession(
        merchant_id=merchant.id,
        customer_token_hash=token_hash,
        status="active",
    )
    db_session.add(session)
    db_session.flush()

    msg = CustomerSupportMessage(
        session_id=session.id,
        merchant_id=merchant.id,
        customer_text="Inquiry before merchant removal",
        status="needs_review",
        ai_status="completed",
        suggested_reply="Auto reply",
    )
    db_session.add(msg)
    db_session.flush()

    session_id = session.id
    msg_id = msg.id

    # Delete merchant profile and verify DB cascade
    db_session.delete(merchant)
    db_session.flush()
    db_session.expire_all()

    # Verify session and message are cascaded and deleted in PostgreSQL
    remaining_session = db_session.get(CustomerSupportSession, session_id)
    remaining_msg = db_session.get(CustomerSupportMessage, msg_id)
    assert remaining_session is None
    assert remaining_msg is None
