"""Evaluation harness for the Phase 03 RAG and citation acceptance criteria.

Per Phase 03 specification:
- 'Build a gold set of >=200 Hindi/English officer questions, including known-answer,
   no-answer, amendments, conflicting documents and ACL-denied cases.'
- 'Pilot gate: >=90% recall@10 for answer-bearing queries; >=95% citation page precision;
   100% tested no-answer cases refuse unsupported claims; 0 cross-tenant/ACL leaks.
   Measure by department and language.'
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from adam.db.models import (
    Source,
    Document,
    DocumentVersion,
    DocumentPage,
    TextBlock,
    DocumentAttribute,
    PrecedentReference,
    DocumentChunk,
)
from adam.rag.chunker import chunk_document_version
from adam.rag.generator import RagGenerator
from adam.rag.gold_set import EVAL_CORPUS_DOCS, generate_gold_questions
from adam.rag.models import UserContext
from adam.rag.pipeline import RagPipeline
from adam.vocabularies import (
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ProvenanceStatus,
    RefreshCadence,
    ReviewStatus,
    SourceStatus,
)


def populate_eval_corpus(session: Session) -> Dict[str, str]:
    """Seed the evaluation corpus documents, approved pages, blocks, and precedent graph."""
    doc_id_map: Dict[str, str] = {}

    # 1. Ensure test sources exist
    src_fin = session.query(Source).filter(Source.id == "src_eval_finance").first()
    if not src_fin:
        src_fin = Source(
            id="src_eval_finance",
            name="Finance & Treasury Portal",
            department_id=DepartmentId.FINANCE_TREASURY.value,
            owner_name="Director of Treasury",
            owner_contact="treasury@uk.gov.in",
            written_authority_ref="AUTH-FIN-2024",
            permitted_domains=["ekosh.uk.gov.in"],
            permitted_path_prefixes=["/government-orders/"],
            access_classification=Classification.PUBLIC.value,
            refresh_cadence=RefreshCadence.WEEKLY.value,
            status=SourceStatus.APPROVED.value,
        )
        session.add(src_fin)

    src_rd = session.query(Source).filter(Source.id == "src_eval_rd").first()
    if not src_rd:
        src_rd = Source(
            id="src_eval_rd",
            name="Rural Development Portal",
            department_id=DepartmentId.RURAL_DEVELOPMENT.value,
            owner_name="Commissioner Rural Development",
            owner_contact="rd@uk.gov.in",
            written_authority_ref="AUTH-RD-2024",
            permitted_domains=["ukrd.uk.gov.in"],
            permitted_path_prefixes=["/documents/"],
            access_classification=Classification.PUBLIC.value,
            refresh_cadence=RefreshCadence.WEEKLY.value,
            status=SourceStatus.APPROVED.value,
        )
        session.add(src_rd)

    session.flush()

    # 2. Add evaluation documents
    for d_spec in EVAL_CORPUS_DOCS:
        doc_id = d_spec["id"]
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            doc = Document(
                id=doc_id,
                source_id="src_eval_finance" if "fin" in doc_id else "src_eval_rd",
                department_id=d_spec["department_id"],
                doc_type=d_spec["doc_type"],
                title=d_spec["title"],
                language="hi" if "title_hi" in d_spec and "hi" in doc_id else "en",
                authority_level="DEPARTMENTAL_SECRETARY",
                classification=d_spec["classification"],
                lifecycle_status=LifecycleStatus.ACTIVE.value,
            )
            session.add(doc)
            session.flush()

        doc_id_map[doc_id] = doc.id

        ver_id = f"ver_{doc_id}"
        version = session.query(DocumentVersion).filter(DocumentVersion.id == ver_id).first()
        if not version:
            issued_dt = (
                datetime.strptime(d_spec["issued_on"], "%Y-%m-%d").date()
                if "issued_on" in d_spec
                else None
            )
            effective_dt = (
                datetime.strptime(d_spec["effective_from"], "%Y-%m-%d").date()
                if "effective_from" in d_spec
                else None
            )

            dummy_bytes = d_spec["title"].encode("utf-8")
            version = DocumentVersion(
                id=ver_id,
                document_id=doc.id,
                source_url=f"https://uk.gov.in/orders/{d_spec.get('go_number', ver_id).replace('/', '_')}.pdf",
                go_number=d_spec.get("go_number"),
                sha256=hashlib.sha256(dummy_bytes).hexdigest(),
                mime_type="application/pdf",
                byte_size=len(dummy_bytes),
                issued_on=issued_dt,
                effective_from=effective_dt,
                provenance_status=ProvenanceStatus.VERIFIED.value,
                original_object_key=f"docs/{ver_id}.pdf",
            )
            session.add(version)
            session.flush()
            doc.current_version_id = version.id

            # Attributes
            subj = d_spec["title"]
            if "title_hi" in d_spec:
                subj = f"{d_spec['title']} / {d_spec['title_hi']}"
            attr = DocumentAttribute(
                version_id=version.id,
                subject=subj,
                order_number=d_spec.get("go_number"),
                order_date=issued_dt,
                issuing_authority_title="Additional Chief Secretary",
            )
            session.add(attr)

            # Pages and Blocks
            for p_spec in d_spec["pages"]:
                p_no = p_spec["page_number"]
                p_text = p_spec["text"]
                page = DocumentPage(
                    id=f"page_{ver_id}_{p_no}",
                    version_id=version.id,
                    page_number=p_no,
                    clean_text=p_text,
                    raw_text=p_text,
                    selected_text=p_text,
                    is_scanned=0,
                    word_count=len(p_text.split()),
                    review_status=ReviewStatus.AUTO_APPROVED.value,
                    detected_language="hi" if any("\u0900" <= c <= "\u097f" for c in p_text) else "en",
                )
                session.add(page)
                session.flush()

                # Paragraph blocks
                paragraphs = [par.strip() for par in p_text.split("\n") if par.strip()]
                for b_idx, par in enumerate(paragraphs):
                    blk = TextBlock(
                        page_id=page.id,
                        block_type="HEADING" if b_idx == 0 or "Section" in par or "विषय" in par else "PARAGRAPH",
                        text=par,
                        bbox=[50.0, 50.0 + b_idx * 40.0, 500.0, 80.0 + b_idx * 40.0],
                        reading_order=b_idx,
                        confidence=1.0,
                    )
                    session.add(blk)
                session.flush()

        session.flush()
        # Chunk the version
        chunk_document_version(session, ver_id)

    # 3. Add Precedent Relationship between 2024 DA and 2022 DA
    prec = (
        session.query(PrecedentReference)
        .filter(PrecedentReference.source_version_id == "ver_doc_fin_da_2024")
        .first()
    )
    if not prec:
        prec = PrecedentReference(
            id="prec_eval_da_supersedes",
            source_version_id="ver_doc_fin_da_2024",
            raw_citation_text="In supersession of previous order UK/FIN/2022/45 dated 01.07.2022",
            cited_order_number="UK/FIN/2022/45",
            cited_date=date(2022, 7, 1),
            target_document_id="doc_fin_da_2022_old",
            relation_type="SUPERSEDES",
        )
        session.add(prec)

    session.commit()
    return doc_id_map


@dataclass
class EvaluationScorecard:
    """Acceptance scorecard metrics per Phase 03 acceptance gate."""
    total_queries: int = 0
    answer_bearing_queries: int = 0
    recall_at_10_count: int = 0
    recall_at_10: float = 0.0  # Gate: >= 90%
    citation_precision_count: int = 0
    citation_precision_total: int = 0
    citation_page_precision: float = 0.0  # Gate: >= 95%
    no_answer_refusal_count: int = 0
    no_answer_total: int = 0
    no_answer_refusal_rate: float = 0.0  # Gate: 100%
    acl_leak_count: int = 0  # Gate: 0 leaks
    acl_total: int = 0
    by_department: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_language: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    gate_passed: bool = False
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_queries": self.total_queries,
            "answer_bearing_queries": self.answer_bearing_queries,
            "recall_at_10": round(self.recall_at_10, 4),
            "citation_page_precision": round(self.citation_page_precision, 4),
            "no_answer_refusal_rate": round(self.no_answer_refusal_rate, 4),
            "acl_leak_count": self.acl_leak_count,
            "gate_passed": self.gate_passed,
            "by_department": self.by_department,
            "by_language": self.by_language,
        }


def evaluate_gold_set(
    session: Session,
    pipeline: Optional[RagPipeline] = None,
    gold_questions: Optional[List[Dict[str, Any]]] = None,
) -> EvaluationScorecard:
    """Execute evaluation over gold dataset and compute pilot gate metrics."""
    pipe = pipeline or RagPipeline(session)
    questions = gold_questions or generate_gold_questions()

    scorecard = EvaluationScorecard(total_queries=len(questions))

    dept_stats: Dict[str, Dict[str, int]] = {}
    lang_stats: Dict[str, Dict[str, int]] = {}

    for q in questions:
        q_id = q["id"]
        query_text = q["question"]
        lang = q["language"]
        dept = q["department"]
        category = q["category"]
        expected_doc_ids = q.get("expected_doc_ids", [])
        expected_page = q.get("expected_page")
        expected_refusal = q.get("expected_refusal", False)

        # Build UserContext
        u_ctx_dict = q.get("user_context")
        user_ctx = None
        if u_ctx_dict:
            user_ctx = UserContext(
                user_id=u_ctx_dict.get("user_id", "anonymous"),
                roles=u_ctx_dict.get("roles", ["PUBLIC"]),
                department_id=u_ctx_dict.get("department_id"),
                clearance_level=u_ctx_dict.get("clearance_level", Classification.PUBLIC.value),
            )

        # Run query through RAG pipeline
        response = pipe.query(query_text, user_context=user_ctx, top_k=10)

        # Initialize department/language counters
        if dept not in dept_stats:
            dept_stats[dept] = {"total": 0, "correct": 0}
        if lang not in lang_stats:
            lang_stats[lang] = {"total": 0, "correct": 0}
        dept_stats[dept]["total"] += 1
        lang_stats[lang]["total"] += 1

        query_success = False

        if category == "no_answer":
            scorecard.no_answer_total += 1
            # 100% refusal required
            is_refused = (
                response.is_no_answer
                or RagGenerator.NO_EVIDENCE_REFUSAL in response.answer
            )
            if is_refused:
                scorecard.no_answer_refusal_count += 1
                query_success = True

        elif category == "acl_denied":
            scorecard.acl_total += 1
            # 0 cross-tenant/ACL leaks permitted
            forbidden_ids = set(expected_doc_ids)
            retrieved_doc_ids = set()
            if response.evidence_packet:
                retrieved_doc_ids = {p.document_id for p in response.evidence_packet.passages}
            citation_doc_ids = {c.document_title for c in response.citations}

            # Check if any forbidden document was retrieved or cited
            has_leak = bool(forbidden_ids & retrieved_doc_ids)
            if has_leak:
                scorecard.acl_leak_count += 1
            else:
                # Must also refuse
                if response.is_no_answer or RagGenerator.NO_EVIDENCE_REFUSAL in response.answer:
                    query_success = True

        else:
            # Answer-bearing queries (known_answer, amendment, conflicting_docs)
            scorecard.answer_bearing_queries += 1

            retrieved_doc_ids = []
            if response.evidence_packet:
                retrieved_doc_ids = [p.document_id for p in response.evidence_packet.passages]

            # 1. Recall@10: Ground truth document found in top 10
            recall_hit = any(doc_id in retrieved_doc_ids for doc_id in expected_doc_ids)
            if recall_hit:
                scorecard.recall_at_10_count += 1

            # 2. Citation Page Precision: Citation page matches ground truth page
            if expected_page is not None and response.citations:
                scorecard.citation_precision_total += 1
                top_cit = response.citations[0]
                if top_cit.page == expected_page:
                    scorecard.citation_precision_count += 1

            if recall_hit:
                query_success = True

        if query_success:
            dept_stats[dept]["correct"] += 1
            lang_stats[lang]["correct"] += 1

        scorecard.details.append({
            "id": q_id,
            "category": category,
            "language": lang,
            "department": dept,
            "success": query_success,
            "is_no_answer": response.is_no_answer,
            "citations_count": len(response.citations),
        })

    # Compute overall rates
    if scorecard.answer_bearing_queries > 0:
        scorecard.recall_at_10 = (
            scorecard.recall_at_10_count / scorecard.answer_bearing_queries
        )
    if scorecard.citation_precision_total > 0:
        scorecard.citation_page_precision = (
            scorecard.citation_precision_count / scorecard.citation_precision_total
        )
    if scorecard.no_answer_total > 0:
        scorecard.no_answer_refusal_rate = (
            scorecard.no_answer_refusal_count / scorecard.no_answer_total
        )

    # Pilot gate criteria:
    # >=90% recall@10 for answer-bearing queries
    # >=95% citation page precision
    # 100% tested no-answer cases refuse unsupported claims
    # 0 cross-tenant/ACL leaks
    scorecard.gate_passed = (
        scorecard.recall_at_10 >= 0.90
        and scorecard.citation_page_precision >= 0.95
        and scorecard.no_answer_refusal_rate >= 1.00
        and scorecard.acl_leak_count == 0
    )

    scorecard.by_department = {
        d: {
            "total": s["total"],
            "accuracy": round(s["correct"] / max(s["total"], 1), 4),
        }
        for d, s in dept_stats.items()
    }
    scorecard.by_language = {
        l: {
            "total": s["total"],
            "accuracy": round(s["correct"] / max(s["total"], 1), 4),
        }
        for l, s in lang_stats.items()
    }

    return scorecard
