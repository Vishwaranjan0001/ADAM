"""Tests for ingestion pipeline: idempotency, versioning, delta discovery, and quarantine."""

import hashlib
from datetime import datetime, timezone, date
from typing import Iterator, Dict
import pytest
from sqlalchemy.orm import Session

from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.db.models import Document, DocumentVersion, Source, IngestionRun, AuditEvent
from adam.ingest.pipeline import IngestionPipeline
from adam.ingest.registry import SourceRegistry, SourceOnboardingSheet, InvalidSourceStateError
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import SourceStatus, LifecycleStatus, ProvenanceStatus, DocType, DepartmentId


class MockPortalConnector(BaseConnector):
    """Configurable mock connector for simulating crawl runs and content changes."""

    def __init__(self, initial_items: Dict[str, bytes]):
        # url -> bytes
        self.items_data = dict(initial_items)
        self.disappeared_urls = set()

    def discover(self, source: Source) -> Iterator[DiscoveredItem]:
        for url in list(self.items_data.keys()):
            if url in self.disappeared_urls:
                continue
            yield DiscoveredItem(
                source_url=url,
                title=f"Order for {url.split('/')[-1]}",
                doc_type=DocType.GO.value,
                department_id=source.department_id,
                displayed_date=date(2024, 1, 15),
                go_number="UK/GO/2024/001",
                authority_level="DEPARTMENTAL_SECRETARY",
            )

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        data = self.items_data[item.source_url]
        return FetchResult(
            source_url=item.source_url,
            data=data,
            http_status=200,
            http_headers={"content-type": "application/pdf"},
            retrieved_at=datetime.now(timezone.utc),
        )


def test_pipeline_idempotency_and_versioning(
    db_session: Session,
    tmp_storage: LocalStorageBackend,
    sample_source_sheet: SourceOnboardingSheet,
):
    """Test full ingestion workflow including Acceptance Criteria 2:

    Re-running a connector is idempotent and does not duplicate byte-identical files.
    """
    registry = SourceRegistry(db_session)
    source = registry.onboard(sample_source_sheet)

    url1 = "https://ekosh.uk.gov.in/government-orders/order-1.pdf"
    content_v1 = b"%PDF-1.4 original content of order 1"
    connector = MockPortalConnector({url1: content_v1})

    pipeline = IngestionPipeline(db_session, tmp_storage, connector)

    # 1. Verification: pipeline cannot run if source is still PENDING_APPROVAL
    with pytest.raises(InvalidSourceStateError):
        pipeline.run(source.id)

    # Approve source
    registry.approve(source.id, approver="it_secretary")

    # 2. Run initial ingestion
    run1 = pipeline.run(source.id)
    assert run1.count_found == 1
    assert run1.count_downloaded == 1

    # Verify database state
    doc = db_session.query(Document).filter(Document.source_id == source.id).first()
    assert doc is not None
    assert doc.lifecycle_status == LifecycleStatus.ACTIVE.value
    assert len(doc.versions) == 1

    ver1 = doc.versions[0]
    assert ver1.source_url == url1
    assert ver1.sha256 == hashlib.sha256(content_v1).hexdigest()
    assert ver1.provenance_status == ProvenanceStatus.VERIFIED.value

    # 3. Acceptance Criteria 2: Re-running connector is idempotent
    run2 = pipeline.run(source.id)
    assert run2.count_found == 1
    assert run2.count_downloaded == 0  # 0 duplicates downloaded or created!

    # Check that versions count has NOT increased
    db_session.refresh(doc)
    assert len(doc.versions) == 1

    # 4. Content update at same URL produces a new version without overwriting prior
    content_v2 = b"%PDF-1.4 revised amended content of order 1"
    connector.items_data[url1] = content_v2

    run3 = pipeline.run(source.id)
    assert run3.count_found == 1
    assert run3.count_downloaded == 1

    db_session.refresh(doc)
    assert len(doc.versions) == 2

    # Verify prior version is preserved and superseded
    prior_ver = [v for v in doc.versions if v.id != doc.current_version_id][0]
    current_ver = [v for v in doc.versions if v.id == doc.current_version_id][0]

    assert prior_ver.sha256 == hashlib.sha256(content_v1).hexdigest()
    assert current_ver.sha256 == hashlib.sha256(content_v2).hexdigest()
    assert current_ver.supersedes_version_id == prior_ver.id

    # Verify both versions exist simultaneously and immutably in object storage
    assert tmp_storage.get(prior_ver.original_object_key) == content_v1
    assert tmp_storage.get(current_ver.original_object_key) == content_v2


def test_delta_discovery_quarantine_removals(
    db_session: Session,
    tmp_storage: LocalStorageBackend,
    sample_source_sheet: SourceOnboardingSheet,
):
    """Test Step 6: Delta discovery quarantines disappeared URLs and notifies owner

    without deleting evidence.
    """
    registry = SourceRegistry(db_session)
    source = registry.onboard(sample_source_sheet)
    registry.approve(source.id, approver="it_secretary")

    url1 = "https://ekosh.uk.gov.in/government-orders/order-alpha.pdf"
    url2 = "https://ekosh.uk.gov.in/government-orders/order-beta.pdf"
    connector = MockPortalConnector({
        url1: b"%PDF-1.4 Order Alpha",
        url2: b"%PDF-1.4 Order Beta",
    })

    pipeline = IngestionPipeline(db_session, tmp_storage, connector)
    pipeline.run(source.id)

    doc_alpha = db_session.query(Document).filter(Document.title.contains("order-alpha.pdf")).first()
    assert doc_alpha.lifecycle_status == LifecycleStatus.ACTIVE.value

    # Simulate removal on portal: order-alpha disappears from the index
    connector.disappeared_urls.add(url1)

    # Next delta discovery run
    pipeline.run(source.id)

    db_session.refresh(doc_alpha)
    # Alpha must be quarantined, NOT deleted from database
    assert doc_alpha.lifecycle_status == LifecycleStatus.QUARANTINED.value

    # Check that audit event for quarantine with owner notification was generated
    quarantine_audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_id == doc_alpha.id, AuditEvent.action == "QUARANTINE_REMOVAL")
        .first()
    )
    assert quarantine_audit is not None
    assert "owner_notification" in quarantine_audit.details_json
    assert quarantine_audit.details_json["owner_notification"]["owner_contact"] == source.owner_contact
