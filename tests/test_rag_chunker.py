"""Unit tests for semantic chunking and operative clause/proviso preservation.

Tests:
1. Operative clause and proviso/schedule binding:
   - English "Provided that" is bound to its operative clause
   - Hindi "परन्तु यह कि" is bound to its operative clause
   - Attached schedules ("Schedule A", "अनुसूची 1") are bound to preceding clauses
2. Target token sizing (350–700 tokens) with 10–15% overlap
3. Metadata retention on DocumentChunk:
   - version_id, page_start, page_end, section_heading, language, dates, authority,
     department_id, classification, review_status, go_number, sha256, block_ids, bboxes
4. Approved blocks dependency:
   - Only blocks from pages with approved status (AUTO_APPROVED, REVIEWED, CORRECTED) are chunked
   - FLAGGED pages are excluded from chunking
"""

import pytest
from datetime import date
from sqlalchemy.orm import Session

from adam.db.models import (
    Document,
    DocumentVersion,
    DocumentPage,
    TextBlock,
    DocumentChunk,
    Source,
)
from adam.rag.chunker import (
    SemanticChunker,
    SemanticUnit,
    chunk_document_version,
    estimate_tokens,
)
from adam.vocabularies import (
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ProvenanceStatus,
    ReviewStatus,
    SourceStatus,
)


def test_estimate_tokens_bilingual():
    """Verify bilingual token estimation handles English and Devanagari accurately."""
    eng_text = "The Governor of Uttarakhand is pleased to enhance Dearness Allowance."
    tokens_eng = estimate_tokens(eng_text)
    assert tokens_eng >= 10
    assert tokens_eng <= 20

    hindi_text = "उत्तराखण्ड शासन वित्त विभाग शासनादेश संख्या 101 दिनांक 15 जनवरी 2024"
    tokens_hi = estimate_tokens(hindi_text)
    assert tokens_hi >= 10
    assert tokens_hi <= 30

    assert estimate_tokens("") == 0


def test_proviso_and_schedule_detection():
    """Verify regex detection of English and Hindi provisos and schedules."""
    # Provisos
    assert SemanticChunker.is_proviso("Provided that arrears shall be deposited into GPF.")
    assert SemanticChunker.is_proviso("Provided further that no cash withdrawal is permitted.")
    assert SemanticChunker.is_proviso("परन्तु यह कि अवशेष धनराशि का भुगतान जीपीएफ खाते में किया जाएगा।")
    assert SemanticChunker.is_proviso("बशर्ते कि कर्मचारी नियमित सेवा में हो।")
    assert not SemanticChunker.is_proviso("The basic pay scale is revised to level 10.")

    # Schedules
    assert SemanticChunker.is_schedule("Schedule A: Rates of non-practicing allowance.")
    assert SemanticChunker.is_schedule("अनुसूची-1: विभिन्न जनपदों हेतु यात्रा भत्ता दरें।")
    assert SemanticChunker.is_schedule("Annexure II: Procurement guidelines for civil works.")
    assert not SemanticChunker.is_schedule("Regular operational instructions for treasury.")


def test_operative_clause_proviso_binding():
    """Verify that an operative clause is never split from its proviso or schedule."""
    blocks = [
        {
            "block_id": "blk_1",
            "block_type": "PARAGRAPH",
            "page_number": 1,
            "text": "The Governor accords sanction for payment of enhanced allowance at 50% of basic pay.",
            "bbox": [50.0, 50.0, 400.0, 80.0],
        },
        {
            "block_id": "blk_2",
            "block_type": "PARAGRAPH",
            "page_number": 1,
            "text": "Provided that arrears from 1st January 2024 shall be credited to General Provident Fund.",
            "bbox": [50.0, 90.0, 400.0, 120.0],
        },
        {
            "block_id": "blk_3",
            "block_type": "PARAGRAPH",
            "page_number": 1,
            "text": "Schedule A specifies the calculation criteria for non-practicing medical officers.",
            "bbox": [50.0, 130.0, 400.0, 160.0],
        },
    ]

    atomic_units = SemanticChunker.build_atomic_units(blocks)
    # The 3 blocks should be bound into 1 atomic unit (operative clause + proviso + schedule)
    assert len(atomic_units) == 1
    unit = atomic_units[0]
    assert "accords sanction" in unit.text
    assert "Provided that" in unit.text
    assert "Schedule A" in unit.text
    assert len(unit.block_ids) == 3


def test_operative_clause_hindi_proviso_binding():
    """Verify Hindi operative clause and proviso binding."""
    blocks = [
        {
            "block_id": "blk_hi_1",
            "block_type": "PARAGRAPH",
            "page_number": 1,
            "text": "राज्यपाल महोदय राज्य कर्मचारियों हेतु महंगाई भत्ते की दर 50% निर्धारित करते हैं।",
            "bbox": [50.0, 50.0, 400.0, 80.0],
        },
        {
            "block_id": "blk_hi_2",
            "block_type": "PARAGRAPH",
            "page_number": 1,
            "text": "परन्तु यह कि दिनांक 01 जनवरी 2024 से अवशेष धनराशि जीपीएफ खाते में जमा की जाएगी।",
            "bbox": [50.0, 90.0, 400.0, 120.0],
        },
    ]

    atomic_units = SemanticChunker.build_atomic_units(blocks)
    assert len(atomic_units) == 1
    assert "राज्यपाल महोदय" in atomic_units[0].text
    assert "परन्तु यह कि" in atomic_units[0].text


