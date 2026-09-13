"""Agent execution audit and state machine governance endpoints."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.db.models import AgentExecutionAudit
from adam.rag.models import UserContext

router = APIRouter()


@router.get("/audit/executions")
def list_execution_audits(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> List[Dict[str, Any]]:
    """Return immutable records of bounded 7-stage state machine executions."""
    records = (
        db.query(AgentExecutionAudit)
        .order_by(AgentExecutionAudit.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "user_id": r.user_id,
            "user_role": r.user_role,
            "clearance_level": r.clearance_level,
            "query_text": r.query_text,
            "model_id": r.model_id,
            "retrieval_pass_count": r.retrieval_pass_count,
            "answer_pass_count": r.answer_pass_count,
            "is_no_answer": bool(r.is_no_answer),
            "is_high_risk": bool(r.is_high_risk),
            "validation_passed": bool(r.validation_passed),
            "latency_ms": round(r.latency_ms, 2),
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "state_transitions": r.state_transitions_json or [],
            "tool_calls": r.tool_calls_json or [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
