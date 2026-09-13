"""V1 Feedback API recording correction signals strictly isolated from source documents."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.api.services.idempotency import IdempotencyManager
from adam.db.models import FeedbackRecord
from adam.rag.models import UserContext

router = APIRouter(prefix="/v1", tags=["v1-feedback"])


class V1FeedbackRequest(BaseModel):
    trace_id: str = Field(..., description="Trace ID associated with the answer being reviewed")
    session_id: Optional[str] = Field(default=None, description="Chat session ID if available")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="1 to 5 quality rating")
    feedback_type: str = Field(default="CORRECTION", description="CORRECTION, ACCURACY, CITATION_MISSING, POSITIVE")
    comment: Optional[str] = Field(default=None, description="User or officer feedback comments")
    correction_text: Optional[str] = Field(default=None, description="Suggested correction to the response")
    cited_chunk_ids: Optional[List[str]] = Field(default=None, description="Chunk IDs related to the feedback")


class V1FeedbackResponse(BaseModel):
    feedback_id: str
    status: str
    trace_id: str


@router.post("/feedback", response_model=V1FeedbackResponse)
def record_feedback(
    req: V1FeedbackRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> V1FeedbackResponse:
    """Record user feedback and correction signals.

    Specification: POST /v1/feedback records correction signals separately from source truth.
    Stores signals in dedicated feedback records without mutating ground-truth documents or chunks.
    Supports idempotent submission via Idempotency-Key header.
    """
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or req.trace_id

    # 1. Check idempotency
    if idempotency_key:
        cached = IdempotencyManager.get_cached_response(
            db=db,
            key=idempotency_key,
            user_id=user_ctx.user_id,
            endpoint="/v1/feedback",
            payload=req.model_dump(),
        )
        if cached:
            status_code, cached_json = cached
            return V1FeedbackResponse(**cached_json)

    # 2. Persist feedback record
    record = FeedbackRecord(
        trace_id=req.trace_id,
        session_id=req.session_id,
        user_id=user_ctx.user_id,
        rating=req.rating,
        feedback_type=req.feedback_type,
        comment=req.comment,
        correction_text=req.correction_text,
        cited_chunk_ids=req.cited_chunk_ids,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    resp = V1FeedbackResponse(
        feedback_id=record.id,
        status="RECORDED",
        trace_id=trace_id,
    )

    # 3. Cache response if idempotency key was supplied
    if idempotency_key:
        IdempotencyManager.save_response(
            db=db,
            key=idempotency_key,
            user_id=user_ctx.user_id,
            endpoint="/v1/feedback",
            payload=req.model_dump(),
            status_code=200,
            response_json=resp.model_dump(),
        )

    return resp
