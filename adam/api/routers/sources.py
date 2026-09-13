"""Data acquisition sources and connector governance endpoints."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.db.models import Document, Source
from adam.rag.models import UserContext
from adam.vocabularies import SourceStatus

router = APIRouter()


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Return all registered data sources, connectors, and crawl status."""
    sources = db.query(Source).order_by(Source.name.asc()).all()

    items = []
    for s in sources:
        doc_count = db.query(Document).filter(Document.source_id == s.id).count()
        domains = s.permitted_domains or []
        domain_str = ", ".join(domains) if isinstance(domains, list) else str(domains)
        items.append(
            {
                "id": s.id,
                "name": s.name,
                "department_id": s.department_id,
                "owner_name": s.owner_name,
                "permitted_domains": domains,
                "base_url": domain_str,
                "status": s.status,
                "refresh_cadence": s.refresh_cadence,
                "access_classification": s.access_classification,
                "document_count": doc_count,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
        )

    return items


@router.post("/sources/{source_id}/toggle-status")
def toggle_source_status(
    source_id: str,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Toggle source status between APPROVED and PAUSED."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    new_status = (
        SourceStatus.PAUSED.value
        if source.status == SourceStatus.APPROVED.value
        else SourceStatus.APPROVED.value
    )
    source.status = new_status
    db.commit()

    return {
        "id": source.id,
        "name": source.name,
        "status": source.status,
        "message": f"Source status updated to {new_status}",
    }
