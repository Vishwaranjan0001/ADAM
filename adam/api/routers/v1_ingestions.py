"""V1 Ingestion API with RBAC, transactional rollback, and idempotency guarantees."""

import base64
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context, require_roles
from adam.api.services.idempotency import IdempotencyManager
from adam.api.services.ingestion_worker import TransactionalIngestionRunner
from adam.db.models import IngestionJob
from adam.rag.models import UserContext

router = APIRouter(prefix="/v1", tags=["v1-ingestions"])


class V1IngestionFilePayload(BaseModel):
    filename: str
    content_base64: str


class V1IngestionRequest(BaseModel):
    source_id: str = Field(..., description="Target registered source ID")
    files: Optional[List[V1IngestionFilePayload]] = Field(default=None, description="Optional base64 files")


class V1IngestionResponse(BaseModel):
    job_id: str
    status: str
    source_id: str
    count_found: int
    count_ingested: int
    error: Optional[str] = None
    trace_id: str


@router.post("/ingestions", response_model=V1IngestionResponse)
def trigger_ingestion(
    req: V1IngestionRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_roles("ADMIN", "RECORDS_OFFICER")),
) -> V1IngestionResponse:
    """Trigger a transactional, retry-safe ingestion job (Admin / Records-Officer only).

    Acceptance criterion: Ingestion failures are retry-safe and do not publish partial index data.
    Idempotent writes prevent duplicate jobs when Idempotency-Key is provided.
    """
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"

    # 1. Idempotency Check
    if idempotency_key:
        cached = IdempotencyManager.get_cached_response(
            db=db,
            key=idempotency_key,
            user_id=user_ctx.user_id,
            endpoint="/v1/ingestions",
            payload=req.model_dump(),
        )
        if cached:
            status_code, cached_json = cached
            return V1IngestionResponse(**cached_json)

    # 2. Decode files if provided
    file_tuples = []
    if req.files:
        for f in req.files:
            try:
                raw_bytes = base64.b64decode(f.content_base64)
                file_tuples.append((f.filename, raw_bytes))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to decode base64 file '{f.filename}': {e}")

    # 3. Execute transactional ingestion runner
    runner = TransactionalIngestionRunner(db)
    try:
        job = runner.run_ingestion(
            source_id=req.source_id,
            user_id=user_ctx.user_id,
            trace_id=trace_id,
            files=file_tuples,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Ingestion rejected without publishing partial index data: {str(exc)}",
        ) from exc

    resp = V1IngestionResponse(
        job_id=job.id,
        status=job.status,
        source_id=job.source_id,
        count_found=job.count_found,
        count_ingested=job.count_ingested,
        error=job.error_message,
        trace_id=trace_id,
    )

    # 4. Save response to idempotency cache if key was given
    if idempotency_key:
        IdempotencyManager.save_response(
            db=db,
            key=idempotency_key,
            user_id=user_ctx.user_id,
            endpoint="/v1/ingestions",
            payload=req.model_dump(),
            status_code=200,
            response_json=resp.model_dump(),
        )

    return resp


@router.get("/ingestions/{job_id}", response_model=V1IngestionResponse)
def get_ingestion_status(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_roles("ADMIN", "RECORDS_OFFICER")),
) -> V1IngestionResponse:
    """Retrieve status of an ingestion run (Admin / Records-Officer only)."""
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"

    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found.")

    return V1IngestionResponse(
        job_id=job.id,
        status=job.status,
        source_id=job.source_id,
        count_found=job.count_found,
        count_ingested=job.count_ingested,
        error=job.error_message,
        trace_id=trace_id,
    )
