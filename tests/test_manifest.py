"""Tests for signed inventory generation, verification, and tamper detection."""

import hashlib
from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from adam.db.models import Document, DocumentVersion, Source
from adam.ingest.manifest import SignedInventory
from adam.ingest.registry import SourceRegistry, SourceOnboardingSheet


def test_signed_inventory_acceptance_criteria(
    db_session: Session, sample_source_sheet: SourceOnboardingSheet
):
    """Acceptance criteria 1: A pilot source produces a signed inventory with

    100% original URLs, hashes and fetch timestamps.
    """
    registry = SourceRegistry(db_session)
    source = registry.onboard(sample_source_sheet)

    # Add multiple test documents and versions
    doc = Document(
        id="doc_pilot_1",
        source_id=source.id,
        department_id=source.department_id,
        title="Pilot Treasury Order 1",
    )
    db_session.add(doc)

    data1 = b"%PDF-1.4 pilot file 1"
    hash1 = hashlib.sha256(data1).hexdigest()
    ts1 = datetime.now(timezone.utc)

    ver1 = DocumentVersion(
        id="ver_pilot_1",
        document_id=doc.id,
        source_url="https://ekosh.uk.gov.in/government-orders/pilot-1.pdf",
        sha256=hash1,
        mime_type="application/pdf",
        byte_size=len(data1),
        retrieved_at=ts1,
        original_object_key="pilot/key1",
        provenance_status="VERIFIED",
    )
    db_session.add(ver1)
    db_session.commit()

    secret = "test-authority-secret-key-uk"
    manifest = SignedInventory.generate_for_source(db_session, source.id, secret_key=secret)

    # Verify manifest structure and acceptance criteria
    assert manifest["source_id"] == source.id
    assert manifest["total_records"] == 1
    assert "signature" in manifest
    assert manifest["signature_algorithm"] == "HMAC-SHA256"

    records = manifest["records"]
    assert len(records) == 1

    rec = records[0]
    # Acceptance Criteria 1: 100% original URLs, hashes and fetch timestamps
    assert rec["source_url"] == "https://ekosh.uk.gov.in/government-orders/pilot-1.pdf"
    assert rec["sha256"] == hash1
    assert rec["retrieved_at"] == ts1.isoformat()

    # Verify signature passes
    valid, err = SignedInventory.verify_manifest(manifest, secret_key=secret)
    assert valid is True
    assert err is None


def test_signed_inventory_tamper_detection(
    db_session: Session, sample_source_sheet: SourceOnboardingSheet
):
    registry = SourceRegistry(db_session)
    source = registry.onboard(sample_source_sheet)

    doc = Document(id="doc_p2", source_id=source.id, title="P2")
    ver = DocumentVersion(
        id="ver_p2",
        document_id=doc.id,
        source_url="https://ekosh.uk.gov.in/government-orders/doc.pdf",
        sha256=hashlib.sha256(b"abc").hexdigest(),
        mime_type="application/pdf",
        byte_size=3,
        retrieved_at=datetime.now(timezone.utc),
        original_object_key="k",
    )
    db_session.add(doc)
    db_session.add(ver)
    db_session.commit()

    secret = "secret-1"
    manifest = SignedInventory.generate_for_source(db_session, source.id, secret_key=secret)

    # 1. Invalid signing key fails
    valid, err = SignedInventory.verify_manifest(manifest, secret_key="wrong-secret")
    assert valid is False
    assert "tampered" in err.lower() or "failed" in err.lower()

    # 2. Tampered hash in records fails
    tampered_manifest = dict(manifest)
    tampered_records = [dict(r) for r in manifest["records"]]
    tampered_records[0]["sha256"] = "deadbeef" * 8
    tampered_manifest["records"] = tampered_records

    valid2, err2 = SignedInventory.verify_manifest(tampered_manifest, secret_key=secret)
    assert valid2 is False

    # 3. Missing URL in record fails
    incomplete_manifest = dict(manifest)
    incomplete_records = [dict(r) for r in manifest["records"]]
    incomplete_records[0]["source_url"] = ""
    incomplete_manifest["records"] = incomplete_records

    valid3, err3 = SignedInventory.verify_manifest(incomplete_manifest, secret_key=secret)
    assert valid3 is False
    assert "missing" in err3.lower()
