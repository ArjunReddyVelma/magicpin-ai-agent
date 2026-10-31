import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.tests.conftest import TestingSessionLocal
from backend.app.core.config import settings
from backend.app.core.db_safety import validate_test_database_isolation
from backend.app.db.session import check_database_connection
from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.models.merchant_profile import MerchantProfile
from backend.app.models.conversation import Conversation
from backend.app.models.message import Message
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.repositories.message_repository import MessageRepository
from backend.app.services.chat_service import ChatService
from backend.app.ai.provider import LLMProvider, LLMResponse, LLMTimeoutError


class DelayedMockLLMProvider(LLMProvider):
    """
    Thread-safe mock LLM provider with configurable delay to test real database concurrency.
    """

    def __init__(self, delay_seconds: float = 0.2, should_fail: bool = False):
        self.delay_seconds = delay_seconds
        self.should_fail = should_fail
        self.call_count = 0
        self.lock = threading.Lock()

    def generate_response(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        with self.lock:
            self.call_count += 1

        time.sleep(self.delay_seconds)

        if self.should_fail:
            raise LLMTimeoutError("Simulated LLM timeout under concurrency")

        return LLMResponse(
            content="Concurrent test response from grounded LLM.",
            provider="mock-delayed",
            model="mock-delay-model",
            input_tokens=15,
            output_tokens=25,
        )


@pytest.fixture(autouse=True)
def require_test_database():
    test_db_url = settings.DATABASE_URL_TEST
    validate_test_database_isolation(test_db_url)
    test_engine = create_engine(test_db_url)
    if not check_database_connection(test_engine):
        test_engine.dispose()
        pytest.skip("Test database (DATABASE_URL_TEST) is unavailable; skipping chat concurrency tests.")
    test_engine.dispose()


@pytest.fixture
def test_merchant_and_conversation():
    """
    Sets up a test merchant and active conversation directly in PostgreSQL,
    committing so independent worker sessions can see them.
    Cleans up after the test.
    """
    db = TestingSessionLocal()
    try:
        user = User(
            full_name="Concurrency Merchant",
            email=f"concurrency_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("ValidPassword123!"),
            is_active=True,
        )
        db.add(user)
        db.flush()

        merchant = MerchantProfile(
            user_id=user.id,
            business_name="Concurrent Cafe",
            category="Restaurant",
        )
        db.add(merchant)
        db.flush()

        conv = Conversation(
            merchant_id=merchant.id,
            title="Concurrency Test Conversation",
            status="active",
        )
        db.add(conv)
        db.commit()

        merchant_id = merchant.id
        conversation_id = conv.id
        user_id = user.id
    finally:
        db.close()

    yield merchant_id, conversation_id

    # Cleanup
    cleanup_db = TestingSessionLocal()
    try:
        db_user = cleanup_db.get(User, user_id)
        if db_user:
            cleanup_db.delete(db_user)
            cleanup_db.commit()
    finally:
        cleanup_db.close()


def test_concurrent_duplicate_submissions_with_idempotency_key(test_merchant_and_conversation):
    """
    Proves that concurrent duplicate requests with the same idempotency key across separate
    database sessions are serialized by Conversation row locking:
    - Provider is invoked exactly once.
    - Exactly one user message and one assistant message are created.
    - Both callers receive the exact same successful ChatResponse.
    """
    merchant_id, conv_id = test_merchant_and_conversation
    provider = DelayedMockLLMProvider(delay_seconds=0.25)
    chat_service = ChatService()
    shared_idempotency_key = f"concurrent_key_{uuid.uuid4().hex}"

    def run_worker():
        db: Session = TestingSessionLocal()
        try:
            merchant = db.get(MerchantProfile, merchant_id)
            return chat_service.send_message(
                merchant=merchant,
                conversation_id=conv_id,
                content="What is on the menu?",
                db=db,
                provider=provider,
                idempotency_key=shared_idempotency_key,
            )
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(run_worker)
        future2 = executor.submit(run_worker)
        res1 = future1.result()
        res2 = future2.result()

    # 1. Both workers succeeded
    assert res1 is not None
    assert res2 is not None

    # 2. Both workers returned the exact same message IDs
    assert res1.user_message.id == res2.user_message.id
    assert res1.assistant_message.id == res2.assistant_message.id
    assert res1.user_message.status == "complete"
    assert res2.assistant_message.status == "complete"

    # 3. Provider was invoked exactly once
    assert provider.call_count == 1

    # 4. In PostgreSQL database, exactly 2 messages exist for this conversation
    verify_db: Session = TestingSessionLocal()
    try:
        msg_repo = MessageRepository(verify_db)
        msgs, total = msg_repo.list_messages(conversation_id=conv_id)
        assert total == 2
        roles = [m.role for m in msgs]
        assert roles == ["user", "assistant"]
    finally:
        verify_db.close()


def test_concurrent_retries_for_same_failed_message(test_merchant_and_conversation):
    """
    Proves that concurrent retries for the same failed message across separate database
    sessions are serialized:
    - Exactly one retry succeeds (200 OK) and marks the message complete.
    - The second retry is rejected with HTTP 409 MESSAGE_ALREADY_COMPLETED.
    - Provider is invoked exactly once.
    """
    merchant_id, conv_id = test_merchant_and_conversation

    # Create an initial failed user message in PostgreSQL
    init_db: Session = TestingSessionLocal()
    try:
        msg_repo = MessageRepository(init_db)
        failed_msg = msg_repo.create(
            conversation_id=conv_id,
            role="user",
            content="Original failed query",
            status="failed",
        )
        failed_msg_id = failed_msg.id
    finally:
        init_db.close()

    provider = DelayedMockLLMProvider(delay_seconds=0.25)
    chat_service = ChatService()

    def run_retry():
        db: Session = TestingSessionLocal()
        try:
            merchant = db.get(MerchantProfile, merchant_id)
            return chat_service.send_message(
                merchant=merchant,
                conversation_id=conv_id,
                content="Retried query content",
                db=db,
                provider=provider,
                retry_message_id=failed_msg_id,
            )
        except HTTPException as exc:
            return exc
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        fut1 = executor.submit(run_retry)
        fut2 = executor.submit(run_retry)
        out1 = fut1.result()
        out2 = fut2.result()

    # One worker must succeed and one worker must receive 409 Conflict
    results = [out1, out2]
    successes = [r for r in results if not isinstance(r, HTTPException)]
    conflicts = [r for r in results if isinstance(r, HTTPException)]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}"

    conflict = conflicts[0]
    assert conflict.status_code == 409
    assert conflict.detail["error"]["code"] == "MESSAGE_ALREADY_COMPLETED"

    # Provider was called only once
    assert provider.call_count == 1

    # In PostgreSQL database, the user message is complete and there is exactly 1 assistant response
    verify_db: Session = TestingSessionLocal()
    try:
        msg_repo = MessageRepository(verify_db)
        msgs, total = msg_repo.list_messages(conversation_id=conv_id)
        assert total == 2
        user_m = next(m for m in msgs if m.role == "user")
        assert user_m.id == failed_msg_id
        assert user_m.status == "complete"
        assistant_m = next(m for m in msgs if m.role == "assistant")
        assert assistant_m.status == "complete"
    finally:
        verify_db.close()


