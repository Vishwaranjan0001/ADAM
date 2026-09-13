"""Cryptographically signed inventory generation and verification."""

import hmac
import json
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session

from adam.config import SIGNING_SECRET
from adam.db.models import Source, Document, DocumentVersion


class SignedInventory:
    """Generates and verifies cryptographically signed inventories of acquired records."""

    MANIFEST_VERSION = "1.0"
    ALGORITHM = "HMAC-SHA256"

    @classmethod
    def generate_for_source(
        cls,
        session: Session,
        source_id: str,
        secret_key: Optional[str] = None,
        key_id: str = "adam-uk-gov-authority-key",
    ) -> Dict[str, Any]:
        """Generate a signed inventory manifest for all records acquired from a source.

        Fulfills Acceptance Criteria 1: 100% original URLs, hashes and fetch timestamps.
        """
        source = session.query(Source).filter(Source.id == source_id).first()
        if not source:
            raise ValueError(f"Source '{source_id}' not found.")

        # Query all versions for documents under this source
        versions = (
            session.query(DocumentVersion, Document)
            .join(Document, DocumentVersion.document_id == Document.id)
            .filter(Document.source_id == source_id)
            .order_by(DocumentVersion.source_url.asc(), DocumentVersion.retrieved_at.asc())
            .all()
        )

        records: List[Dict[str, Any]] = []
        for ver, doc in versions:
            records.append({
                "document_id": doc.id,
                "version_id": ver.id,
                "title": doc.title,
                "doc_type": doc.doc_type,
                "department_id": doc.department_id,
                "source_url": ver.source_url,
                "source_locator": ver.source_locator,
                "sha256": ver.sha256,
                "byte_size": ver.byte_size,
                "mime_type": ver.mime_type,
                "retrieved_at": ver.retrieved_at.isoformat() if ver.retrieved_at else None,
                "go_number": ver.go_number,
                "gazette_number": ver.gazette_number,
                "provenance_status": ver.provenance_status,
                "original_object_key": ver.original_object_key,
            })

        # Canonical sort by source_url, then retrieved_at, then version_id
        records.sort(key=lambda r: (r["source_url"], r["retrieved_at"] or "", r["version_id"]))

        payload = {
            "manifest_version": cls.MANIFEST_VERSION,
            "source_id": source.id,
            "source_name": source.name,
            "department_id": source.department_id,
            "written_authority_ref": source.written_authority_ref,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_records": len(records),
            "records": records,
        }

        canonical_bytes = cls._canonical_bytes(payload)
        key = (secret_key or SIGNING_SECRET).encode("utf-8")
        signature = hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()

        return {
            **payload,
            "signature_algorithm": cls.ALGORITHM,
            "signing_key_id": key_id,
            "signature": signature,
        }

    @classmethod
    def verify_manifest(
        cls,
        manifest: Dict[str, Any],
        secret_key: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic signature and completeness of an inventory manifest."""
        manifest_copy = dict(manifest)
        signature = manifest_copy.pop("signature", None)
        algorithm = manifest_copy.pop("signature_algorithm", None)
        manifest_copy.pop("signing_key_id", None)

        if not signature:
            return False, "Manifest is missing cryptographic signature."
        if algorithm != cls.ALGORITHM:
            return False, f"Unsupported signature algorithm: {algorithm}"

        # Verify record count matches length of records
        records = manifest_copy.get("records", [])
        if len(records) != manifest_copy.get("total_records"):
            return False, "Record count mismatch in manifest."

        # Verify that 100% of records contain source_url, sha256, and retrieved_at
        for i, rec in enumerate(records):
            if not rec.get("source_url"):
                return False, f"Record {i} missing original source_url."
            if not rec.get("sha256"):
                return False, f"Record {i} missing SHA-256 hash."
            if not rec.get("retrieved_at"):
                return False, f"Record {i} missing retrieval timestamp."

        canonical_bytes = cls._canonical_bytes(manifest_copy)
        key = (secret_key or SIGNING_SECRET).encode("utf-8")
        expected_sig = hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return False, "Cryptographic signature verification failed (tampered content or invalid key)."

        return True, None

    @staticmethod
    def _canonical_bytes(payload: Dict[str, Any]) -> bytes:
        """Produce deterministic canonical JSON bytes."""
        return json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
