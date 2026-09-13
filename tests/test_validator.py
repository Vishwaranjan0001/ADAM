"""Tests for content validation, malware detection, and searchability gating."""

from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from adam.db.models import Document, DocumentVersion
from adam.ingest.validator import ContentValidator, ProvenanceGate
from adam.vocabularies import LifecycleStatus, ProvenanceStatus


def test_magic_bytes_and_format_detection():
    pdf_data = b"%PDF-1.4 sample pdf stream"
    res_pdf = ContentValidator.validate(pdf_data, declared_mime_type="application/pdf")
    assert res_pdf.is_safe is True
    assert res_pdf.detected_mime_type == "application/pdf"
    assert res_pdf.suggested_provenance == ProvenanceStatus.VERIFIED.value

    html_data = b"<!DOCTYPE html><html><body>Portal content</body></html>"
    res_html = ContentValidator.validate(html_data, declared_mime_type="text/html")
    assert res_html.is_safe is True
    assert res_html.detected_mime_type == "text/html"


def test_malware_and_executable_rejection():
    # PE Executable disguised as PDF
    malicious_pe = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100
    res_pe = ContentValidator.validate(malicious_pe, declared_mime_type="application/pdf")
    assert res_pe.is_safe is False
    assert any("Executable binary content detected" in issue for issue in res_pe.issues)
    assert res_pe.suggested_provenance == ProvenanceStatus.FAILED_VALIDATION.value

    # Linux ELF executable
    malicious_elf = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 100
    res_elf = ContentValidator.validate(malicious_elf, declared_mime_type="application/pdf")
    assert res_elf.is_safe is False
    assert res_elf.suggested_provenance == ProvenanceStatus.FAILED_VALIDATION.value


def test_suspicious_pdf_embedded_actions_flagged():
    risky_pdf = b"%PDF-1.4\n<< /Type /Action /S /Launch /F (cmd.exe) >>\n%%EOF"
    res_risky = ContentValidator.validate(risky_pdf, declared_mime_type="application/pdf")
    assert res_risky.is_safe is False
    assert any("Suspicious executable pattern" in issue for issue in res_risky.issues)


def test_searchability_provenance_gate(db_session: Session):
    """Acceptance criteria 4: No document becomes searchable before malware/type validation

    and provenance status is 'verified' or visibly 'unverified'.
    """
    doc = Document(
        id="doc_test_1",
        title="Sample Treasury Order",
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    ver = DocumentVersion(
        id="ver_test_1",
        document_id=doc.id,
        source_url="https://ekosh.uk.gov.in/orders/1.pdf",
        sha256="abc",
        mime_type="application/pdf",
        byte_size=100,
        original_object_key="key1",
        provenance_status=ProvenanceStatus.PENDING_VERIFICATION.value,
    )
    doc.versions.append(ver)
    doc.current_version_id = ver.id

    # 1. PENDING_VERIFICATION must NOT be searchable
    assert ProvenanceGate.is_searchable(doc, ver) is False

    # 2. FAILED_VALIDATION must NOT be searchable
    ver.provenance_status = ProvenanceStatus.FAILED_VALIDATION.value
    assert ProvenanceGate.is_searchable(doc, ver) is False

    # 3. VERIFIED is searchable
    ver.provenance_status = ProvenanceStatus.VERIFIED.value
    assert ProvenanceGate.is_searchable(doc, ver) is True

    # 4. UNVERIFIED is visibly searchable (with unverified banner per spec)
    ver.provenance_status = ProvenanceStatus.UNVERIFIED.value
    assert ProvenanceGate.is_searchable(doc, ver) is True

    # 5. QUARANTINED version or document must NOT be searchable even if previously verified
    ver.provenance_status = ProvenanceStatus.VERIFIED.value
    doc.lifecycle_status = LifecycleStatus.QUARANTINED.value
    assert ProvenanceGate.is_searchable(doc, ver) is False

    doc.lifecycle_status = LifecycleStatus.REPEALED.value
    assert ProvenanceGate.is_searchable(doc, ver) is False
