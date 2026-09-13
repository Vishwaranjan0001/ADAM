"""Tests for Phase 02 enhanced document extraction pipeline.

Covers:
1. Full digital PDF extraction: DocumentPage, TextBlock, ProcessingRun, AuditEvent, image rendering.
2. Scanned page handling: scan detection, OCR fallback, quality gate flagging, PARTIAL result.
3. Idempotency: re-running pipeline replaces blocks and tables without duplicates and appends ProcessingRun.
4. Page count verification: Acceptance criterion 1 (100% pages accounted for, consecutive numbering).
5. Quality gate integration: review_status evaluation for digital sparse text vs. scanned pages.
6. Review annotation workflow: non-mutating reviewer corrections on DocumentPage.
"""

import fitz  # PyMuPDF
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from adam.config import COLLECTOR_VERSION
from adam.db.models import (
    AuditEvent,
    Document,
    DocumentPage,
    DocumentVersion,
    ExtractedTable,
    ProcessingRun,
    ReviewAnnotation,
    Source,
    TextBlock,
)
from adam.extract.blocks import VALID_BLOCK_TYPES
from adam.extract.pipeline import DocumentExtractionPipeline
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import (
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ProcessingResult,
    ProvenanceStatus,
    RefreshCadence,
    ReviewStatus,
    SourceStatus,
)


# ---------------------------------------------------------------------------
# Test PDF Generation Helpers
# ---------------------------------------------------------------------------

def _create_digital_pdf(pages_content: List[List[Tuple]]) -> bytes:
    """Generate a digital PDF from coordinate-text tuples per page.

    Args:
        pages_content: List of pages, where each page contains a list of
            (x, y, text, fontsize) or (x, y, text) tuples.

    Returns:
        bytes: Encoded PDF stream.
    """
    doc = fitz.open()
    for items in pages_content:
        page = doc.new_page(width=595, height=842)  # Standard A4
        for item in items:
            if len(item) == 4:
                x, y, text, fontsize = item
            elif len(item) == 3:
                x, y, text = item
                fontsize = 11
            else:
                raise ValueError(f"Invalid item format: {item}")
            page.insert_text((x, y), text, fontsize=fontsize)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _create_scanned_pdf(text_content: str = "Scan header") -> bytes:
    """Generate a PDF containing an embedded bitmap image and minimal text (< 50 chars).

    Args:
        text_content: Sparse text string to place on the page (must be < 50 chars).

    Returns:
        bytes: Encoded PDF stream.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Insert a dummy raster pixmap image to simulate a scanned document
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 500), 1)
    pix.clear_with(240)  # Near-white grayscale raster
    page.insert_image(page.rect, pixmap=pix)

    if text_content:
        page.insert_text((50, 50), text_content, fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _create_pdf_with_table() -> bytes:
    """Generate a PDF containing body text and a fully bordered table detected by PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Narrative content
    page.insert_text((50, 50), "Uttarakhand Government - Finance Department", fontsize=14)
    page.insert_text((50, 75), "Order No: UK/FIN/2024/999", fontsize=11)
    page.insert_text((50, 100), "Subject: Revision of Employee Allowances Schedule.", fontsize=11)

    # Structured table with bounding borders
    x_cols = [50, 200, 350, 500]
    y_rows = [130, 160, 190, 220]

    for y in y_rows:
        page.draw_line(fitz.Point(x_cols[0], y), fitz.Point(x_cols[-1], y))
    for x in x_cols:
        page.draw_line(fitz.Point(x, y_rows[0]), fitz.Point(x, y_rows[-1]))

    page.insert_text((60, 150), "Cadre Designation")
    page.insert_text((210, 150), "Old Allowance")
    page.insert_text((360, 150), "New Allowance")

    page.insert_text((60, 180), "Administrative Officers")
    page.insert_text((210, 180), "Rs 5,000")
    page.insert_text((360, 180), "Rs 8,000")

    page.insert_text((60, 210), "Secretariat Assistants")
    page.insert_text((210, 210), "Rs 3,000")
    page.insert_text((360, 210), "Rs 5,000")

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# Database & Ingestion Setup Helpers
# ---------------------------------------------------------------------------

