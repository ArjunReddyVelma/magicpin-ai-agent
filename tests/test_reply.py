import pytest

from services.reply_service import ReplyService
from storage.conversation_store import conversation_store


@pytest.fixture(autouse=True)
def clear_conversations():
    """
    Clear shared in-memory conversations before
    and after every test.
    """

    conversation_store._conversations.clear()

    yield

    conversation_store._conversations.clear()


@pytest.fixture
def reply_service():
    return ReplyService()


@pytest.fixture
def conversation(reply_service):
    return reply_service.memory_manager.create_conversation(
        merchant_id="m_001"
    )


def test_action_intent_returns_send(
    reply_service,
    conversation,
):
    result = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message="I want to join magicpin.",
        turn_number=1,
    )

    assert result["action"] == "send"
    assert result["body"] is not None
    assert result["cta"] == "open_ended"
    assert result["wait_seconds"] is None

    assert (
        "next step"
        in result["body"].lower()
    )


def test_wait_intent_returns_wait(
    reply_service,
    conversation,
):
    result = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message="I'm busy right now, can we talk tomorrow?",
        turn_number=1,
    )

    assert result["action"] == "wait"
    assert result["body"] is None
    assert result["cta"] is None
    assert result["wait_seconds"] == 86400


def test_later_intent_returns_one_hour_wait(
    reply_service,
    conversation,
):
    result = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message="Can we talk later?",
        turn_number=1,
    )

    assert result["action"] == "wait"
    assert result["wait_seconds"] == 3600


def test_stop_intent_returns_end(
    reply_service,
    conversation,
):
    result = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message="No thanks, I'm not interested.",
        turn_number=1,
    )

    assert result["action"] == "end"
    assert result["body"] is None
    assert result["cta"] is None
    assert result["wait_seconds"] is None


def test_unsubscribe_returns_end(
    reply_service,
    conversation,
):
    result = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message="Please unsubscribe me.",
        turn_number=1,
    )

    assert result["action"] == "end"


def test_auto_reply_returns_end(
    reply_service,
    conversation,
):
    result = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message=(
            "Thank you for contacting us. "
            "Our team will get back to you shortly."
        ),
        turn_number=1,
    )

    assert result["action"] == "end"
    assert result["body"] is None
    assert result["wait_seconds"] is None


def test_repeated_identical_reply_returns_end(
    reply_service,
    conversation,
):
    message = "Hello there"

    # First identical message.
    first = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message=message,
        turn_number=1,
    )

    assert first["action"] == "send"

    # Second identical message.
    second = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message=message,
        turn_number=2,
    )

    assert second["action"] == "end"
    assert second["body"] is None
    assert second["cta"] is None
    assert second["wait_seconds"] is None


def test_conversation_not_found(
    reply_service,
):
    with pytest.raises(
        ValueError,
        match="Conversation not found.",
    ):
        reply_service.reply(
            conversation_id="does-not-exist",
            merchant_id="m_001",
            message="Hello",
            turn_number=1,
        )


def test_merchant_mismatch(
    reply_service,
    conversation,
):
    with pytest.raises(
        ValueError,
        match="Merchant ID does not match the conversation.",
    ):
        reply_service.reply(
            conversation_id=conversation.session_id,
            merchant_id="wrong_merchant",
            message="Hello",
            turn_number=1,
        )


def test_normal_conversation_uses_composer(
    reply_service,
    conversation,
    monkeypatch,
):
    def fake_compose_reply(
        message,
        turn_number,
    ):
        return {
            "action": "send",
            "body": "Here is the next step.",
            "cta": "open_ended",
            "wait_seconds": None,
            "rationale": "Test response.",
        }

    monkeypatch.setattr(
        reply_service,
        "_compose_reply",
        fake_compose_reply,
    )

    result = reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message="Can you tell me more?",
        turn_number=1,
    )

    assert result["action"] == "send"
    assert result["body"] == "Here is the next step."
    assert result["cta"] == "open_ended"


def test_merchant_message_is_saved(
    reply_service,
    conversation,
):
    reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message="I want to join magicpin.",
        turn_number=1,
    )

    updated = (
        reply_service.memory_manager.get_conversation(
            conversation.session_id
        )
    )

    assert updated is not None

    merchant_messages = [
        message
        for message in updated.messages
        if message.role == "merchant"
    ]

    assert len(merchant_messages) == 1
    assert (
        merchant_messages[0].content
        == "I want to join magicpin."
    )


def test_send_response_is_saved(
    reply_service,
    conversation,
):
    reply_service.reply(
        conversation_id=conversation.session_id,
        merchant_id="m_001",
        message="I want to join magicpin.",
        turn_number=1,
    )

    updated = (
        reply_service.memory_manager.get_conversation(
            conversation.session_id
        )
    )

    assistant_messages = [
        message
        for message in updated.messages
        if message.role == "assistant"
    ]

    assert len(assistant_messages) == 1
    assert (
        "next step"
        in assistant_messages[0].content.lower()
    )