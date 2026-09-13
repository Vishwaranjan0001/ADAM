"""Retention schedules, TTL calculations, and secure content purging for conversation memory.

Enforces:
- 'Classified/PII content uses the shortest approved retention; access and deletion are audited.'
- 'Expiry/deletion removes encrypted content and makes it unavailable to retrieval; audit event remains without content.'
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from adam.db.models import AuditEvent, ChatSession, ChatTurn, SessionSummary


# Retention schedule definitions (in seconds)
RETENTION_STANDARD_SECONDS = 86_400  # 24 hours standard TTL
RETENTION_CLASSIFIED_PII_SECONDS = 3_600  # 1 hour shortest approved retention for classified / PII content

RETENTION_TAG_STANDARD = "STANDARD"
RETENTION_TAG_CLASSIFIED_PII = "CLASSIFIED_PII_SHORT"


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime has UTC timezone info for safe comparisons across DB dialects."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)



def calculate_session_expiry(
    ttl_seconds: Optional[int] = None,
    retention_tag: str = RETENTION_TAG_STANDARD,
    start_time: Optional[datetime] = None,
) -> datetime:
    """Calculate explicit session expiration timestamp based on retention tag and TTL."""
    base_time = start_time or datetime.now(timezone.utc)

    if ttl_seconds is not None and ttl_seconds > 0:
        # If tag is classified/PII, cap TTL at the shortest approved limit
        if retention_tag == RETENTION_TAG_CLASSIFIED_PII:
            effective_seconds = min(ttl_seconds, RETENTION_CLASSIFIED_PII_SECONDS)
        else:
            effective_seconds = ttl_seconds
    else:
        if retention_tag == RETENTION_TAG_CLASSIFIED_PII:
            effective_seconds = RETENTION_CLASSIFIED_PII_SECONDS
        else:
            effective_seconds = RETENTION_STANDARD_SECONDS

    return base_time + timedelta(seconds=effective_seconds)


def purge_expired_sessions(db: Session, actor: str = "system") -> Dict[str, int]:
    """Purge all sessions and content past their expiration timestamp.

    Strict Acceptance Criterion:
        'Expiry/deletion removes encrypted content and makes it unavailable
         to retrieval; audit event remains without content.'

    Returns:
        Summary dict of purged sessions and turns.
    """
    now = datetime.now(timezone.utc)
    expired_sessions = db.query(ChatSession).filter(ChatSession.expires_at <= now).all()

    purged_session_count = 0
    purged_turn_count = 0

    for sess in expired_sessions:
        turn_count = len(sess.turns) if sess.turns else 0
        user_id = sess.user_id
        session_id = sess.id
        expired_at_str = sess.expires_at.isoformat()

        # Delete the session (cascades to turns and summary)
        db.delete(sess)

        # Audit event records metadata ONLY - strictly zero conversational content
        audit = AuditEvent(
            entity_type="CHAT_SESSION",
            entity_id=session_id,
            action="PURGE_EXPIRED",
            actor=actor,
            details_json={
                "user_id": user_id,
                "turns_purged": turn_count,
                "had_summary": sess.summary is not None,
                "expired_at": expired_at_str,
                "purged_at": now.isoformat(),
            },
            timestamp=now,
        )
        db.add(audit)

        purged_session_count += 1
        purged_turn_count += turn_count

    db.commit()

    return {
        "purged_sessions": purged_session_count,
        "purged_turns": purged_turn_count,
    }