def _create_approved_source(
    session: Session,
    source_id: str = "src_phase2_test",
    department_id: str = DepartmentId.FINANCE_TREASURY.value,
) -> Source:
    """Create and persist an APPROVED source registry entry."""
    source = session.query(Source).filter(Source.id == source_id).first()
    if source:
        return source

    source = Source(
        id=source_id,
        name="Uttarakhand Finance Portal (Ekosh)",
        department_id=department_id,
        owner_name="IT Directorate, Finance",
        owner_contact="it-finance@uk.gov.in",
        written_authority_ref="AUTH-UK-FIN-2024-V2",
        permitted_domains=["ekosh.uk.gov.in"],
        permitted_path_prefixes=["/government-orders/"],
        access_classification=Classification.PUBLIC.value,
        refresh_cadence=RefreshCadence.WEEKLY.value,
        rate_limit_per_minute=60,
        retention_policy="PERMANENT",
        status=SourceStatus.APPROVED.value,
    )
    session.add(source)
    session.flush()
    return source


def _setup_document_and_version(
    session: Session,
    storage: LocalStorageBackend,
    pdf_bytes: bytes,
    source: Source,
    doc_id: str,
    version_id: str,
    go_number: str = "UK/FIN/2024/789",
) -> DocumentVersion:
    """Store PDF in immutable storage and link Source, Document, and DocumentVersion."""
    storage_key = f"documents/{version_id}.pdf"
    storage.store(key=storage_key, data=pdf_bytes)

    sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()

    doc = Document(
        id=doc_id,
        source_id=source.id,
        department_id=source.department_id,
        doc_type=DocType.GO.value,
        title="Sanction of Annual Budgetary Allocations for Public Infrastructure Projects",
        language="en",
        authority_level="DEPARTMENTAL_SECRETARY",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    session.add(doc)

    version = DocumentVersion(
        id=version_id,
        document_id=doc.id,
        source_url=f"https://ekosh.uk.gov.in/orders/{version_id}.pdf",
        go_number=go_number,
        sha256=sha256_hash,
        mime_type="application/pdf",
        byte_size=len(pdf_bytes),
        provenance_status=ProvenanceStatus.VERIFIED.value,
        original_object_key=storage_key,
    )
    doc.versions.append(version)
    doc.current_version_id = version.id
    session.add(version)
    session.commit()
    return version


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_phase2_pipeline_full_extraction(
    db_session: Session,
    tmp_storage: LocalStorageBackend,
):
    """Test the full Phase 02 extraction pipeline on a digital 2-page PDF:

    Assertions:
    a. DocumentPage rows created with page_number, clean_text, selected_text, review_status
    b. image_key is populated with valid rendered page images (PNG)
    c. TextBlock rows exist with valid block_type, text, bbox, reading_order
    d. ProcessingRun row created with parser_version, config_hash, result='SUCCESS'
    e. Page count matches original PDF (acceptance criterion 1)
    f. AuditEvent with action='TEXT_EXTRACTION' created
    """
    # 1. Create a 2-page digital PDF with English text
    pdf_bytes = _create_digital_pdf([
        [
            (50, 60, "Government of Uttarakhand Finance Department Notification", 16),
            (50, 100, "Order No: UK/FIN/2024/789", 12),
            (50, 140, "Subject: Sanction of Annual Budgetary Allocations for Public Infrastructure Projects.", 12),
            (50, 180, "The Governor of Uttarakhand accords financial sanction for infrastructural development in hill districts.", 11),
            (50, 220, "All implementing departments shall adhere to standard procurement procedure and treasury guidelines.", 11),
        ],
        [
            (50, 60, "Annexure: Guidelines for Expenditure Control and Monitoring", 14),
            (50, 100, "1. Monthly expenditure reports must be submitted to the treasury by the fifth of every subsequent month.", 11),
            (50, 140, "2. Capital funds cannot be reallocated or transferred into recurring revenue expenditure streams.", 11),
            (50, 180, "By Order and in the name of the Governor of Uttarakhand.", 11),
            (50, 220, "Additional Chief Secretary to the Government of Uttarakhand Finance Department.", 11),
        ],
    ])

    source = _create_approved_source(db_session, source_id="src_full_ext")
    version = _setup_document_and_version(
        db_session,
        tmp_storage,
        pdf_bytes,
        source=source,
        doc_id="doc_full_ext",
        version_id="ver_full_ext",
    )

    # 2. Run the extraction pipeline
    pipeline = DocumentExtractionPipeline(db_session, tmp_storage)
    pipeline.process_version(version.id, actor="pipeline_test_runner")

    # -----------------------------------------------------------------------
    # Assertion a: DocumentPage rows created with correct fields
    # -----------------------------------------------------------------------
    pages = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    assert len(pages) == 2

    # Page 1 checks
    p1 = pages[0]
    assert p1.page_number == 1
    assert "Finance Department Notification" in p1.clean_text
    assert "Sanction of Annual Budgetary Allocations" in p1.clean_text
    assert p1.selected_text == p1.clean_text
    assert p1.review_status == ReviewStatus.AUTO_APPROVED.value
    assert p1.is_scanned == 0
    assert p1.word_count > 10

    # Page 2 checks
    p2 = pages[1]
    assert p2.page_number == 2
    assert "Guidelines for Expenditure Control" in p2.clean_text
    assert p2.selected_text == p2.clean_text
    assert p2.review_status == ReviewStatus.AUTO_APPROVED.value
    assert p2.is_scanned == 0
    assert p2.word_count > 10

    # -----------------------------------------------------------------------
    # Assertion b: image_key is populated and stored as PNG
    # -----------------------------------------------------------------------
    assert p1.image_key is not None
    assert p1.image_key.startswith(f"pages/{version.id}/")
    assert tmp_storage.exists(p1.image_key)
    p1_img_data = tmp_storage.get(p1.image_key)
    assert p1_img_data.startswith(b"\x89PNG")

    assert p2.image_key is not None
    assert p2.image_key.startswith(f"pages/{version.id}/")
    assert tmp_storage.exists(p2.image_key)
    p2_img_data = tmp_storage.get(p2.image_key)
    assert p2_img_data.startswith(b"\x89PNG")

    # -----------------------------------------------------------------------
    # Assertion c: TextBlock rows exist with valid block_type, text, bbox, reading_order
    # -----------------------------------------------------------------------
    blocks_p1 = (
        db_session.query(TextBlock)
        .filter(TextBlock.page_id == p1.id)
        .order_by(TextBlock.reading_order)
        .all()
    )
    assert len(blocks_p1) > 0

    for blk in blocks_p1:
        assert blk.block_type in VALID_BLOCK_TYPES
        assert isinstance(blk.text, str) and len(blk.text.strip()) > 0
        assert isinstance(blk.bbox, list) and len(blk.bbox) == 4
        # Verify coordinates: x0 < x1, y0 < y1
        assert blk.bbox[0] < blk.bbox[2]
        assert blk.bbox[1] < blk.bbox[3]
        assert blk.reading_order >= 0
        assert blk.confidence is not None and blk.confidence > 0.0

    blocks_p2 = (
        db_session.query(TextBlock)
        .filter(TextBlock.page_id == p2.id)
        .order_by(TextBlock.reading_order)
        .all()
    )
    assert len(blocks_p2) > 0
    for blk in blocks_p2:
        assert blk.block_type in VALID_BLOCK_TYPES
        assert blk.reading_order >= 0

    # -----------------------------------------------------------------------
    # Assertion d: ProcessingRun row created with parser_version, config_hash, result='SUCCESS'
    # -----------------------------------------------------------------------
    prun = (
        db_session.query(ProcessingRun)
        .filter(ProcessingRun.version_id == version.id)
        .first()
    )
    assert prun is not None
    assert prun.parser_version == COLLECTOR_VERSION
    assert prun.config_hash is not None and len(prun.config_hash) == 64
    assert prun.result == ProcessingResult.SUCCESS.value
    assert prun.started_at is not None
    assert prun.completed_at is not None
    assert prun.completed_at >= prun.started_at
    assert prun.details_json["page_count"] == 2
    assert prun.details_json["expected_page_count"] == 2

    # -----------------------------------------------------------------------
    # Assertion e: Page count matches original PDF (acceptance criterion 1)
    # -----------------------------------------------------------------------
    db_session.refresh(version)
    assert len(version.pages) == 2
    assert [p.page_number for p in version.pages] == [1, 2]

    # -----------------------------------------------------------------------
    # Assertion f: AuditEvent with action='TEXT_EXTRACTION' created
    # -----------------------------------------------------------------------
    audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.entity_type == "DOCUMENT_VERSION",
            AuditEvent.entity_id == version.id,
            AuditEvent.action == "TEXT_EXTRACTION",
        )
        .first()
    )
    assert audit is not None
    assert audit.actor == "pipeline_test_runner"
    assert audit.details_json["page_count"] == 2
    assert audit.details_json["processing_run_result"] == ProcessingResult.SUCCESS.value


