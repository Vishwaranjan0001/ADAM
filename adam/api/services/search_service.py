"""Evidence search service providing ACL-filtered retrieval without model generation."""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from adam.rag.models import UserContext
from adam.rag.query import QueryUnderstanding
from adam.rag.retriever import HybridRetriever


class EvidenceSearchService:
    """Performs hybrid retrieval for evidence passages strictly without executing model generation."""

    def __init__(self, db: Session):
        self.db = db
        self.retriever = HybridRetriever(db)

    def search_evidence(
        self,
        query_str: str,
        user_context: UserContext,
        department_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        trace_id: str = "",
    ) -> Dict[str, Any]:
        """Retrieve authorized evidence chunks matching query.

        Strictly returns evidence passages and metadata. Never invokes an LLM generator.
        """
        # Parse query for explicit filters and terms
        parsed_query = QueryUnderstanding.parse(query_str)
        if department_id:
            parsed_query.department = department_id

        # Retrieve top passages with pre-ranking ACL enforcement
        fetch_k = max(1, min(100, limit + offset))
        all_passages = self.retriever.retrieve(parsed_query, user_context, top_k=fetch_k)

        # Slice according to pagination offset & limit
        total_authorized = len(all_passages)
        paged_passages = all_passages[offset : offset + limit]

        evidence_items = []
        for p in paged_passages:
            evidence_items.append({
                "chunk_id": p.chunk_id,
                "document_id": p.document_id,
                "version_id": p.version_id,
                "document_title": p.title,
                "department": p.department_id,
                "doc_type": p.doc_type,
                "page_start": p.page_start,
                "page_end": p.page_end,
                "section_heading": p.section_heading,
                "text": p.content,
                "score": round(p.score, 4),
                "bm25_score": round(p.bm25_score, 4),
                "vector_score": round(p.vector_score, 4),
                "go_number": p.go_number,
                "order_date": p.order_date.isoformat() if p.order_date else None,
                "source_url": p.source_url,
                "currency_status": p.currency_status,
                "is_amending": p.is_amending,
                "is_superseding": p.is_superseding,
            })

        return {
            "query": query_str,
            "total": total_authorized,
            "limit": limit,
            "offset": offset,
            "evidence": evidence_items,
            "trace_id": trace_id,
        }
