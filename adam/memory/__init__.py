"""Conversation memory package for ADAM (Phase 05).

Provides minimal, explicit, per-session conversation memory with field-level
authenticated encryption, cross-user isolation, grounded summarization,
retention schedules, and user-visible preference controls.
"""

from adam.memory.crypto import AuthenticatedCipher, MemoryCryptoError, get_cipher
from adam.memory.preferences import (
    OptInRequiredError,
    PurposeLimitationError,
    UserPreferenceManager,
)
from adam.memory.retention import (
    RETENTION_TAG_CLASSIFIED_PII,
    RETENTION_TAG_STANDARD,
    calculate_session_expiry,
    purge_expired_sessions,
)
from adam.memory.session import (
    DecryptedTurn,
    SessionAccessDeniedError,
    SessionExpiredError,
    SessionManager,
)
from adam.memory.summary import SessionSummarizer, SessionSummaryData

__all__ = [
    "AuthenticatedCipher",
    "MemoryCryptoError",
    "get_cipher",
    "SessionManager",
    "DecryptedTurn",
    "SessionAccessDeniedError",
    "SessionExpiredError",
    "SessionSummarizer",
    "SessionSummaryData",
    "UserPreferenceManager",
    "OptInRequiredError",
    "PurposeLimitationError",
    "calculate_session_expiry",
    "purge_expired_sessions",
    "RETENTION_TAG_STANDARD",
    "RETENTION_TAG_CLASSIFIED_PII",
]
