import uuid
from unittest.mock import MagicMock
import pytest
from sqlalchemy.orm import Session

from backend.app.ai.context_retriever import ContextRetriever
from backend.app.models.context_item import ContextItem


def make_mock_item(
    merchant_id: uuid.UUID,
    title: str,
    content: str,
    item_type: str = "business_fact",
    is_active: bool = True,
) -> ContextItem:
    return ContextItem(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        item_type=item_type,
        title=title,
        content=content,
        is_active=is_active,
        version=1,
    )


def test_clause_aware_retrieval_combining_hours_and_beverages():
    """
    Verifies that multi-clause queries (e.g. asking about closing time AND milk in latte)
    retrieve both the operating hours context and the beverage context, preventing topic starvation.
    """
    merchant_id = uuid.uuid4()
    item_bev = make_mock_item(
        merchant_id=merchant_id,
        title="Beverage Options",
        content="We offer oat milk and almond milk for all espresso drinks for an additional ₹30.",
        item_type="service",
    )
    item_bakery = make_mock_item(
        merchant_id=merchant_id,
        title="Bakery & Pastries",
        content="Certified gluten-free almond pastries are baked fresh daily. Customers should ask staff about current availability.",
        item_type="business_fact",
    )
    item_hours = make_mock_item(
        merchant_id=merchant_id,
        title="Operating Hours",
        content="Opening hours are 8:00 AM to 8:00 PM daily.",
        item_type="operating_info",
    )

    mock_db = MagicMock(spec=Session)
    mock_db.scalars.return_value.all.return_value = [item_bev, item_bakery, item_hours]

    retriever = ContextRetriever(max_items=5)
    query = "What time do you close, and can I get almond milk in my latte?"
    retrieved = retriever.retrieve_relevant_context(merchant_id=merchant_id, query=query, db=mock_db)

    retrieved_titles = [i.title for i in retrieved]
    # Both hours and beverages must be retrieved
    assert "Operating Hours" in retrieved_titles
    assert "Beverage Options" in retrieved_titles
    # Unrelated bakery must not be chosen over the relevant clauses
    assert len(retrieved) == 2


def test_single_topic_retrieval_isolation():
    """
    Verifies that a single-topic inquiry only retrieves items matching that topic
    and does not leak unrelated active items.
    """
    merchant_id = uuid.uuid4()
    item_bev = make_mock_item(
        merchant_id=merchant_id,
        title="Beverage Options",
        content="We offer oat milk and almond milk for all espresso drinks for an additional ₹30.",
        item_type="service",
    )
    item_bakery = make_mock_item(
        merchant_id=merchant_id,
        title="Bakery & Pastries",
        content="Certified gluten-free almond pastries are baked fresh daily.",
        item_type="business_fact",
    )
    item_hours = make_mock_item(
        merchant_id=merchant_id,
        title="Operating Hours",
        content="Opening hours are 8:00 AM to 8:00 PM daily.",
        item_type="operating_info",
    )

    mock_db = MagicMock(spec=Session)
    mock_db.scalars.return_value.all.return_value = [item_bev, item_bakery, item_hours]

    retriever = ContextRetriever(max_items=5)
    query = "Do you offer oat milk?"
    retrieved = retriever.retrieve_relevant_context(merchant_id=merchant_id, query=query, db=mock_db)

    retrieved_titles = [i.title for i in retrieved]
    assert retrieved_titles == ["Beverage Options"]


def test_tenant_isolation_and_inactive_context_exclusion():
    """
    Verifies that ContextRetriever queries strictly by merchant_id and is_active is True.
    """
    merchant_a = uuid.uuid4()
    merchant_b = uuid.uuid4()

    item_a = make_mock_item(merchant_id=merchant_a, title="Merchant A Policy", content="Policy A", is_active=True)
    item_b = make_mock_item(merchant_id=merchant_b, title="Merchant B Policy", content="Policy B", is_active=True)
    item_a_inactive = make_mock_item(merchant_id=merchant_a, title="Merchant A Inactive", content="Inactive", is_active=False)

    mock_db = MagicMock(spec=Session)

    # Simulate SQL filtering: only active items for merchant_a are returned by db.scalars
    def mock_scalars(stmt):
        mock_result = MagicMock()
        # In real DB, the WHERE clause filters out merchant_b and inactive items
        mock_result.all.return_value = [item_a]
        return mock_result

    mock_db.scalars.side_effect = mock_scalars

    retriever = ContextRetriever()
    retrieved = retriever.retrieve_relevant_context(merchant_id=merchant_a, query="Policy", db=mock_db)

    # SQL call assertion
    call_args = mock_db.scalars.call_args[0][0]
    # The compiled statement must contain merchant_id and is_active filters
    stmt_str = str(call_args)
    assert "merchant_id =" in stmt_str
    assert "is_active IS true" in stmt_str or "is_active" in stmt_str

    assert len(retrieved) == 1
    assert retrieved[0].id == item_a.id
    assert retrieved[0].merchant_id == merchant_a


def test_fallback_when_no_item_scores_positive():
    """
    Verifies that when a query has no matching tokens across any items,
    retriever falls back to the top active items bounded by max_items.
    """
    merchant_id = uuid.uuid4()
    items = [
        make_mock_item(merchant_id=merchant_id, title=f"Policy {i}", content=f"Content {i}")
        for i in range(10)
    ]

    mock_db = MagicMock(spec=Session)
    mock_db.scalars.return_value.all.return_value = items

    retriever = ContextRetriever(max_items=3)
    query = "Completely unmentioned query about extraterrestrial satellites"
    retrieved = retriever.retrieve_relevant_context(merchant_id=merchant_id, query=query, db=mock_db)

    assert len(retrieved) == 3
    assert retrieved == items[:3]


def test_character_bounding_guard():
    """
    Verifies that max_total_chars limits the total characters returned.
    """
    merchant_id = uuid.uuid4()
    item1 = make_mock_item(merchant_id=merchant_id, title="Short", content="A" * 100)
    item2 = make_mock_item(merchant_id=merchant_id, title="Huge", content="B" * 2000)

    mock_db = MagicMock(spec=Session)
    mock_db.scalars.return_value.all.return_value = [item1, item2]

    # Limit total chars to 150
    retriever = ContextRetriever(max_items=5, max_total_chars=150)
    retrieved = retriever.retrieve_relevant_context(merchant_id=merchant_id, query="Short", db=mock_db)

    assert len(retrieved) == 1
    assert retrieved[0].title == "Short"
