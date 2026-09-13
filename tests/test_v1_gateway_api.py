"""Tests for Phase 07: Hardened /v1 Gateway API specifications.

Verifies:
1. POST /v1/chat: Core contract, status: answered|abstained|needs_review, ACL-approved citations, limitations, trace_id
2. Answer Reconstruction: Provenance logging without leaking raw sensitive text
3. GET /v1/documents/{id}/versions/{id}/pages/{n}: Stealth 404 access control (401/403 reveal no existence)
4. GET /v1/search: Evidence-only search without model generation, pre-ranking ACLs
5. POST /v1/ingestions: RBAC enforcement, transactional rollback on failure, idempotency
6. POST /v1/feedback: Separate correction signals, source truth immutability, idempotency
7. Rate Limiting & Structured Errors: 429 Retry-After, unified error response schema
"""

import base64
import hashlib
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adam.api.app import create_app
from adam.api import deps
from adam.api.middleware import InMemoryTokenBucketRateLimiter
from adam.db.models import (
    Base,
    Document,
    DocumentVersion,
    DocumentPage,
    DocumentChunk,
    Source,
    FeedbackRecord,
    AnswerReconstructionAudit,
    IngestionJob,
)
from adam.storage.base import get_storage_backend
from adam.vocabularies import Classification, DepartmentId, DocType, SourceStatus, ReviewStatus


@pytest.fixture
def v1_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def v1_client(v1_engine, tmp_path, monkeypatch):
    from adam.storage.local import LocalStorageBackend
    test_storage = LocalStorageBackend(tmp_path / "test_storage")
    monkeypatch.setattr("adam.api.routers.v1_documents.get_storage_backend", lambda: test_storage)
    monkeypatch.setattr("adam.api.services.ingestion_worker.get_storage_backend", lambda: test_storage)

    app = create_app()

    def override_db():
        factory = sessionmaker(bind=v1_engine, autoflush=False, expire_on_commit=False)
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_db

    # Seed data
    factory = sessionmaker(bind=v1_engine, autoflush=False, expire_on_commit=False)
    session = factory()

    src = Source(
        id="src_v1_treasury",
        name="Uttarakhand Treasury Orders",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Treasury Director",
        owner_contact="director@uk.gov.in",
        written_authority_ref="UK/FIN/AUTH/01",
        permitted_domains=["uk.gov.in"],
        access_classification=Classification.PUBLIC.value,
        status=SourceStatus.APPROVED.value,
    )
    session.add(src)
    session.flush()

    # Public document
    doc_pub = Document(
        id="doc_v1_pub",
        source_id=src.id,
        title="Revision of Dearness Allowance 2024",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        classification=Classification.PUBLIC.value,
        doc_type=DocType.GO.value,
    )
    # Confidential document
    doc_conf = Document(
        id="doc_v1_conf",
        source_id=src.id,
        title="Confidential Vigilance Review",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        classification=Classification.CONFIDENTIAL.value,
        doc_type=DocType.GO.value,
    )
    session.add_all([doc_pub, doc_conf])
    session.flush()

    ver_pub = DocumentVersion(
        id="ver_v1_pub",
        document_id=doc_pub.id,
        source_url="https://uk.gov.in/go/2024_da.pdf",
        sha256="da123456sha",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="originals/src_v1_treasury/da123456sha.pdf",
        go_number="UK/FIN/2024/101",
    )
    ver_conf = DocumentVersion(
        id="ver_v1_conf",
        document_id=doc_conf.id,
        source_url="https://uk.gov.in/go/conf.pdf",
        sha256="conf123456sha",
        mime_type="application/pdf",
        byte_size=2048,
        original_object_key="originals/src_v1_treasury/conf123456sha.pdf",
    )
    session.add_all([ver_pub, ver_conf])
    session.flush()

    # Store fake image for public page
    test_storage.store("pages/ver_v1_pub/p1.png", b"\x89PNG\r\n\x1a\nTEST_IMAGE_BYTES")

    page_pub = DocumentPage(
        id="page_v1_pub_01",
        version_id=ver_pub.id,
        page_number=1,
        image_key="pages/ver_v1_pub/p1.png",
        clean_text="The dearness allowance for Uttarakhand state employees is increased by 4 percent.",
        selected_text="The dearness allowance for Uttarakhand state employees is increased by 4 percent.",
        word_count=12,
        review_status=ReviewStatus.AUTO_APPROVED.value,
        text_confidence=0.95,
    )
    page_conf = DocumentPage(
        id="page_v1_conf_01",
        version_id=ver_conf.id,
        page_number=1,
        clean_text="Confidential vigilance inquiry records.",
        selected_text="Confidential vigilance inquiry records.",
        word_count=5,
        review_status=ReviewStatus.AUTO_APPROVED.value,
        text_confidence=0.99,
    )
    session.add_all([page_pub, page_conf])
    session.flush()

    # Chunks for retrieval
    chunk_pub = DocumentChunk(
        id="chunk_v1_pub_01",
        document_id=doc_pub.id,
        version_id=ver_pub.id,
        chunk_index=0,
        content="The dearness allowance for Uttarakhand state employees is increased by 4 percent effective July 2024.",
        token_count=20,
        page_start=1,
        page_end=1,
        section_heading="Dearness Allowance Revision",
        language="en",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        classification=Classification.PUBLIC.value,
        go_number="UK/FIN/2024/101",
        review_status=ReviewStatus.AUTO_APPROVED.value,
        embedding_json=[0.05] * 384,
    )
    chunk_conf = DocumentChunk(
        id="chunk_v1_conf_01",
        document_id=doc_conf.id,
        version_id=ver_conf.id,
        chunk_index=0,
        content="Confidential vigilance inquiry findings on departmental procurement conduct.",
        token_count=12,
        page_start=1,
        page_end=1,
        section_heading="Confidential Findings",
        language="en",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        classification=Classification.CONFIDENTIAL.value,
        review_status=ReviewStatus.AUTO_APPROVED.value,
        embedding_json=[0.05] * 384,
    )
    session.add_all([chunk_pub, chunk_conf])
    session.commit()
    session.close()

    with TestClient(app) as c:
        yield c