def test_phase2_pipeline_scanned_page_handling(
    db_session: Session,
    tmp_storage: LocalStorageBackend,
):
    """Test scanned page handling when OCR engine is NullOcrEngine:

    Assertions:
    a. is_scanned = 1
    b. review_status = 'FLAGGED' (because OCR_UNAVAILABLE on this machine)
    c. ocr_text is empty string (NullOcrEngine)
    d. ProcessingRun result = 'PARTIAL'
    """
    # Create PDF with embedded raster image and sparse text (< 50 chars threshold)
    pdf_bytes = _create_scanned_pdf(text_content="Scan Page 1")

    source = _create_approved_source(db_session, source_id="src_scanned_test")
    version = _setup_document_and_version(
        db_session,
        tmp_storage,
        pdf_bytes,
        source=source,
        doc_id="doc_scanned_test",
        version_id="ver_scanned_test",
    )

    pipeline = DocumentExtractionPipeline(db_session, tmp_storage)
    pipeline.process_version(version.id)

    # -----------------------------------------------------------------------
    # Assertions a, b, c on DocumentPage
    # -----------------------------------------------------------------------
    page = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .first()
    )
    assert page is not None
    assert page.is_scanned == 1
    assert page.review_status == ReviewStatus.FLAGGED.value
    assert page.ocr_text == ""
    assert page.text_confidence == 0.0

    # -----------------------------------------------------------------------
    # Assertion d: ProcessingRun result is PARTIAL
    # -----------------------------------------------------------------------
    prun = (
        db_session.query(ProcessingRun)
        .filter(ProcessingRun.version_id == version.id)
        .first()
    )
    assert prun is not None
    assert prun.result == ProcessingResult.PARTIAL.value
    assert prun.details_json["quality"]["flagged_pages"] == 1
    assert prun.details_json["has_scanned_pages"] is True


