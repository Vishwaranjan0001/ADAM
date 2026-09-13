"""Tests for grounded session summarization and source turn ID retention.

Enforces Acceptance Criterion 2:
- 'Summary cannot introduce facts absent from cited turns; source turn IDs are retained.'
- Stores strictly query intent, selected filters, citations opened, and user corrections.
"""

from adam.memory.session import SessionManager
from adam.memory.summary import SessionSummarizer, SessionSummaryData


def test_session_summary_grounding_and_turn_id_retention(db_session):
    """Acceptance Criterion 2: Verify summary retains source turn IDs and strictly reflects cited turns."""
    manager = SessionManager(db_session)
    summarizer = SessionSummarizer(db_session)

    sess = manager.create_session(user_id="analyst_1")

    # Turn 1: User asks query with explicit department filter
    t1 = manager.add_turn(
        session_id=sess.id,
        user_id="analyst_1",
        role="user",
        content="What are the finance department rules for gratuity payment?",
    )

    # Turn 2: Assistant responds with cited chunk
    t2 = manager.add_turn(
        session_id=sess.id,
        user_id="analyst_1",
        role="assistant",
        content="Under Finance Department GO 789, gratuity limit is 20 lakhs.",
        cited_chunk_ids=["chk_gratuity_789"],
    )

    # Turn 3: User provides explicit correction
    t3 = manager.add_turn(
        session_id=sess.id,
        user_id="analyst_1",
        role="user",
        content="Actually I meant for autonomous board employees instead.",
    )

    summary: SessionSummaryData = summarizer.update_summary(session_id=sess.id, requesting_user_id="analyst_1")

    # Assert source turn IDs are strictly retained
    assert t1.id in summary.source_turn_ids
    assert t2.id in summary.source_turn_ids
    assert t3.id in summary.source_turn_ids
    assert len(summary.source_turn_ids) == 3

    # Assert citations opened match cited chunks from turns
    assert "chk_gratuity_789" in summary.citations_opened

    # Assert selected filters reflect explicit query entities
    assert summary.selected_filters.get("department_id") == "FINANCE_TREASURY"

    # Assert user correction was captured
    assert any("Actually I meant" in c for c in summary.user_corrections)

    # Decrypt and verify via get_summary
    fetched = summarizer.get_summary(session_id=sess.id, requesting_user_id="analyst_1")
    assert fetched is not None
    assert fetched.source_turn_ids == [t1.id, t2.id, t3.id]
    assert fetched.citations_opened == ["chk_gratuity_789"]
