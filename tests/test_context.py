import pytest

from services.context_manager import ContextManager
from storage.context_store import context_store


@pytest.fixture(autouse=True)
def clear_context_store():
    """
    Clear the shared in-memory context store
    before and after every test.
    """
    for scope in context_store.contexts:
        context_store.contexts[scope].clear()

    yield

    for scope in context_store.contexts:
        context_store.contexts[scope].clear()


def test_save_new_context():
    manager = ContextManager()

    result = manager.save_context(
        scope="merchant",
        context_id="m_001",
        version=1,
        payload={
            "identity": {
                "name": "Smile Dental Clinic"
            }
        },
        delivered_at="2026-08-08T15:50:00Z",
    )

    assert result == ("created", None)

    context = manager.get_context(
        "merchant",
        "m_001",
    )

    assert context is not None
    assert context.version == 1
    assert (
        context.payload["identity"]["name"]
        == "Smile Dental Clinic"
    )


def test_newer_version_updates_context():
    manager = ContextManager()

    manager.save_context(
        scope="merchant",
        context_id="m_001",
        version=1,
        payload={
            "identity": {
                "name": "Old Clinic"
            }
        },
        delivered_at="2026-08-08T15:50:00Z",
    )

    result = manager.save_context(
        scope="merchant",
        context_id="m_001",
        version=2,
        payload={
            "identity": {
                "name": "Smile Dental Clinic"
            }
        },
        delivered_at="2026-08-08T15:55:00Z",
    )

    assert result == ("updated", None)

    context = manager.get_context(
        "merchant",
        "m_001",
    )

    assert context.version == 2
    assert (
        context.payload["identity"]["name"]
        == "Smile Dental Clinic"
    )


def test_stale_version_is_rejected():
    manager = ContextManager()

    manager.save_context(
        scope="merchant",
        context_id="m_001",
        version=5,
        payload={
            "identity": {
                "name": "Current Clinic"
            }
        },
        delivered_at="2026-08-08T15:50:00Z",
    )

    result = manager.save_context(
        scope="merchant",
        context_id="m_001",
        version=4,
        payload={
            "identity": {
                "name": "Old Clinic"
            }
        },
        delivered_at="2026-08-08T15:55:00Z",
    )

    assert result == ("stale", 5)

    context = manager.get_context(
        "merchant",
        "m_001",
    )

    assert context.version == 5
    assert (
        context.payload["identity"]["name"]
        == "Current Clinic"
    )


def test_same_version_is_idempotent():
    manager = ContextManager()

    payload = {
        "identity": {
            "name": "Smile Dental Clinic"
        }
    }

    first = manager.save_context(
        scope="merchant",
        context_id="m_001",
        version=1,
        payload=payload,
        delivered_at="2026-08-08T15:50:00Z",
    )

    second = manager.save_context(
        scope="merchant",
        context_id="m_001",
        version=1,
        payload=payload,
        delivered_at="2026-08-08T15:50:00Z",
    )

    assert first == ("created", None)
    assert second == ("duplicate", 1)

    context = manager.get_context(
        "merchant",
        "m_001",
    )

    assert context.version == 1


def test_invalid_scope_is_rejected():
    manager = ContextManager()

    with pytest.raises(ValueError):
        manager.save_context(
            scope="invalid_scope",
            context_id="test_001",
            version=1,
            payload={},
            delivered_at="2026-08-08T15:50:00Z",
        )


def test_scopes_are_independent():
    manager = ContextManager()

    manager.save_context(
        scope="merchant",
        context_id="m_001",
        version=1,
        payload={
            "name": "Smile Dental Clinic"
        },
        delivered_at="2026-08-08T15:50:00Z",
    )

    manager.save_context(
        scope="customer",
        context_id="m_001",
        version=1,
        payload={
            "name": "Rahul"
        },
        delivered_at="2026-08-08T15:50:00Z",
    )

    merchant = manager.get_context(
        "merchant",
        "m_001",
    )

    customer = manager.get_context(
        "customer",
        "m_001",
    )

    assert merchant.payload["name"] == "Smile Dental Clinic"
    assert customer.payload["name"] == "Rahul"