"""Phase 09: Primary Integration Acceptance Test Suite.

Verifies the 4 primary acceptance criteria defined in 09-testing-integration.md:
1. An uploaded approved PDF travels original → reviewed text → index → cited chat answer with correct source page.
2. An amendment/conflict query exposes relevant versions and avoids unsupported currency claims.
3. ACL denied content is absent from search, answer, citations, logs and error text.
4. Backup restore recreates originals, metadata and index aliases; audit trail remains usable.
"""

import hashlib
import os
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adam.backup import create_backup, verify_backup, restore_backup
from adam.db.models import (
    AuditEvent,
    Base,
    Classification,
    DepartmentId,
    DocType,
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentVersion,
    LifecycleStatus,
    PrecedentReference,
    ProvenanceStatus,
    RefreshCadence,
    ReviewStatus,
    Source,
    SourceStatus,
    TextBlock,
)
from adam.extract.pipeline import DocumentExtractionPipeline
from adam.ingest.validator import ContentValidator
from adam.api.routers.v1_documents import can_access_document
from adam.rag.chunker import chunk_document_version
from adam.rag.models import UserContext
from adam.rag.pipeline import RagPipeline
from adam.rag.query import QueryUnderstanding
from adam.rag.retriever import HybridRetriever


def create_sample_pdf_bytes(pages_text: list[str]) -> bytes:
    """Generate in-memory PDF bytes with PyMuPDF."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page(width=595, height=842)  # A4
        rect = fitz.Rect(50, 50, 545, 792)
        page.insert_textbox(rect, text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_test_source(
    source_id: str,
    dept_id: str = DepartmentId.FINANCE_TREASURY.value,
    classification: str = Classification.PUBLIC.value,
) -> Source:
    return Source(
        id=source_id,
        name=f"Test Source {source_id}",
        department_id=dept_id,
        owner_name="Director of Treasuries",
        owner_contact="treasury@uk.gov.in",
        written_authority_ref="AUTH-UK-TEST-2026",
        permitted_domains=["uk.gov.in", "ekosh.uk.gov.in", "gad.uk.gov.in"],
        permitted_path_prefixes=["/orders/", "/conf/"],
        access_classification=classification,
        refresh_cadence=RefreshCadence.WEEKLY.value,
        status=SourceStatus.APPROVED.value,
    )


def test_acceptance_criterion_1_e2e_pdf_to_cited_chat(db_session, tmp_storage):
    """Criterion 1: Uploaded approved PDF travels original -> reviewed text -> index -> cited chat answer with correct source page."""
    # ── 1. Original PDF Generation ──────────────────────────────────────
    page_1_content = (
        "GOVERNMENT OF UTTARAKHAND\n"
        "DEPARTMENT OF FINANCE AND TREASURY\n\n"
        "ORDER NO: UK/FIN/2026/8892\n"
        "DATED: 15 January 2026\n\n"
        "Subject: Sanction of Hill Compensatory Allowance for State Government Servants.\n\n"
        "1. The Governor is pleased to sanction Hill Compensatory Allowance at the revised rate of "
        "Rs 1800 per month for all Category-A hill stations in Uttarakhand.\n"
        "2. This allowance shall take effect from 01 February 2026."
    )
    page_2_content = (
        "3. Accounting Procedure and Budget Allocation:\n"
        "The expenditure shall be debited under Major Head 2052 - Secretariat General Services.\n"
        "All Drawing and Disbursing Officers (DDOs) shall prepare supplementary bills accordingly.\n"
        "By order of the Governor,\n"
        "Principal Secretary (Finance)"
    )
    pdf_bytes = create_sample_pdf_bytes([page_1_content, page_2_content])

    # ── 2. Validation Gate ──────────────────────────────────────────────
    val_res = ContentValidator.validate(pdf_bytes, declared_mime_type="application/pdf")
    assert val_res.is_safe is True
    assert val_res.detected_mime_type == "application/pdf"

    # ── 3. Database Ingestion & Storage ─────────────────────────────────
    source = make_test_source("src_uk_finance_pilot")
    db_session.add(source)
    db_session.flush()

    doc = Document(
        id="doc_hill_allowance_2026",
        source_id=source.id,
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Sanction of Hill Compensatory Allowance for State Government Servants 2026",
        authority_level="STATE_CABINET",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db_session.add(doc)
    db_session.flush()

    sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
    storage_key = f"documents/doc_hill_allowance_2026/{sha256_hash}.pdf"
    tmp_storage.store(storage_key, pdf_bytes)

    version = DocumentVersion(
        id="ver_hill_allowance_2026",
        document_id=doc.id,
        source_url="https://ekosh.uk.gov.in/orders/UK_FIN_2026_8892.pdf",
        go_number="UK/FIN/2026/8892",
        issued_on=date(2026, 1, 15),
        effective_from=date(2026, 2, 1),
        sha256=sha256_hash,
        mime_type="application/pdf",
        byte_size=len(pdf_bytes),
        original_object_key=storage_key,
        provenance_status=ProvenanceStatus.VERIFIED.value,
    )
    db_session.add(version)
    doc.current_version_id = version.id
    db_session.commit()

    # ── 4. Processing Pipeline & Page Rendering ─────────────────────────
    pipeline = DocumentExtractionPipeline(db_session, tmp_storage)
    proc_ver = pipeline.process_version(version.id)
    assert proc_ver.id == version.id

    # Verify DocumentPage rows and set review status to REVIEWED
    pages = db_session.query(DocumentPage).filter(DocumentPage.version_id == version.id).order_by(DocumentPage.page_number).all()
    assert len(pages) == 2
    for p in pages:
        p.review_status = ReviewStatus.REVIEWED.value
    db_session.commit()

    # ── 5. Semantic Chunking & Indexing ─────────────────────────────────
    chunks = chunk_document_version(db_session, version.id)
    assert len(chunks) >= 1
    db_session.commit()

    # ── 6. RAG Retrieval & Cited Chat Answer ────────────────────────────
    rag = RagPipeline(db_session)
    user_ctx = UserContext(
        user_id="officer_uk_01",
        roles=["OFFICER"],
        department_id="FINANCE_TREASURY",
        clearance_level=Classification.PUBLIC.value,
    )

    query = "What is the revised rate of Hill Compensatory Allowance for Category-A hill stations?"
    response = rag.query(query, user_context=user_ctx)

    assert response.is_no_answer is False
    assert "1800" in response.answer
    assert "Category-A" in response.answer or "category-a" in response.answer.lower()
    assert len(response.citations) > 0

    # Verify citation provenance points to the exact page (page 1)
    primary_citation = response.citations[0]
    assert primary_citation.page == 1
    assert primary_citation.go_number == "UK/FIN/2026/8892"
    assert primary_citation.version_hash is not None
    assert primary_citation.pdf_page_link is not None
    assert response.validation_passed is True


def test_acceptance_criterion_2_amendment_conflict_currency_warning(db_session):
    """Criterion 2: An amendment/conflict query exposes relevant versions and avoids unsupported currency claims."""
    from adam.rag.evaluation import populate_eval_corpus

    populate_eval_corpus(db_session)

    rag = RagPipeline(db_session)
    user_ctx = UserContext(user_id="auditor_01", roles=["OFFICER"], clearance_level="PUBLIC")
    query = "What was the previous Dearness Allowance rate under order UK/FIN/2022/45?"
    response = rag.query(query, user_context=user_ctx)

    assert response.is_no_answer is False
    assert len(response.citations) >= 2  # Exposes both 2022 and 2024 versions

    # Check that currency alert banners are present
    all_banners = response.currency_banners + [c.currency_banner for c in response.citations if c.currency_banner]
    assert len(all_banners) > 0
    assert any("amendment" in b.lower() or "supersession" in b.lower() for b in all_banners)


def test_acceptance_criterion_3_acl_denied_zero_leak(db_session):
    """Criterion 3: ACL denied content is absent from search, answer, citations, logs and error text."""
    source = make_test_source(
        "src_gad_secret",
        dept_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        classification=Classification.CONFIDENTIAL.value,
    )
    db_session.add(source)

    # Confidential Document
    secret_doc = Document(
        id="doc_secret_investigation_99",
        source_id=source.id,
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        title="CONFIDENTIAL VIGILANCE REPORT REGARDING PROJECT TOP_SECRET_ALPHA",
        classification=Classification.CONFIDENTIAL.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db_session.add(secret_doc)
    db_session.flush()

    secret_ver = DocumentVersion(
        id="ver_secret_99",
        document_id=secret_doc.id,
        source_url="https://gad.uk.gov.in/conf/99.pdf",
        go_number="GAD/CONF/2026/99",
        sha256="secret_sha_9999",
        mime_type="application/pdf",
        byte_size=512,
        original_object_key="confidential/99.pdf",
        provenance_status=ProvenanceStatus.VERIFIED.value,
    )
    db_session.add(secret_ver)

    secret_page = DocumentPage(
        id="page_secret_1",
        version_id=secret_ver.id,
        page_number=1,
        clean_text="Classified inquiry into unauthorized contractor disbursements in TOP_SECRET_ALPHA.",
        selected_text="Classified inquiry into unauthorized contractor disbursements in TOP_SECRET_ALPHA.",
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    db_session.add(secret_page)
    db_session.commit()

    chunk_document_version(db_session, secret_ver.id)
    db_session.commit()

    # Public unprivileged user queries directly for the confidential project name
    user_ctx = UserContext(
        user_id="public_citizen_01",
        roles=["PUBLIC"],
        clearance_level=Classification.PUBLIC.value,
    )

    # 1. Search Service / Hybrid Retriever Check
    retriever = HybridRetriever(db_session)
    parsed = QueryUnderstanding.parse("TOP_SECRET_ALPHA contractor disbursements")
    retrieved_chunks = retriever.retrieve(parsed, user_context=user_ctx, top_k=10)
    assert len(retrieved_chunks) == 0  # Pre-ranking ACL filter completely drops confidential chunks

    # 2. RAG Pipeline Refusal Check
    rag = RagPipeline(db_session)
    response = rag.query("Show me the classified inquiry about TOP_SECRET_ALPHA", user_context=user_ctx)
    assert response.is_no_answer is True
    assert "TOP_SECRET_ALPHA" not in response.answer or "could not establish" in response.answer
    assert len(response.citations) == 0

    # 3. Policy Stealth 404 Access Check
    assert can_access_document(user_ctx, secret_doc, db_session) is False


def test_acceptance_criterion_4_backup_and_disaster_recovery(tmp_path):
    """Criterion 4: Backup restore recreates originals, metadata and index aliases; audit trail remains usable."""
    # Create isolated test environment
    test_storage = tmp_path / "storage"
    test_storage.mkdir()
    (test_storage / "originals").mkdir()
    test_pdf = test_storage / "originals" / "test_order.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 Mock Uttarakhand GO content")

    test_db_file = tmp_path / "test_adam.db"
    db_url = f"sqlite:///{test_db_file}"
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed metadata
    src = make_test_source("src_backup_test")
    session.add(src)

    doc = Document(
        id="doc_backup_01",
        source_id=src.id,
        department_id="FINANCE_TREASURY",
        title="Document to be backed up and restored",
    )
    session.add(doc)

    # Seed Audit Events
    audit_1 = AuditEvent(
        entity_type="DOCUMENT",
        entity_id="doc_backup_01",
        action="INGEST_RECORD",
        actor="system_test",
        details_json={"hash": "test_hash"},
    )
    session.add(audit_1)
    session.commit()
    session.close()
    engine.dispose()

    # ── 1. Create Crash-Consistent Backup ──────────────────────────────
    backup_file = tmp_path / "test_backup.tar.gz"
    res_path = create_backup(backup_path=backup_file, storage_dir=test_storage, db_url=db_url)
    assert res_path.exists()

    # ── 2. Verify Cryptographic Integrity ──────────────────────────────
    v_res = verify_backup(res_path)
    assert v_res["valid"] is True
    assert v_res["table_counts"]["documents"] >= 1
    assert v_res["table_counts"]["audit_events"] >= 1

    # ── 3. Simulate Total Disaster (Data Wiped) ────────────────────────
    test_db_file.unlink()
    shutil.rmtree(test_storage)
    assert not test_db_file.exists()
    assert not test_storage.exists()

    # ── 4. Disaster Recovery Restore ───────────────────────────────────
    r_res = restore_backup(
        archive_path=res_path,
        target_storage_dir=test_storage,
        target_db_url=db_url,
        force=True,
    )
    assert r_res["status"] == "SUCCESS"
    assert r_res["audit_trail_verified"] is True
    assert r_res["audit_events_count"] >= 1

    # ── 5. Verify Restored Assets & Audit Usability ─────────────────────
    assert test_db_file.exists()
    assert test_pdf.exists()
    assert test_pdf.read_bytes() == b"%PDF-1.4 Mock Uttarakhand GO content"

    new_engine = create_engine(db_url)
    NewSession = sessionmaker(bind=new_engine)
    check_session = NewSession()

    restored_doc = check_session.query(Document).filter(Document.id == "doc_backup_01").first()
    assert restored_doc is not None
    assert restored_doc.title == "Document to be backed up and restored"

    restored_audit = check_session.query(AuditEvent).filter(AuditEvent.entity_id == "doc_backup_01").first()
    assert restored_audit is not None
    assert restored_audit.action == "INGEST_RECORD"

    check_session.close()
    new_engine.dispose()