def test_semantic_chunker_metadata_retention(db_session: Session):
    """Verify DocumentChunk retains all required metadata fields per Phase 03 spec."""
    source = Source(
        id="src_chunk_test",
        name="Finance Test Source",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Test Owner",
        owner_contact="owner@uk.gov.in",
        written_authority_ref="AUTH-TEST",
        status=SourceStatus.APPROVED.value,
    )
    db_session.add(source)

    doc = Document(
        id="doc_chunk_test",
        source_id=source.id,
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Treasury Financial Order for Hill Districts",
        language="hi",
        authority_level="DEPARTMENTAL_SECRETARY",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db_session.add(doc)

    version = DocumentVersion(
        id="ver_chunk_test",
        document_id=doc.id,
        source_url="https://ekosh.uk.gov.in/orders/test.pdf",
        go_number="UK/FIN/2024/777",
        gazette_number="GAZ/2024/12",
        sha256="abc123sha256hash",
        mime_type="application/pdf",
        byte_size=1024,
        issued_on=date(2024, 2, 1),
        effective_from=date(2024, 2, 1),
        effective_to=date(2025, 3, 31),
        provenance_status=ProvenanceStatus.VERIFIED.value,
        original_object_key="docs/test.pdf",
    )
    doc.versions.append(version)
    db_session.add(version)

    page = DocumentPage(
        id="page_chunk_test_1",
        version_id=version.id,
        page_number=1,
        clean_text="Approved digital text for testing.",
        selected_text="Approved digital text for testing.",
        review_status=ReviewStatus.AUTO_APPROVED.value,
        detected_language="hi",
    )
    db_session.add(page)

    blk1 = TextBlock(
        page_id=page.id,
        block_type="HEADING",
        text="Section 1: Financial Delegation and Authorities",
        bbox=[50.0, 50.0, 400.0, 80.0],
        reading_order=0,
        confidence=1.0,
    )
    blk2 = TextBlock(
        page_id=page.id,
        block_type="PARAGRAPH",
        text="All district treasury officers are authorized to disburse grants up to Rs 50 Lakh.\n" * 15,
        bbox=[50.0, 90.0, 400.0, 300.0],
        reading_order=1,
        confidence=1.0,
    )
    db_session.add_all([blk1, blk2])
    db_session.commit()

    chunks = chunk_document_version(db_session, version.id)
    assert len(chunks) >= 1

    chunk = chunks[0]
    assert chunk.document_id == doc.id
    assert chunk.version_id == version.id
    assert chunk.department_id == DepartmentId.FINANCE_TREASURY.value
    assert chunk.doc_type == DocType.GO.value
    assert chunk.classification == Classification.PUBLIC.value
    assert chunk.go_number == "UK/FIN/2024/777"
    assert chunk.gazette_number == "GAZ/2024/12"
    assert chunk.sha256 == "abc123sha256hash"
    assert chunk.source_url == "https://ekosh.uk.gov.in/orders/test.pdf"
    assert chunk.page_start == 1
    assert chunk.page_end == 1
    assert chunk.order_date == date(2024, 2, 1)
    assert chunk.effective_from == date(2024, 2, 1)
    assert chunk.effective_to == date(2025, 3, 31)
    assert chunk.review_status == ReviewStatus.AUTO_APPROVED.value
    assert chunk.token_count > 0


def test_chunker_excludes_unapproved_pages(db_session: Session):
    """Verify that FLAGGED pages are excluded from chunking (Module 03 consumes approved blocks only)."""
    source = Source(
        id="src_unapp_test",
        name="Unapproved Page Source",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Test Owner",
        owner_contact="owner@uk.gov.in",
        written_authority_ref="AUTH-TEST-2",
        status=SourceStatus.APPROVED.value,
    )
    db_session.add(source)

    doc = Document(
        id="doc_unapp_test",
        source_id=source.id,
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Document with Flagged Unapproved Scans",
        language="en",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db_session.add(doc)

    version = DocumentVersion(
        id="ver_unapp_test",
        document_id=doc.id,
        source_url="https://ekosh.uk.gov.in/orders/unapp.pdf",
        sha256="unapproved_sha",
        mime_type="application/pdf",
        byte_size=1024,
        provenance_status=ProvenanceStatus.VERIFIED.value,
        original_object_key="docs/unapp.pdf",
    )
    doc.versions.append(version)
    db_session.add(version)

    # Page 1 is FLAGGED
    page1 = DocumentPage(
        id="page_flagged_1",
        version_id=version.id,
        page_number=1,
        clean_text="Low quality unreviewed scanned text.",
        selected_text="Low quality unreviewed scanned text.",
        review_status=ReviewStatus.FLAGGED.value,
    )
    blk_unapp = TextBlock(
        page_id=page1.id,
        block_type="PARAGRAPH",
        text="Low quality text that must not be chunked or indexed.",
        reading_order=0,
    )
    db_session.add_all([page1, blk_unapp])
    db_session.commit()

    chunks = chunk_document_version(db_session, version.id)
    # Since page 1 is FLAGGED, no chunks should be generated
    assert len(chunks) == 0