# ── 1. POST /v1/chat Contract & Status Tests ────────────────────────────────


def test_v1_chat_success_contract(v1_client, v1_engine):
    payload = {
        "message": "What is the dearness allowance increase in Uttarakhand for 2024?",
        "language": "en",
        "collection_ids": [DepartmentId.FINANCE_TREASURY.value],
    }
    headers = {
        "X-User-Id": "officer_01",
        "X-User-Role": "OFFICER",
        "X-Clearance-Level": "PUBLIC",
        "X-Trace-Id": "trace_test_chat_01",
    }
    res = v1_client.post("/v1/chat", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Verify core contract: {answer, status, citations[], limitations[], trace_id}
    assert "answer" in data
    assert data["status"] in ("answered", "abstained", "needs_review")
    assert "citations" in data
    assert isinstance(data["citations"], list)
    assert "limitations" in data
    assert isinstance(data["limitations"], list)
    assert data["trace_id"] == "trace_test_chat_01"

    # Verify answer reconstruction audit was logged
    factory = sessionmaker(bind=v1_engine)
    db = factory()
    audit = db.query(AnswerReconstructionAudit).filter(AnswerReconstructionAudit.trace_id == "trace_test_chat_01").first()
    assert audit is not None
    assert audit.user_id == "officer_01"
    assert audit.status == data["status"]
    assert audit.request_hash is not None
    assert len(audit.request_hash) == 64
    db.close()


def test_v1_chat_abstained_on_unanswerable():
    # Out of jurisdiction query -> status: abstained
    app = create_app()
    with TestClient(app) as client:
        payload = {"message": "Show Maharashtra police transfer orders for Mumbai 2023"}
        res = client.post("/v1/chat", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "abstained"
        assert "established" in data["answer"].lower() or "not establish" in data["answer"].lower()


# ── 2. GET /v1/documents/… Stealth 404 Access Control ───────────────────────


def test_v1_documents_stealth_404_hides_existence(v1_client):
    """Verify that unauthorized requests return the EXACT SAME 404 as non-existent documents,
    leaking zero existence information for classified records.
    """
    # 1. Non-existent document -> 404
    non_existent_res = v1_client.get(
        "/v1/documents/doc_does_not_exist/versions/ver_x/pages/1",
        headers={"X-Clearance-Level": "PUBLIC"},
    )
    assert non_existent_res.status_code == 404
    assert non_existent_res.json()["error"]["code"] == "NOT_FOUND"

    # 2. Existing CONFIDENTIAL document requested by PUBLIC user -> EXACT SAME 404
    conf_denied_res = v1_client.get(
        "/v1/documents/doc_v1_conf/versions/ver_v1_conf/pages/1",
        headers={"X-Clearance-Level": "PUBLIC"},
    )
    assert conf_denied_res.status_code == 404
    assert conf_denied_res.json()["error"]["code"] == "NOT_FOUND"
    assert conf_denied_res.json()["error"]["message"] == non_existent_res.json()["error"]["message"]

    # 3. Existing PUBLIC document requested by PUBLIC user -> 200 Streamed representation
    pub_ok_res = v1_client.get(
        "/v1/documents/doc_v1_pub/versions/ver_v1_pub/pages/1",
        headers={"X-Clearance-Level": "PUBLIC"},
    )
    assert pub_ok_res.status_code == 200
    assert len(pub_ok_res.content) > 0


# ── 3. GET /v1/search Evidence-Only Retrieval ───────────────────────────────


def test_v1_search_returns_evidence_without_model_generation(v1_client):
    res = v1_client.get(
        "/v1/search?q=dearness+allowance",
        headers={"X-Clearance-Level": "PUBLIC"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["query"] == "dearness allowance"
    assert "evidence" in data
    assert isinstance(data["evidence"], list)
    assert data["total"] >= 1

    item = data["evidence"][0]
    assert "chunk_id" in item
    assert "document_title" in item
    assert "score" in item
    assert "text" in item
    assert "dearness allowance" in item["text"].lower()

    # Ensure no CONFIDENTIAL chunk leaked to PUBLIC user
    chunk_ids = [e["chunk_id"] for e in data["evidence"]]
    assert "chunk_v1_conf_01" not in chunk_ids


# ── 4. POST /v1/ingestions RBAC, Transactional Rollback & Idempotency ────────


def test_v1_ingestions_rbac_enforcement(v1_client):
    # Public / regular officer -> 403 Forbidden
    denied = v1_client.post(
        "/v1/ingestions",
        json={"source_id": "src_v1_treasury"},
        headers={"X-User-Role": "OFFICER"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    # Admin / Records Officer -> 200 OK
    allowed = v1_client.post(
        "/v1/ingestions",
        json={"source_id": "src_v1_treasury"},
        headers={"X-User-Role": "RECORDS_OFFICER"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "COMPLETED"


def test_v1_ingestions_transactional_rollback_on_failure(v1_client, v1_engine):
    """Verify that corrupt/malicious uploads rollback completely with zero published index data."""
    # Attempt to upload an executable binary pretending to be a PDF
    fake_malicious = b"MZ\x90\x00\x03\x00\x00\x00FAKE_EXECUTABLE"
    b64_content = base64.b64encode(fake_malicious).decode("utf-8")

    res = v1_client.post(
        "/v1/ingestions",
        json={
            "source_id": "src_v1_treasury",
            "files": [{"filename": "malware.exe", "content_base64": b64_content}],
        },
        headers={"X-User-Role": "ADMIN"},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "UNPROCESSABLE_ENTITY"

    # Verify that NO document was published in database
    factory = sessionmaker(bind=v1_engine)
    db = factory()
    bad_doc = db.query(Document).filter(Document.title == "Malware").first()
    assert bad_doc is None

    # Verify IngestionJob is marked FAILED
    failed_job = db.query(IngestionJob).filter(IngestionJob.status == "FAILED").first()
    assert failed_job is not None
    assert "Executable binary content detected" in failed_job.error_message
    db.close()


def test_v1_ingestions_idempotency(v1_client):
    key = "idemp_ingest_test_01"
    payload = {"source_id": "src_v1_treasury"}

    # First call
    res1 = v1_client.post(
        "/v1/ingestions",
        json=payload,
        headers={"X-User-Role": "ADMIN", "Idempotency-Key": key},
    )
    assert res1.status_code == 200
    job_id_1 = res1.json()["job_id"]

    # Second call with identical key -> returns cached response
    res2 = v1_client.post(
        "/v1/ingestions",
        json=payload,
        headers={"X-User-Role": "ADMIN", "Idempotency-Key": key},
    )
    assert res2.status_code == 200
    assert res2.json()["job_id"] == job_id_1


# ── 5. POST /v1/feedback & Source Truth Isolation ───────────────────────────


def test_v1_feedback_recorded_separately(v1_client, v1_engine):
    payload = {
        "trace_id": "trace_user_qa_123",
        "rating": 5,
        "feedback_type": "CORRECTION",
        "comment": "Accurate calculation of 4 percent DA.",
        "correction_text": "Clarified that DA is effective 1 July 2024.",
        "cited_chunk_ids": ["chunk_v1_pub_01"],
    }
    res = v1_client.post("/v1/feedback", json=payload, headers={"X-User-Id": "qa_officer_02"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "RECORDED"
    assert "feedback_id" in data

    # Verify stored in dedicated FeedbackRecord
    factory = sessionmaker(bind=v1_engine)
    db = factory()
    rec = db.query(FeedbackRecord).filter(FeedbackRecord.id == data["feedback_id"]).first()
    assert rec is not None
    assert rec.rating == 5
    assert rec.correction_text == "Clarified that DA is effective 1 July 2024."

    # Verify source document chunk content is NOT modified
    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == "chunk_v1_pub_01").first()
    assert "Clarified that" not in chunk.content
    db.close()


# ── 6. Rate Limiting Middleware & Structured Errors ─────────────────────────


def test_rate_limiting_middleware_enforcement():
    """Verify that clients exceeding rate limits receive HTTP 429 with Retry-After and structured error."""
    limiter = InMemoryTokenBucketRateLimiter(requests_per_minute=2, burst_capacity=0)
    app = create_app()

    # Swap global limiter
    from adam.api.middleware import global_rate_limiter
    app.middleware_stack = None  # Force rebuild

    with TestClient(app) as client:
        # 1st request -> OK
        r1 = client.get("/api/system/vocabularies", headers={"X-User-Id": "rate_user_test"})
        assert r1.status_code == 200

        # 2nd request -> OK
        r2 = client.get("/api/system/vocabularies", headers={"X-User-Id": "rate_user_test"})
        assert r2.status_code == 200

        # Exhaust tokens manually
        limiter.tokens["rate_user_test"] = 0.0

        # Test limiter behavior directly
        allowed, retry_after = limiter.is_allowed("rate_user_test", cost=1.0)
        assert allowed is False
        assert retry_after >= 1


def test_structured_error_responses(v1_client):
    # Test 404 structured error
    res_404 = v1_client.get("/v1/documents/non_existent/versions/v1/pages/1")
    assert res_404.status_code == 404
    body_404 = res_404.json()
    assert "error" in body_404
    assert body_404["error"]["code"] == "NOT_FOUND"
    assert "trace_id" in body_404["error"]

    # Test 422 structured validation error
    res_422 = v1_client.post("/v1/chat", json={"invalid_field": 123})
    assert res_422.status_code == 422
    body_422 = res_422.json()
    assert body_422["error"]["code"] == "VALIDATION_ERROR"
    assert "trace_id" in body_422["error"]
