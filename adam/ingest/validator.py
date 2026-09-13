"""Content validation, malware/type checking, and searchability provenance gating."""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from sqlalchemy.orm import Query

from adam.config import MAX_FILE_SIZE_BYTES
from adam.db.models import Document, DocumentVersion
from adam.vocabularies import ProvenanceStatus, LifecycleStatus


@dataclass
class ValidationResult:
    """Result of content safety and MIME type verification."""
    is_safe: bool
    detected_mime_type: str
    declared_mime_type: str
    byte_size: int
    issues: List[str] = field(default_factory=list)
    suggested_provenance: str = ProvenanceStatus.PENDING_VERIFICATION.value


class ContentValidator:
    """Performs magic byte detection, MIME type verification, and basic security checks."""

    # Common executable magic bytes that must be strictly rejected
    EXECUTABLE_SIGNATURES = [
        (b"MZ", "DOS/Windows Executable (PE)"),
        (b"\x7fELF", "Linux ELF Executable"),
        (b"\xca\xfe\xba\xbe", "Java Class / Mach-O Fat Binary"),
        (b"\xfe\xed\xfa\xce", "Mach-O Binary (32-bit)"),
        (b"\xfe\xed\xfa\xcf", "Mach-O Binary (64-bit)"),
        (b"\xcf\xfa\xed\xfe", "Mach-O Binary (reversed)"),
    ]

    # Malicious or high-risk PDF keywords that require quarantine
    HIGH_RISK_PDF_PATTERNS = [
        re.compile(rb"/Launch\b"),
        re.compile(rb"/EmbeddedFiles\b"),
        re.compile(rb"/JavaScript\b"),
        re.compile(rb"/JS\b"),
        re.compile(rb"/OpenAction\b"),
    ]

    @classmethod
    def detect_mime_type(cls, data: bytes) -> str:
        """Inspect magic bytes to determine actual file format."""
        if not data:
            return "application/x-empty"

        if data.startswith(b"%PDF-"):
            return "application/pdf"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        elif data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        elif data.startswith(b"PK\x03\x04"):
            return "application/zip"
        elif data.strip().startswith(b"<!DOCTYPE") or data.strip().startswith(b"<html") or data.strip().startswith(b"<HTML"):
            return "text/html"
        elif data.strip().startswith(b"<?xml"):
            return "application/xml"
        elif data.strip().startswith(b"{") or data.strip().startswith(b"["):
            return "application/json"

        # Check if plain text
        try:
            data[:1024].decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            return "application/octet-stream"

    @classmethod
    def validate(cls, data: bytes, declared_mime_type: Optional[str] = None) -> ValidationResult:
        """Validate content safety, size limits, and format consistency."""
        issues: List[str] = []
        byte_size = len(data)

        if byte_size == 0:
            issues.append("Zero-byte file content.")
            return ValidationResult(
                is_safe=False,
                detected_mime_type="application/x-empty",
                declared_mime_type=declared_mime_type or "unknown",
                byte_size=0,
                issues=issues,
                suggested_provenance=ProvenanceStatus.FAILED_VALIDATION.value,
            )

        if byte_size > MAX_FILE_SIZE_BYTES:
            issues.append(
                f"File size {byte_size} bytes exceeds maximum permitted limit {MAX_FILE_SIZE_BYTES} bytes."
            )

        # Check for executable signatures
        for sig, desc in cls.EXECUTABLE_SIGNATURES:
            if data.startswith(sig):
                issues.append(f"Executable binary content detected ({desc}). Ingestion forbidden.")

        detected_mime = cls.detect_mime_type(data)
        dec_mime = (declared_mime_type or detected_mime).lower().split(";")[0].strip()

        # Check PDF safety
        if detected_mime == "application/pdf":
            # Check for high risk patterns in PDF stream
            header_sample = data[:4096]
            for pattern in cls.HIGH_RISK_PDF_PATTERNS:
                if pattern.search(data):
                    issues.append(f"Suspicious executable pattern found in PDF: {pattern.pattern!r}")

        # Check for mismatch between declared PDF and actual non-PDF content
        if "pdf" in dec_mime and detected_mime != "application/pdf":
            issues.append(
                f"Declared MIME type is '{declared_mime_type}', but actual content is '{detected_mime}'."
            )

        is_safe = len(issues) == 0
        provenance = (
            ProvenanceStatus.VERIFIED.value if is_safe else ProvenanceStatus.FAILED_VALIDATION.value
        )

        return ValidationResult(
            is_safe=is_safe,
            detected_mime_type=detected_mime,
            declared_mime_type=dec_mime,
            byte_size=byte_size,
            issues=issues,
            suggested_provenance=provenance,
        )


class ProvenanceGate:
    """Controls searchability and public availability based on provenance and security validation."""

    @staticmethod
    def is_searchable(doc: Document, version: Optional[DocumentVersion] = None) -> bool:
        """Acceptance Criteria 4:
        No document becomes searchable before malware/type validation and provenance status
        is 'verified' or visibly 'unverified'.
        """
        # Document lifecycle check
        if doc.lifecycle_status in (
            LifecycleStatus.QUARANTINED.value,
            LifecycleStatus.REPEALED.value,
            LifecycleStatus.ARCHIVED.value,
            LifecycleStatus.DRAFT.value,
        ):
            return False

        target_ver = version
        if not target_ver:
            # Look at current version if loaded
            if hasattr(doc, "versions") and doc.versions:
                for v in doc.versions:
                    if v.id == doc.current_version_id:
                        target_ver = v
                        break
                if not target_ver:
                    target_ver = doc.versions[-1]

        if not target_ver:
            return False

        # Provenance status must be explicitly VERIFIED or UNVERIFIED
        allowed_statuses = {
            ProvenanceStatus.VERIFIED.value,
            ProvenanceStatus.UNVERIFIED.value,
        }

        if target_ver.provenance_status not in allowed_statuses:
            return False

        return True

    @staticmethod
    def filter_searchable_versions(query: Query) -> Query:
        """Apply SQLAlchemy filter to include only documents/versions meeting searchability gate."""
        return (
            query.join(Document, DocumentVersion.document_id == Document.id)
            .filter(
                Document.lifecycle_status == LifecycleStatus.ACTIVE.value,
                DocumentVersion.provenance_status.in_([
                    ProvenanceStatus.VERIFIED.value,
                    ProvenanceStatus.UNVERIFIED.value,
                ]),
            )
        )
