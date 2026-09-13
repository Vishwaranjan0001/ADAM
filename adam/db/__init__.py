"""Database package for ADAM."""

from adam.db.session import get_engine, get_session, init_db
from adam.db.models import (
    Base,
    Source,
    Document,
    DocumentVersion,
    DocumentPage,
    PrecedentReference,
    DocumentAttribute,
    IngestionRun,
    AccessGrant,
    AuditEvent,
    TextBlock,
    ExtractedTable,
    ProcessingRun,
    ReviewAnnotation,
    ChatSession,
    ChatTurn,
    SessionSummary,
    UserPreference,
)

__all__ = [
    "get_engine",
    "get_session",
    "init_db",
    "Base",
    "Source",
    "Document",
    "DocumentVersion",
    "DocumentPage",
    "PrecedentReference",
    "DocumentAttribute",
    "IngestionRun",
    "AccessGrant",
    "AuditEvent",
    "TextBlock",
    "ExtractedTable",
    "ProcessingRun",
    "ReviewAnnotation",
    "ChatSession",
    "ChatTurn",
    "SessionSummary",
    "UserPreference",
]


