"""Tests for ITDA-curated official sample set connector."""

import json
from pathlib import Path
import fitz
import pytest
from sqlalchemy.orm import Session

from adam.connectors.itda import ITDASampleBatchConnector
from adam.db.models import Source, Document, DocumentVersion
from adam.extract.pipeline import DocumentExtractionPipeline
from adam.ingest.pipeline import IngestionPipeline
from adam.ingest.registry import SourceRegistry, SourceOnboardingSheet
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import Classification, DepartmentId, SourceStatus


@pytest.fixture
def itda_sample_dir(tmp_path: Path) -> Path:
    """Create a temporary directory simulating a curated departmental ITDA batch folder."""
    batch_path = tmp_path / "itda_curated_batch"
    batch_path.mkdir(parents=True, exist_ok=True)

    # 1. Create a sample GO PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Uttarakhand Government - Planning Department (Niyojan)", fontsize=12)
    page.insert_text((50, 80), "Order No : 55/PLAN/2023", fontsize=11)
    page.insert_text((50, 110), "Subject : Capital Asset Financial Management Guidelines.", fontsize=11)
    page.insert_text((50, 150), "Sd/- (Dr. R. Meenakshi Sundaram) Secretary", fontsize=10)

    pdf_file = batch_path / "GO_55_PLAN_2023.pdf"
    doc.save(str(pdf_file))
    doc.close()

    # 2. Sidecar metadata file
    meta = {
        "title": "Capital Asset Financial Management Guidelines",
        "go_number": "55/PLAN/2023",
        "date": "2023-08-20",
        "department_id": DepartmentId.FINANCE_TREASURY.value,
    }
    json_file = batch_path / "GO_55_PLAN_2023.json"
    json_file.write_text(json.dumps(meta), encoding="utf-8")

    return batch_path


def test_itda_batch_discovery_and_ingestion(
    db_session: Session,
    tmp_storage: LocalStorageBackend,
    itda_sample_dir: Path,
):
    registry = SourceRegistry(db_session)
    source_sheet = SourceOnboardingSheet(
        id="src_itda_pilot_batch",
        name="ITDA Curated Representative GO Batch",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="ITDA Directorate Uttarakhand",
        owner_contact="director-itda@uk.gov.in",
        written_authority_ref="ITDA-CURATED-AUTH-2024",
        permitted_domains=["local.uk.gov.in", "localhost"],
        permitted_path_prefixes=["/"],
        access_classification=Classification.PUBLIC.value,
    )
    source = registry.onboard(source_sheet)
    registry.approve(source.id, approver="itda_director")

    connector = ITDASampleBatchConnector(itda_sample_dir)
    items = list(connector.discover(source))
    assert len(items) == 1
    assert items[0].go_number == "55/PLAN/2023"
    assert "Capital Asset" in items[0].title

    # Ingest batch
    pipeline = IngestionPipeline(db_session, tmp_storage, connector)
    run_rec = pipeline.run(source.id)
    assert run_rec.count_found == 1
    assert run_rec.count_downloaded == 1

    # Extract clean text and attributes
    ext_pipeline = DocumentExtractionPipeline(db_session, tmp_storage)
    count = ext_pipeline.process_all(source_id=source.id)
    assert count == 1

    # Verify extracted records
    doc = db_session.query(Document).filter(Document.source_id == source.id).first()
    assert doc is not None
    ver = doc.versions[0]
    assert len(ver.pages) == 1
    assert "Capital Asset" in ver.pages[0].clean_text
    assert ver.attributes.order_number == "55/PLAN/2023"
    assert ver.attributes.issuing_authority_title == "Secretary"