def test_phase2_pipeline_idempotency(
    db_session: Session,
    tmp_storage: LocalStorageBackend,
):
    """Test that re-running pipeline clears old records and preserves idempotency:

    Assertions:
    - First run creates TextBlock and ExtractedTable records
    - Second run replaces records without duplicating TextBlock, ExtractedTable, or DocumentPage
    - A new ProcessingRun audit record is appended for the second run
    """
    pdf_bytes = _create_pdf_with_table()

    source = _create_approved_source(db_session, source_id="src_idempotent_test")
    version = _setup_document_and_version(
        db_session,
        tmp_storage,
        pdf_bytes,
        source=source,
        doc_id="doc_idempotent_test",
        version_id="ver_idempotent_test",
    )

    pipeline = DocumentExtractionPipeline(db_session, tmp_storage)

    # 1. First execution
    pipeline.process_version(version.id)

    blocks_run1 = (
        db_session.query(TextBlock)
        .join(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .all()
    )
    tables_run1 = (
        db_session.query(ExtractedTable)
        .join(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .all()
    )
    pages_run1 = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .all()
    )
    runs_run1 = (
        db_session.query(ProcessingRun)
        .filter(ProcessingRun.version_id == version.id)
        .all()
    )

    # Confirm initial records exist
    assert len(blocks_run1) > 0
    assert len(tables_run1) > 0
    assert len(pages_run1) == 1
    assert len(runs_run1) == 1

    # Verify extracted table properties
    table = tables_run1[0]
    assert table.extraction_method == "PYMUPDF"
    assert table.table_data_json is not None
    assert table.table_data_json["col_count"] >= 3

    # 2. Second execution on the same document version
    pipeline.process_version(version.id)

    blocks_run2 = (
        db_session.query(TextBlock)
        .join(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .all()
    )
    tables_run2 = (
        db_session.query(ExtractedTable)
        .join(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .all()
    )
    pages_run2 = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .all()
    )
    runs_run2 = (
        db_session.query(ProcessingRun)
        .filter(ProcessingRun.version_id == version.id)
        .all()
    )

    # Confirm old records are replaced without duplication
    assert len(blocks_run2) == len(blocks_run1)
    assert len(tables_run2) == len(tables_run1)
    assert len(pages_run2) == len(pages_run1)

    # Confirm a new ProcessingRun is created
    assert len(runs_run2) == 2


def test_phase2_pipeline_page_count_verification(
    db_session: Session,
    tmp_storage: LocalStorageBackend,
):
    """Test acceptance criterion 1: 100% pages accounted for in sequential order.

    Assertions:
    - 3-page PDF produces exactly 3 DocumentPage rows with consecutive page_numbers [1, 2, 3]
    - If extracted page count does not match expected page count, pipeline raises ValueError
    """
    pdf_bytes = _create_digital_pdf([
        [(50, 60, "Section 1: Preamble and Legislative Authority of Uttarakhand Public Works", 12)],
        [(50, 60, "Section 2: Tender Evaluation and Financial Committee Constitution", 12)],
        [(50, 60, "Section 3: Standard Operating Procedures for Quality Inspection and Auditing", 12)],
    ])

    source = _create_approved_source(db_session, source_id="src_page_count_test")
    version = _setup_document_and_version(
        db_session,
        tmp_storage,
        pdf_bytes,
        source=source,
        doc_id="doc_page_count_test",
        version_id="ver_page_count_test",
    )

    pipeline = DocumentExtractionPipeline(db_session, tmp_storage)
    pipeline.process_version(version.id)

    # Verify 3 DocumentPage rows with consecutive page_numbers
    pages = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.version_id == version.id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    assert len(pages) == 3
    assert [p.page_number for p in pages] == [1, 2, 3]

    # Verify acceptance criterion 1 error handling on mismatch
    with patch("adam.extract.pdf.PdfExtractor.get_page_count", return_value=4):
        with pytest.raises(ValueError, match="Page count mismatch"):
            pipeline.process_version(version.id)


def test_phase2_quality_gates_in_pipeline(
    db_session: Session,
    tmp_storage: LocalStorageBackend,
):
    """Test quality gate integration:

    Assertions:
    - Digital page with sparse text (< 20 chars) triggers LOW_CHAR_YIELD WARNING,
      which retains AUTO_APPROVED status.
    - Scanned page without OCR text triggers LOW_CONFIDENCE and OCR_UNAVAILABLE
      with REQUIRES_REVIEW severity, which sets review_status to FLAGGED.
    """
    source = _create_approved_source(db_session, source_id="src_quality_gate_test")

    # Case A: Digital PDF with minimal text (< 20 chars)
    doc_digital = fitz.open()
    page_digital = doc_digital.new_page()
    page_digital.insert_text((50, 50), "Short text", fontsize=10)  # 10 characters
    digital_pdf_bytes = doc_digital.tobytes()
    doc_digital.close()

    version_a = _setup_document_and_version(
        db_session,
        tmp_storage,
        digital_pdf_bytes,
        source=source,
        doc_id="doc_quality_digital",
        version_id="ver_quality_digital",
    )

    pipeline = DocumentExtractionPipeline(db_session, tmp_storage)
    pipeline.process_version(version_a.id)

    page_a = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.version_id == version_a.id)
        .first()
    )
    assert page_a is not None
    assert page_a.is_scanned == 0
    assert len(page_a.clean_text) < 20
    # Digital low char yield is a WARNING -> AUTO_APPROVED
    assert page_a.review_status == ReviewStatus.AUTO_APPROVED.value

    run_a = (
        db_session.query(ProcessingRun)
        .filter(ProcessingRun.version_id == version_a.id)
        .first()
    )
    assert run_a.result == ProcessingResult.SUCCESS.value

    # Case B: Scanned page with sparse text and raster image
    scanned_pdf_bytes = _create_scanned_pdf(text_content="Sparse scan")
    version_b = _setup_document_and_version(
        db_session,
        tmp_storage,
        scanned_pdf_bytes,
        source=source,
        doc_id="doc_quality_scanned",
        version_id="ver_quality_scanned",
    )

    pipeline.process_version(version_b.id)

    page_b = (
        db_session.query(DocumentPage)
        .filter(DocumentPage.version_id == version_b.id)
        .first()
    )
    assert page_b is not None
    assert page_b.is_scanned == 1
    # Scanned without OCR triggers REQUIRES_REVIEW -> FLAGGED
    assert page_b.review_status == ReviewStatus.FLAGGED.value

    run_b = (
        db_session.query(ProcessingRun)
        .filter(ProcessingRun.version_id == version_b.id)
        .first()
    )
    assert run_b.result == ProcessingResult.PARTIAL.value


