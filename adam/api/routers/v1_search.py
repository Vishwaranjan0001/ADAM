"""V1 Search API returning evidence passages strictly without model generation."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.api.services.search_service import EvidenceSearchService
from adam.rag.models import UserContext

router = APIRouter(prefix="/v1", tags=["v1-search"])


class V1EvidenceItem(BaseModel):
    chunk_id: str
    document_id: str
    version_id: str
    document_title: str
    department: Optional[str] = None
    doc_type: Optional[str] = None
    page_start: int
    page_end: int
    section_heading: Optional[str] = None
    text: str
    score: float
    bm25_score: float
    vector_score: float
    go_number: Optional[str] = None
    order_date: Optional[str] = None
    source_url: Optional[str] = None
    currency_status: str
    is_amending: bool = False
    is_superseding: bool = False


class V1SearchResponse(BaseModel):
    query: str
    total: int
    limit: int
    offset: int
    evidence: List[V1EvidenceItem]
    trace_id: str


@router.get("/search", response_model=V1SearchResponse)
def search_evidence(
    q: str = Query(..., description="Query search string"),
    department: Optional[str] = Query(default=None, description="Optional department filter"),
    limit: int = Query(default=10, ge=1, le=100, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    request: Request = None,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> V1SearchResponse:
    """Evidence retrieval endpoint.

    Specification: GET /v1/search returns evidence, not model-generated answers.
    Enforces metadata ACLs before scoring so that no unauthorized counts or chunks are disclosed.
    """
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"

    service = EvidenceSearchService(db)
    result = service.search_evidence(
        query_str=q,
        user_context=user_ctx,
        department_id=department,
        limit=limit,
        offset=offset,
        trace_id=trace_id,
    )

    return V1SearchResponse(**result)
