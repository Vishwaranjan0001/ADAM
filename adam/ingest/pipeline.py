"""Ingestion pipeline executing authorized crawls, versioning, and delta governance."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set

from sqlalchemy.orm import Session

from adam.config import COLLECTOR_VERSION
from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.db.models import Source, Document, DocumentVersion, IngestionRun, AuditEvent
from adam.ingest.crawler import UrlCrawlerGuard, DisallowedUrlError
from adam.ingest.registry import InvalidSourceStateError, SourceNotFoundError
from adam.ingest.validator import ContentValidator
from adam.storage.base import StorageBackend
from adam.vocabularies import (
    SourceStatus,
    LifecycleStatus,
    ProvenanceStatus,
    AuthorityLevel,
    DocType,
    DepartmentId,
)


class IngestionPipeline:
    """Orchestrates authorized ingestion runs, enforcing immutability and provenance."""

    def __init__(
        self,
        session: Session,
        storage: StorageBackend,
        connector: BaseConnector,
    ):
        self.session = session
        self.storage = storage
        self.connector = connector

    def run(self, source_id: str, actor: str = "collector", max_items: Optional[int] = None) -> IngestionRun:
        """Execute an authorized ingestion run for an authorized source."""
        source = self.session.query(Source).filter(Source.id == source_id).first()
        if not source:
            raise SourceNotFoundError(f"Source '{source_id}' not found.")

        # Governance gate: must be APPROVED
        if source.status != SourceStatus.APPROVED.value:
            raise InvalidSourceStateError(
                f"Source '{source_id}' cannot be crawled. Current status: '{source.status}'. "
                f"Only sources with status '{SourceStatus.APPROVED.value}' can be executed."
            )

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        run_record = IngestionRun(
            id=run_id,
            source_id=source.id,
            started_at=datetime.now(timezone.utc),
            collector_version=COLLECTOR_VERSION,
            count_found=0,
            count_downloaded=0,
            failures_json=[],
        )
        self.session.add(run_record)
        self.session.flush()

        guard = UrlCrawlerGuard(
            permitted_domains=source.permitted_domains,
            permitted_path_prefixes=source.permitted_path_prefixes,
        )

        current_run_urls: Set[str] = set()
        failures: List[Dict[str, Any]] = []
        count_found = 0
        count_downloaded = 0

        # Step 2: Discover index/list pages and enqueue items
        try:
            discovered_items = list(self.connector.discover(source))
        except Exception as e:
            failures.append({
                "stage": "discovery",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            discovered_items = []

        for item in discovered_items:
            if max_items is not None and count_downloaded >= max_items:
                break
            count_found += 1
            canonical_url = guard.normalize_url(item.source_url)
            current_run_urls.add(canonical_url)

            # Validate URL against allow-list
            try:
                guard.validate_or_raise(canonical_url)
            except DisallowedUrlError as due:

                failures.append({
                    "stage": "url_guard",
                    "url": item.source_url,
                    "error": str(due),
                })
                continue

            # Fetch original bytes
            try:
                fetch_res = self.connector.fetch(item)
            except Exception as e:
                failures.append({
                    "stage": "fetch",
                    "url": canonical_url,
                    "error": str(e),
                })
                continue

            if fetch_res.http_status != 200:
                failures.append({
                    "stage": "http_status",
                    "url": canonical_url,
                    "status_code": fetch_res.http_status,
                })
                continue

            data = fetch_res.data
            sha256_hash = hashlib.sha256(data).hexdigest()

            # Step 5: Content and malware/type checks
            val_res = ContentValidator.validate(
                data,
                declared_mime_type=fetch_res.http_headers.get("content-type"),
            )

            # Step 3 & 4: Idempotency and Byte Hash Detection
            # Look up if a document version with exact same source_url AND sha256 already exists
            existing_identical_version = (
                self.session.query(DocumentVersion)
                .join(Document, DocumentVersion.document_id == Document.id)
                .filter(
                    Document.source_id == source.id,
                    DocumentVersion.source_url == canonical_url,
                    DocumentVersion.sha256 == sha256_hash,
                )
                .first()
            )

            if existing_identical_version:
                # Byte-identical version already recorded; idempotent skip
                continue

            # Store immutable original bytes to object storage
            storage_key = f"{source.id}/{sha256_hash[:2]}/{sha256_hash}.bin"
            self.storage.store(storage_key, data, expected_sha256=sha256_hash)

            # Check if there is an existing Document for this source_url with a previous sha256
            existing_doc_version = (
                self.session.query(DocumentVersion)
                .join(Document, DocumentVersion.document_id == Document.id)
                .filter(
                    Document.source_id == source.id,
                    DocumentVersion.source_url == canonical_url,
                )
                .order_by(DocumentVersion.retrieved_at.desc())
                .first()
            )

            if existing_doc_version:
                # Existing document found with prior hash -> create new version without overwriting prior
                doc = existing_doc_version.document
                new_ver_id = f"ver_{uuid.uuid4().hex[:12]}"
                new_version = DocumentVersion(
                    id=new_ver_id,
                    document_id=doc.id,
                    source_url=canonical_url,
                    source_locator=item.detail_page_url,
                    issued_on=item.displayed_date,
                    go_number=item.go_number,
                    gazette_number=item.gazette_number,
                    supersedes_version_id=existing_doc_version.id,
                    sha256=sha256_hash,
                    mime_type=val_res.detected_mime_type,
                    byte_size=val_res.byte_size,
                    retrieved_at=fetch_res.retrieved_at,
                    provenance_status=val_res.suggested_provenance,
                    original_object_key=storage_key,
                    http_headers=fetch_res.http_headers,
                    metadata_json={
                        **item.metadata,
                        "validation_issues": val_res.issues,
                    },
                )
                self.session.add(new_version)
                doc.current_version_id = new_ver_id
                doc.updated_at = datetime.now(timezone.utc)
                count_downloaded += 1

                audit = AuditEvent(
                    entity_type="DOCUMENT",
                    entity_id=doc.id,
                    action="NEW_VERSION",
                    actor=actor,
                    details_json={
                        "version_id": new_ver_id,
                        "superseded_version_id": existing_doc_version.id,
                        "sha256": sha256_hash,
                        "url": canonical_url,
                    },
                )
                self.session.add(audit)

            else:
                # Brand new document
                doc_id = f"doc_{uuid.uuid4().hex[:12]}"
                ver_id = f"ver_{uuid.uuid4().hex[:12]}"

                doc = Document(
                    id=doc_id,
                    source_id=source.id,
                    department_id=DepartmentId.validate_or_preserve(item.department_id or source.department_id),
                    doc_type=DocType.validate_or_preserve(item.doc_type),
                    title=item.title.strip() or "Untitled Official Document",
                    language=item.language or "hi",
                    authority_level=AuthorityLevel.validate_or_preserve(item.authority_level),
                    classification=source.access_classification,
                    current_version_id=ver_id,
                    lifecycle_status=LifecycleStatus.ACTIVE.value,
                )
                self.session.add(doc)

                version = DocumentVersion(
                    id=ver_id,
                    document_id=doc_id,
                    source_url=canonical_url,
                    source_locator=item.detail_page_url,
                    issued_on=item.displayed_date,
                    go_number=item.go_number,
                    gazette_number=item.gazette_number,
                    sha256=sha256_hash,
                    mime_type=val_res.detected_mime_type,
                    byte_size=val_res.byte_size,
                    retrieved_at=fetch_res.retrieved_at,
                    provenance_status=val_res.suggested_provenance,
                    original_object_key=storage_key,
                    http_headers=fetch_res.http_headers,
                    metadata_json={
                        **item.metadata,
                        "validation_issues": val_res.issues,
                    },
                )
                self.session.add(version)
                count_downloaded += 1

                audit = AuditEvent(
                    entity_type="DOCUMENT",
                    entity_id=doc_id,
                    action="INGEST_NEW",
                    actor=actor,
                    details_json={
                        "version_id": ver_id,
                        "sha256": sha256_hash,
                        "url": canonical_url,
                    },
                )
                self.session.add(audit)

        # Step 6: Delta Discovery & Quarantine Removals
        # If any previously active document from this source was missing from this crawl run,
        # quarantine it and notify the owner rather than deleting evidence.
        if current_run_urls and max_items is None:
            active_docs = (
                self.session.query(Document)
                .filter(
                    Document.source_id == source.id,
                    Document.lifecycle_status == LifecycleStatus.ACTIVE.value,
                )
                .all()
            )

            for active_doc in active_docs:
                doc_urls = {v.source_url for v in active_doc.versions}
                # If none of this document's URLs were found in current discovery run:
                if not doc_urls.intersection(current_run_urls):
                    active_doc.lifecycle_status = LifecycleStatus.QUARANTINED.value
                    active_doc.updated_at = datetime.now(timezone.utc)

                    audit = AuditEvent(
                        entity_type="DOCUMENT",
                        entity_id=active_doc.id,
                        action="QUARANTINE_REMOVAL",
                        actor=actor,
                        details_json={
                            "reason": "URL no longer present on source portal index during delta crawl.",
                            "missing_urls": list(doc_urls),
                            "owner_notification": {
                                "owner_name": source.owner_name,
                                "owner_contact": source.owner_contact,
                                "department_id": source.department_id,
                                "message": (
                                    f"Document '{active_doc.title}' ({active_doc.id}) disappeared from "
                                    f"source '{source.name}'. Retained as quarantined evidence."
                                ),
                            },
                        },
                    )
                    self.session.add(audit)

        # Finalize ingestion run record
        run_record.completed_at = datetime.now(timezone.utc)
        run_record.count_found = count_found
        run_record.count_downloaded = count_downloaded
        run_record.failures_json = failures

        run_audit = AuditEvent(
            entity_type="INGESTION_RUN",
            entity_id=run_id,
            action="RUN_COMPLETE",
            actor=actor,
            details_json={
                "count_found": count_found,
                "count_downloaded": count_downloaded,
                "failure_count": len(failures),
            },
        )
        self.session.add(run_audit)

        self.session.commit()
        return run_record
