"""Tests for multi-document precedent citation graph linking and resolution."""

import fitz
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from adam.db.models import Document, DocumentVersion, PrecedentReference
from adam.extract.pipeline import DocumentExtractionPipeline
from adam.storage.local import LocalStorageBackend


def _create_test_go_pdf(order_number: str, text_content: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), f"संख्या : {order_number}", fontsize=11)
    page.insert_text((50, 80), text_content, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_precedent_chain_resolution(db_session: Session, tmp_storage: LocalStorageBackend):
    pipeline = DocumentExtractionPipeline(db_session, tmp_storage)

    # 1. Create Document A (The Precedent Order)
    pdf_a = _create_test_go_pdf(
        "GO/2021/100",
        "Subject: Initial Vehicle Advance Rules 2021 for state government employees.\nSd/- Secretary",
    )
    key_a = "docs/go_2021_100.pdf"
    tmp_storage.store(key_a, pdf_a)

    doc_a = Document(
        id="doc_precedent_a",
        title="Vehicle Advance Rules 2021",
        lifecycle_status="ACTIVE",
    )
    ver_a = DocumentVersion(
        id="ver_precedent_a",
        document_id=doc_a.id,
        source_url="https://ekosh.uk.gov.in/go_2021_100.pdf",
        go_number="GO/2021/100",
        sha256="hash_a",
        mime_type="application/pdf",
        byte_size=len(pdf_a),
        original_object_key=key_a,
    )
    doc_a.versions.append(ver_a)
    doc_a.current_version_id = ver_a.id
    db_session.add(doc_a)
    db_session.commit()

    # Process Document A
    pipeline.process_version(ver_a.id)

    # 2. Create Document B (Subsequent Order that Supersedes Document A)
    pdf_b = _create_test_go_pdf(
        "GO/2024/500",
        "Subject: Revised Vehicle Advance Rates 2024.\n"
        "In supersession of Government Order No. GO/2021/100, the revised rules are substituted.\n"
        "Sd/- Additional Chief Secretary",
    )
    key_b = "docs/go_2024_500.pdf"
    tmp_storage.store(key_b, pdf_b)

    doc_b = Document(
        id="doc_subsequent_b",
        title="Revised Vehicle Advance Rules 2024",
        lifecycle_status="ACTIVE",
    )
    ver_b = DocumentVersion(
        id="ver_subsequent_b",
        document_id=doc_b.id,
        source_url="https://ekosh.uk.gov.in/go_2024_500.pdf",
        go_number="GO/2024/500",
        sha256="hash_b",
        mime_type="application/pdf",
        byte_size=len(pdf_b),
        original_object_key=key_b,
    )
    doc_b.versions.append(ver_b)
    doc_b.current_version_id = ver_b.id
    db_session.add(doc_b)
    db_session.commit()

    # Process Document B
    pipeline.process_version(ver_b.id)

    # 3. Verify Precedent Link Resolution
    citations_b = (
        db_session.query(PrecedentReference)
        .filter(PrecedentReference.source_version_id == ver_b.id)
        .all()
    )
    assert len(citations_b) >= 1

    super_cit = next(c for c in citations_b if c.relation_type == "SUPERSEDES")
    assert super_cit.cited_order_number == "GO/2021/100"
    # Target document ID must be resolved to Document A!
    assert super_cit.target_document_id == doc_a.id

    # 4. Verify reverse resolution: Document A can query incoming citations
    incoming_to_a = (
        db_session.query(PrecedentReference)
        .filter(PrecedentReference.target_document_id == doc_a.id)
        .all()
    )
    assert len(incoming_to_a) == 1
    assert incoming_to_a[0].source_version.document_id == doc_b.id
    assert incoming_to_a[0].relation_type == "SUPERSEDES"