def test_row_lock_release_on_provider_timeout_and_subsequent_retry(test_merchant_and_conversation):
    """
    Proves that when the LLM provider fails or times out:
    - User message remains saved as 'failed' in PostgreSQL.
    - Row lock on Conversation is released promptly (committed with status failed).
    - A subsequent retry can immediately acquire the lock and succeed without deadlock or hanging.
    """
    merchant_id, conv_id = test_merchant_and_conversation
    failing_provider = DelayedMockLLMProvider(delay_seconds=0.05, should_fail=True)
    success_provider = DelayedMockLLMProvider(delay_seconds=0.05, should_fail=False)
    chat_service = ChatService()

    # 1. Initial attempt fails with 502
    db1: Session = TestingSessionLocal()
    failed_id = None
    try:
        merchant = db1.get(MerchantProfile, merchant_id)
        with pytest.raises(HTTPException) as exc_info:
            chat_service.send_message(
                merchant=merchant,
                conversation_id=conv_id,
                content="Failing query",
                db=db1,
                provider=failing_provider,
            )
        assert exc_info.value.status_code == 502
        assert exc_info.value.detail["error"]["code"] == "LLM_PROVIDER_ERROR"
        failed_id = uuid.UUID(exc_info.value.detail["error"]["details"]["failed_message_id"])
        # Verify db1 has no dangling uncommitted transaction
        assert not db1.in_transaction()
    finally:
        db1.close()

    assert failed_id is not None

    # 2. Subsequent retry in a completely separate session succeeds immediately
    db2: Session = TestingSessionLocal()
    try:
        merchant = db2.get(MerchantProfile, merchant_id)
        resp = chat_service.send_message(
            merchant=merchant,
            conversation_id=conv_id,
            content="Retrying failing query",
            db=db2,
            provider=success_provider,
            retry_message_id=failed_id,
        )
        assert resp is not None
        assert resp.user_message.id == failed_id
        assert resp.user_message.status == "complete"
        assert resp.assistant_message.status == "complete"
        assert not db2.in_transaction()
    finally:
        db2.close()
