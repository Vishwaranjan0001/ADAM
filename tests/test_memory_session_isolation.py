"""Tests for cross-user session isolation and turn encryption at rest.

Enforces Acceptance Criterion 1:
- 'A new session cannot retrieve a prior user’s turns.'
- Field-level encryption at rest for all turn content.
"""

import pytest

from adam.db.models import ChatSession, ChatTurn
from adam.memory.session import DecryptedTurn, SessionAccessDeniedError, SessionManager


def test_cross_user_isolation_cannot_access_session(db_session):
    """Acceptance Criterion 1: A user cannot access another user's session."""
    manager = SessionManager(db_session)
    session_user_a = manager.create_session(user_id="officer_alpha", classification_ceiling="PUBLIC")

    # Access by owner succeeds
    retrieved = manager.get_session(session_user_a.id, requesting_user_id="officer_alpha")
    assert retrieved.id == session_user_a.id

    # Access by another user is strictly blocked
    with pytest.raises(SessionAccessDeniedError, match="does not belong to user 'officer_beta'"):
        manager.get_session(session_user_a.id, requesting_user_id="officer_beta")


def test_cross_user_isolation_cannot_retrieve_prior_turns(db_session):
    """Acceptance Criterion 1: A new session/user cannot retrieve a prior user's turns."""
    manager = SessionManager(db_session)
    sess_a = manager.create_session(user_id="officer_alpha")

    manager.add_turn(
        session_id=sess_a.id,
        user_id="officer_alpha",
        role="user",
        content="What is the ceiling for medical reimbursement?",
    )
    manager.add_turn(
        session_id=sess_a.id,
        user_id="officer_alpha",
        role="assistant",
        content="Under Finance Department GO 456, medical ceiling is Rs 5,00,000.",
        cited_chunk_ids=["chk_med_456"],
    )

    # Owner can read and decrypt turns
    turns_a = manager.get_turns(sess_a.id, requesting_user_id="officer_alpha")
    assert len(turns_a) == 2
    assert turns_a[0].content == "What is the ceiling for medical reimbursement?"
    assert "Rs 5,00,000" in turns_a[1].content

    # Separate user in their own new session cannot read officer_alpha's turns
    sess_b = manager.create_session(user_id="officer_beta")
    turns_b = manager.get_turns(sess_b.id, requesting_user_id="officer_beta")
    assert len(turns_b) == 0  # Brand new session has 0 turns

    # Officer beta attempting to read officer alpha's session ID directly is blocked
    with pytest.raises(SessionAccessDeniedError):
        manager.get_turns(sess_a.id, requesting_user_id="officer_beta")


def test_turn_content_encrypted_at_rest_in_db(db_session):
    """Verify raw database records store ciphertext, never plaintext."""
    manager = SessionManager(db_session)
    sess = manager.create_session(user_id="officer_gamma")

    secret_query = "Sensitive disciplinary inquiry regarding finance directorate"
    manager.add_turn(
        session_id=sess.id,
        user_id="officer_gamma",
        role="user",
        content=secret_query,
    )

    # Direct query against DB table without decryption
    raw_turn = db_session.query(ChatTurn).filter(ChatTurn.session_id == sess.id).first()
    assert raw_turn is not None
    assert raw_turn.content_ciphertext != secret_query
    assert "Sensitive" not in raw_turn.content_ciphertext
    assert "disciplinary" not in raw_turn.content_ciphertext
