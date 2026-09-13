"""Tests for retention schedules, TTL calculations, and contentless audit purges.

Enforces Acceptance Criterion 3:
- 'Classified/PII content uses the shortest approved retention; access and deletion are audited.'
- 'Expiry/deletion removes encrypted content and makes it unavailable to retrieval; audit event remains without content.'
"""

from datetime import datetime, timedelta, timezone

from adam.db.models import AuditEvent, ChatSession, ChatTurn, SessionSummary
from adam.memory.retention import (
    RETENTION_CLASSIFIED_PII_SECONDS,
    RETENTION_STANDARD_SECONDS,
    RETENTION_TAG_CLASSIFIED_PII,
    RETENTION_TAG_STANDARD,
    calculate_session_expiry,
    purge_expired_sessions,
)
from adam.memory.session import SessionManager
from adam.memory.summary import SessionSummarizer


def test_retention_ttl_calculation():
    """Verify standard (24h) and classified/PII shortest (1h) retention calculations."""
    now = datetime.now(timezone.utc)
    
    # Standard TTL defaults to 24h
    exp_std = calculate_session_expiry(retention_tag=RETENTION_TAG_STANDARD, start_time=now)
    assert abs((exp_std - now).total_seconds() - RETENTION_STANDARD_SECONDS) < 5

    # Classified / PII shortest retention defaults to 1h
    exp_pii = calculate_session_expiry(retention_tag=RETENTION_TAG_CLASSIFIED_PII, start_time=now)
    assert abs((exp_pii - now).total_seconds() - RETENTION_CLASSIFIED_PII_SECONDS) < 5

    # If classified/PII requests long TTL (e.g. 10 hours), it must be capped at 1h
    exp_capped = calculate_session_expiry(
        ttl_seconds=36_000,
        retention_tag=RETENTION_TAG_CLASSIFIED_PII,
        start_time=now,
    )
    assert abs((exp_capped - now).total_seconds() - RETENTION_CLASSIFIED_PII_SECONDS) < 5


def test_purge_expired_sessions_removes_content_leaves_metadata_audit(db_session):
    """Acceptance Criterion 3: Expiry removes content; audit event remains without content."""
    manager = SessionManager(db_session)
    summarizer = SessionSummarizer(db_session)

    # 1. Create a session and populate turns
    sess = manager.create_session(user_id="officer_exp")

    turn1 = manager.add_turn(
        session_id=sess.id,
        user_id="officer_exp",
        role="user",
        content="Confidential investigation query content",
    )
    turn2 = manager.add_turn(
        session_id=sess.id,
        user_id="officer_exp",
        role="assistant",
        content="Secret operative report details",
        cited_chunk_ids=["chk_sec_001"],
    )
    summarizer.update_summary(session_id=sess.id, requesting_user_id="officer_exp")

    # Mark session as expired 10 minutes in the past
    now = datetime.now(timezone.utc)
    past_expiry = now - timedelta(minutes=10)
    sess.expires_at = past_expiry
    db_session.commit()

    # Verify rows exist before purge
    assert db_session.query(ChatSession).filter(ChatSession.id == sess.id).count() == 1
    assert db_session.query(ChatTurn).filter(ChatTurn.session_id == sess.id).count() == 2
    assert db_session.query(SessionSummary).filter(SessionSummary.session_id == sess.id).count() == 1

    # 2. Execute purge
    purge_result = purge_expired_sessions(db_session)
    assert purge_result["purged_sessions"] >= 1
    assert purge_result["purged_turns"] >= 2

    # 3. Verify content is completely removed from DB
    assert db_session.query(ChatSession).filter(ChatSession.id == sess.id).count() == 0
    assert db_session.query(ChatTurn).filter(ChatTurn.session_id == sess.id).count() == 0
    assert db_session.query(SessionSummary).filter(SessionSummary.session_id == sess.id).count() == 0

    # 4. Verify immutable AuditEvent exists WITHOUT conversational content
    purge_audits = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "CHAT_SESSION", AuditEvent.action == "PURGE_EXPIRED")
        .all()
    )
    assert len(purge_audits) >= 1
    matched = [a for a in purge_audits if a.entity_id == sess.id]
    assert len(matched) == 1
    audit = matched[0]

    # Verify zero text/summary content in audit
    details_str = str(audit.details_json)
    assert "Confidential investigation" not in details_str
    assert "Secret operative" not in details_str
    assert audit.details_json.get("turns_purged") == 2
    assert audit.details_json.get("user_id") == "officer_exp"


def test_delete_session_removes_content_leaves_audit(db_session):
    """Acceptance Criterion 3: Manual deletion removes content; audit event remains without content."""
    manager = SessionManager(db_session)
    sess = manager.create_session(user_id="user_del")

    manager.add_turn(
        session_id=sess.id,
        user_id="user_del",
        role="user",
        content="Personal tax record request",
    )

    manager.delete_session(sess.id, requesting_user_id="user_del")

    # Content removed
    assert db_session.query(ChatSession).filter(ChatSession.id == sess.id).count() == 0
    assert db_session.query(ChatTurn).filter(ChatTurn.session_id == sess.id).count() == 0

    # Audit event created without content
    audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "CHAT_SESSION", AuditEvent.entity_id == sess.id, AuditEvent.action == "DELETE")
        .first()
    )
    assert audit is not None
    assert "Personal tax" not in str(audit.details_json)
    assert audit.details_json.get("turns_deleted") == 1
