"""Answer reconstruction service enabling 100% provenance verification without logging sensitive text."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from adam.db.models import AnswerReconstructionAudit


class AnswerReconstructionService:
    """Records and reconstructs bounded agent answers from provenance metadata."""

    @staticmethod
    def compute_request_hash(
        message: str,
        user_roles: List[str],
        collection_ids: Optional[List[str]] = None,
    ) -> str:
        """Deterministically hash the input request parameters."""
        roles_str = ",".join(sorted(user_roles or []))
        cols_str = ",".join(sorted(collection_ids or []))
        raw = f"{message.strip()}|{roles_str}|{cols_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def record_provenance(
        cls,
        db: Session,
        request_hash: str,
        trace_id: str,
        session_id: Optional[str],
        user_id: str,
        model_id: str,
        index_version_ids: List[str],
        cited_chunk_ids: List[str],
        status: str,
        prompt_version: str = "ADAM_OFFICER_PROMPT_V1",
        model_revision: str = "1.0",
    ) -> AnswerReconstructionAudit:
        """Persist answer provenance audit record."""
        audit = AnswerReconstructionAudit(
            request_hash=request_hash,
            trace_id=trace_id,
            session_id=session_id,
            user_id=user_id,
            model_id=model_id,
            model_revision=model_revision,
            prompt_version=prompt_version,
            index_version_ids=index_version_ids,
            cited_chunk_ids=cited_chunk_ids,
            status=status,
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit

    @classmethod
    def get_provenance(cls, db: Session, trace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve audit record by trace ID."""
        rec = db.query(AnswerReconstructionAudit).filter(AnswerReconstructionAudit.trace_id == trace_id).first()
        if not rec:
            return None

        return {
            "id": rec.id,
            "request_hash": rec.request_hash,
            "trace_id": rec.trace_id,
            "session_id": rec.session_id,
            "user_id": rec.user_id,
            "model_id": rec.model_id,
            "model_revision": rec.model_revision,
            "prompt_version": rec.prompt_version,
            "index_version_ids": rec.index_version_ids,
            "cited_chunk_ids": rec.cited_chunk_ids,
            "status": rec.status,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        }