def test_phase2_review_annotation_workflow(db_session: Session):
    """Test the ReviewAnnotation model:

    Assertions:
    - DocumentPage created and associated with ReviewAnnotation
    - ReviewAnnotation persisted with reviewer, corrected_text, annotation_type, and notes
    - Original clean_text on DocumentPage is unchanged (corrections are annotations, not mutations)
    - Relationship navigation between DocumentPage and ReviewAnnotation works
    """
    source = _create_approved_source(db_session, source_id="src_ann_test")

    doc = Document(
        id="doc_ann_test",
        source_id=source.id,
        department_id=source.department_id,
        doc_type=DocType.GO.value,
        title="Document with OCR Transcription Errors",
        language="en",
        authority_level="DEPARTMENTAL_SECRETARY",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db_session.add(doc)

    original_clean_text = "The Governmnt of Uttrakhand hereby sanxions the annual grant."
    version = DocumentVersion(
        id="ver_ann_test",
        document_id=doc.id,
        source_url="https://ekosh.uk.gov.in/orders/ann_test.pdf",
        sha256="test_sha256_hash_123",
        mime_type="application/pdf",
        byte_size=2048,
        provenance_status=ProvenanceStatus.VERIFIED.value,
        original_object_key="docs/ann_test.pdf",
    )
    doc.versions.append(version)
    doc.current_version_id = version.id
    db_session.add(version)

    page = DocumentPage(
        id="page_ann_test_1",
        version_id=version.id,
        page_number=1,
        clean_text=original_clean_text,
        raw_text=original_clean_text,
        selected_text=original_clean_text,
        is_scanned=1,
        detected_language="en",
        word_count=len(original_clean_text.split()),
        review_status=ReviewStatus.FLAGGED.value,
    )
    db_session.add(page)
    db_session.commit()

    # Add a reviewer correction annotation
    corrected_text = "The Government of Uttarakhand hereby sanctions the annual grant."
    annotation = ReviewAnnotation(
        page_id=page.id,
        reviewer="qa_reviewer_sharma",
        corrected_text=corrected_text,
        annotation_type="TEXT_CORRECTION",
        notes="Corrected typographical errors in state name and sanctioning verb.",
    )
    db_session.add(annotation)
    db_session.commit()

    # -----------------------------------------------------------------------
    # Verification: Persisted fields & relations
    # -----------------------------------------------------------------------
    persisted = (
        db_session.query(ReviewAnnotation)
        .filter(ReviewAnnotation.page_id == page.id)
        .first()
    )
    assert persisted is not None
    assert persisted.id.startswith("ann_")
    assert persisted.reviewer == "qa_reviewer_sharma"
    assert persisted.corrected_text == corrected_text
    assert persisted.annotation_type == "TEXT_CORRECTION"
    assert persisted.notes == "Corrected typographical errors in state name and sanctioning verb."
    assert persisted.created_at is not None
    assert persisted.page_id == page.id

    # Relationship from page to annotations
    db_session.refresh(page)
    assert len(page.annotations) == 1
    assert page.annotations[0].id == persisted.id
    assert page.annotations[0].reviewer == "qa_reviewer_sharma"

    # -----------------------------------------------------------------------
    # Verification: original clean_text is unchanged (non-mutating)
    # -----------------------------------------------------------------------
    assert page.clean_text == original_clean_text
    assert page.raw_text == original_clean_text
    assert page.clean_text != corrected_text
