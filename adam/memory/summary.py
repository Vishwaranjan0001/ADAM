"""Grounded session summarizer capturing minimal, explicit conversation context.

Enforces Acceptance Criterion 2:
- 'Summary cannot introduce facts absent from cited turns; source turn IDs are retained.'
- Stores strictly: query intent, selected filters, citations already opened, user corrections.
- Never adds conversational text into the institutional retrieval index.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from adam.db.models import AuditEvent, ChatSession, SessionSummary
from adam.memory.crypto import AuthenticatedCipher, get_cipher
from adam.memory.retention import ensure_utc
from adam.memory.session import DecryptedTurn, SessionAccessDeniedError, SessionManager
from adam.rag.query import QueryUnderstanding


@dataclass
class SessionSummaryData:
    """Grounded structured per-session summary strictly tied to source turns."""
    session_id: str
    query_intents: List[str] = field(default_factory=list)
    selected_filters: Dict[str, Any] = field(default_factory=dict)
    citations_opened: List[str] = field(default_factory=list)
    user_corrections: List[str] = field(default_factory=list)
    source_turn_ids: List[str] = field(default_factory=list)
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query_intents": self.query_intents,
            "selected_filters": self.selected_filters,
            "citations_opened": self.citations_opened,
            "user_corrections": self.user_corrections,
            "source_turn_ids": self.source_turn_ids,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSummaryData":
        return cls(
            session_id=data["session_id"],
            query_intents=data.get("query_intents", []),
            selected_filters=data.get("selected_filters", {}),
            citations_opened=data.get("citations_opened", []),
            user_corrections=data.get("user_corrections", []),
            source_turn_ids=data.get("source_turn_ids", []),
            last_updated=data.get("last_updated"),
        )


class SessionSummarizer:
    """Extracts and persists minimal, grounded summaries with strict turn ID tracking."""

    # Patterns indicating explicit user corrections
    CORRECTION_PATTERNS = [
        re.compile(r"(?i)\b(?:no|wrong|incorrect|actually|instead|i meant|correct(?:ion)? is)\b[:\s]*(.*)"),
        re.compile(r"(?:नहीं|गलत|अशुद्ध|वास्तव में|मेरा मतलब|सही यह है)[:\s]*(.*)"),
    ]

    def __init__(self, db: Session, cipher: Optional[AuthenticatedCipher] = None):
        self.db = db
        self.cipher = cipher or get_cipher()
        self.session_manager = SessionManager(db, cipher=self.cipher)

    def update_summary(self, session_id: str, requesting_user_id: str) -> SessionSummaryData:
        """Analyze all turns in a session and update the grounded summary.

        Guarantees:
            1. All facts and entities in the summary trace directly to source turns.
            2. source_turn_ids tracks every turn incorporated into the summary.
            3. Summary is encrypted at rest with session TTL.
        """
        session = self.session_manager.get_session(session_id, requesting_user_id)
        turns: List[DecryptedTurn] = self.session_manager.get_turns(session_id, requesting_user_id)

        query_intents: List[str] = []
        selected_filters: Dict[str, Any] = {}
        citations_opened: List[str] = []
        user_corrections: List[str] = []
        source_turn_ids: List[str] = []

        for turn in turns:
            source_turn_ids.append(turn.id)

            if turn.role == "user":
                # Extract query understanding: intent and explicit filters
                qu = QueryUnderstanding.parse(turn.content)
                if qu.high_risk_category and qu.high_risk_category not in query_intents:
                    query_intents.append(qu.high_risk_category)
                elif qu.clean_query and len(query_intents) < 5:
                    intent_summary = qu.clean_query[:80].strip()
                    if intent_summary and intent_summary not in query_intents:
                        query_intents.append(intent_summary)

                if qu.department_id:
                    selected_filters["department_id"] = qu.department_id
                if qu.doc_type:
                    selected_filters["doc_type"] = qu.doc_type
                if qu.go_number:
                    selected_filters["go_number"] = qu.go_number
                if qu.exact_date:
                    selected_filters["exact_date"] = qu.exact_date.isoformat()

                # Check for explicit user corrections
                for pat in self.CORRECTION_PATTERNS:
                    m = pat.search(turn.content)
                    if m:
                        snippet = m.group(0).strip()
                        if snippet and snippet not in user_corrections:
                            user_corrections.append(snippet[:200])

            elif turn.role == "assistant":
                # Collect cited chunk IDs
                if turn.cited_chunk_ids:
                    for cid in turn.cited_chunk_ids:
                        if cid and cid not in citations_opened:
                            citations_opened.append(cid)

        now = datetime.now(timezone.utc)
        summary_data = SessionSummaryData(
            session_id=session.id,
            query_intents=query_intents,
            selected_filters=selected_filters,
            citations_opened=citations_opened,
            user_corrections=user_corrections,
            source_turn_ids=source_turn_ids,
            last_updated=now.isoformat(),
        )

        # Encrypt summary before writing to database
        ciphertext = self.cipher.encrypt_json(summary_data.to_dict())

        # Upsert SessionSummary
        existing_summary = self.db.query(SessionSummary).filter(SessionSummary.session_id == session.id).first()
        if existing_summary:
            existing_summary.summary_ciphertext = ciphertext
            existing_summary.source_turn_ids = source_turn_ids
            existing_summary.expires_at = session.expires_at
        else:
            new_summary = SessionSummary(
                session_id=session.id,
                summary_ciphertext=ciphertext,
                source_turn_ids=source_turn_ids,
                expires_at=session.expires_at,
            )
            self.db.add(new_summary)

        # Audit summary generation
        audit = AuditEvent(
            entity_type="CHAT_SESSION",
            entity_id=session.id,
            action="UPDATE_SUMMARY",
            actor=requesting_user_id,
            details_json={
                "turns_summarized": len(source_turn_ids),
                "intents_count": len(query_intents),
                "citations_count": len(citations_opened),
                "corrections_count": len(user_corrections),
            },
            timestamp=now,
        )
        self.db.add(audit)
        self.db.commit()

        return summary_data

    def get_summary(self, session_id: str, requesting_user_id: str) -> Optional[SessionSummaryData]:
        """Retrieve and decrypt the grounded session summary."""
        # Enforce user boundary via session manager
        session = self.session_manager.get_session(session_id, requesting_user_id)

        summary_row = self.db.query(SessionSummary).filter(SessionSummary.session_id == session.id).first()
        if not summary_row:
            return None

        # Verify not expired
        now = datetime.now(timezone.utc)
        if ensure_utc(summary_row.expires_at) <= now:
            return None

        raw_dict = self.cipher.decrypt_json(summary_row.summary_ciphertext)
        return SessionSummaryData.from_dict(raw_dict)
