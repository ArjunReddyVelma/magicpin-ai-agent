import pytest

from services.engagement_planner import EngagementPlanner
from storage.context_store import context_store
from storage.engagement_store import engagement_store


@pytest.fixture(autouse=True)
def clear_stores():
    """
    Clear all shared in-memory stores before
    and after every test.
    """

    for scope in context_store.contexts:
        context_store.contexts[scope].clear()

    engagement_store.sent_suppression_keys.clear()

    yield

    for scope in context_store.contexts:
        context_store.contexts[scope].clear()

    engagement_store.sent_suppression_keys.clear()

@pytest.fixture
def planner(monkeypatch):
    """
    Create an EngagementPlanner with deterministic
    message generation.

    We don't want unit tests calling the real LLM.
    """

    planner = EngagementPlanner()

    monkeypatch.setattr(
        planner,
        "_compose_message",
        lambda category, merchant, trigger, customer=None:
            "Hi Rahul, this is a test engagement message.",
    )

    return planner


def add_basic_contexts():
    """
    Add the minimum category, merchant, customer,
    and trigger context required by EngagementPlanner.
    """

    from models.context import ContextRecord

    context_store.save(
        ContextRecord(
            scope="category",
            context_id="dentists",
            version=1,
            payload={
                "slug": "dentists",
                "display_name": "Dental Clinics",
            },
            delivered_at="2026-08-08T15:50:00Z",
        )
    )

    context_store.save(
        ContextRecord(
            scope="merchant",
            context_id="m_001",
            version=1,
            payload={
                "identity": {
                    "name": "Smile Dental Clinic",
                    "owner_first_name": "Meera",
                },
                "category_slug": "dentists",
            },
            delivered_at="2026-08-08T15:50:00Z",
        )
    )

    context_store.save(
        ContextRecord(
            scope="customer",
            context_id="c_001",
            version=1,
            payload={
                "identity": {
                    "name": "Rahul",
                }
            },
            delivered_at="2026-08-08T15:50:00Z",
        )
    )

    context_store.save(
        ContextRecord(
            scope="trigger",
            context_id="trg_001",
            version=1,
            payload={
                "merchant_id": "m_001",
                "customer_id": "c_001",
                "kind": "customer_lapsed_soft",
                "payload": {
                    "days_since_last_visit": 45,
                },
                "suppression_key": "test:lapsed:m_001:c_001",
                "expires_at": "2026-08-09T15:50:00Z",
            },
            delivered_at="2026-08-08T15:50:00Z",
        )
    )


def test_valid_trigger_creates_action(planner):

    add_basic_contexts()

    actions = planner.plan(
        now="2026-08-08T16:00:00Z",
        available_triggers=["trg_001"],
    )

    assert len(actions) == 1

    action = actions[0]

    assert action["merchant_id"] == "m_001"
    assert action["customer_id"] == "c_001"
    assert action["trigger_id"] == "trg_001"

    assert action["send_as"] == "merchant_on_behalf"

    assert action["template_name"] == "vera_customer_v1"

    assert action["template_params"] == [
        "Rahul",
        "Meera",
    ]

    assert action["cta"] == "YES/STOP"

    assert (
        action["suppression_key"]
        == "test:lapsed:m_001:c_001"
    )

    assert action["body"]


def test_missing_trigger_produces_no_action(planner):

    actions = planner.plan(
        now="2026-08-08T16:00:00Z",
        available_triggers=["does_not_exist"],
    )

    assert actions == []


def test_expired_trigger_produces_no_action(planner):

    add_basic_contexts()

    actions = planner.plan(
        now="2026-08-10T16:00:00Z",
        available_triggers=["trg_001"],
    )

    assert actions == []


def test_missing_merchant_produces_no_action(planner):

    from models.context import ContextRecord

    context_store.save(
        ContextRecord(
            scope="trigger",
            context_id="trg_missing_merchant",
            version=1,
            payload={
                "merchant_id": "does_not_exist",
                "customer_id": "c_001",
                "kind": "customer_lapsed_soft",
                "payload": {},
                "suppression_key": "test:missing:merchant",
            },
            delivered_at="2026-08-08T15:50:00Z",
        )
    )

    actions = planner.plan(
        now="2026-08-08T16:00:00Z",
        available_triggers=[
            "trg_missing_merchant"
        ],
    )

    assert actions == []


def test_missing_category_produces_no_action(planner):

    from models.context import ContextRecord

    context_store.save(
        ContextRecord(
            scope="merchant",
            context_id="m_002",
            version=1,
            payload={
                "identity": {
                    "name": "Test Clinic"
                },
                "category_slug": "missing_category",
            },
            delivered_at="2026-08-08T15:50:00Z",
        )
    )

    context_store.save(
        ContextRecord(
            scope="trigger",
            context_id="trg_missing_category",
            version=1,
            payload={
                "merchant_id": "m_002",
                "customer_id": "c_001",
                "kind": "customer_lapsed_soft",
                "payload": {},
                "suppression_key": "test:missing:category",
            },
            delivered_at="2026-08-08T15:50:00Z",
        )
    )

    actions = planner.plan(
        now="2026-08-08T16:00:00Z",
        available_triggers=[
            "trg_missing_category"
        ],
    )

    assert actions == []


def test_suppressed_trigger_produces_no_action(planner):

    add_basic_contexts()

    # First execution sends the engagement.
    first_actions = planner.plan(
        now="2026-08-08T16:00:00Z",
        available_triggers=["trg_001"],
    )

    assert len(first_actions) == 1

    # Second execution uses the same suppression key.
    second_actions = planner.plan(
        now="2026-08-08T16:01:00Z",
        available_triggers=["trg_001"],
    )

    assert second_actions == []