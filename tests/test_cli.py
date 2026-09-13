"""End-to-end tests for the ADAM CLI commands."""

import json
from pathlib import Path
from click.testing import CliRunner
import pytest

from adam.cli import cli


@pytest.fixture
def cli_runner(tmp_path: Path, monkeypatch):
    """Fixture providing CliRunner isolated in a temporary database and storage directory."""
    db_file = tmp_path / "test_adam.db"
    storage_dir = tmp_path / "test_storage"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir))
    return CliRunner()


def test_cli_source_lifecycle_and_seeding(cli_runner: CliRunner):
    # 1. Seed standard sources
    res_seed = cli_runner.invoke(cli, ["source", "seed"])
    assert res_seed.exit_code == 0
    assert "Seeded" in res_seed.output

    # 2. List sources
    res_list = cli_runner.invoke(cli, ["source", "list"])
    assert res_list.exit_code == 0
    assert "src_ekosh_treasury_go" in res_list.output

    # 3. Approve a source
    res_app = cli_runner.invoke(
        cli,
        ["source", "approve", "src_ekosh_treasury_go", "--approver", "records_director"],
    )
    assert res_app.exit_code == 0
    assert "Source approved: src_ekosh_treasury_go" in res_app.output

    # 4. Check audit trail
    res_aud = cli_runner.invoke(cli, ["source", "audit", "src_ekosh_treasury_go"])
    assert res_aud.exit_code == 0
    assert "APPROVE" in res_aud.output
    assert "records_director" in res_aud.output

    # 5. Pause source
    res_pause = cli_runner.invoke(
        cli,
        ["source", "pause", "src_ekosh_treasury_go", "--actor", "admin", "--reason", "Test pause"],
    )
    assert res_pause.exit_code == 0
    assert "Source paused" in res_pause.output

    # 6. Remove source
    res_rem = cli_runner.invoke(
        cli,
        ["source", "remove", "src_ekosh_treasury_go", "--actor", "admin", "--reason", "Test removal"],
    )
    assert res_rem.exit_code == 0
    assert "Source soft-removed" in res_rem.output
    assert "Audit history preserved" in res_rem.output


def test_cli_inventory_export_and_verify(cli_runner: CliRunner, tmp_path: Path):
    # Onboard and approve
    cli_runner.invoke(
        cli,
        [
            "source",
            "onboard",
            "--id",
            "src_inv_test",
            "--name",
            "Inventory Test Portal",
            "--dept",
            "FINANCE_TREASURY",
            "--owner",
            "Owner",
            "--contact",
            "owner@uk.gov.in",
            "--authority-ref",
            "AUTH-INV-1",
            "--domains",
            "ekosh.uk.gov.in",
            "--paths",
            "/government-orders/",
        ],
    )

    manifest_file = tmp_path / "manifest.json"
    res_export = cli_runner.invoke(
        cli,
        ["inventory", "export", "src_inv_test", "--output", str(manifest_file)],
    )
    assert res_export.exit_code == 0
    assert manifest_file.exists()

    # Verify manifest
    res_ver = cli_runner.invoke(cli, ["inventory", "verify", str(manifest_file)])
    assert res_ver.exit_code == 0
    assert "SUCCESS: Inventory manifest is authentic" in res_ver.output


def test_cli_extract_quality_report_and_processing_runs(cli_runner: CliRunner):
    from adam.db.session import get_session
    from adam.db.models import Document, DocumentVersion, DocumentPage, ProcessingRun, Source
    from adam.vocabularies import ReviewStatus

    session = get_session()
    source = Source(
        id="src_test_extract",
        department_id="FINANCE_TREASURY",
        name="Test Portal",
        permitted_domains=["test.uk.gov.in"],
        permitted_path_prefixes=["/"],
        written_authority_ref="AUTH-1",
        owner_name="Test Owner",
        owner_contact="test@uk.gov.in",
        status="APPROVED",
    )
    doc = Document(id="doc_test_1", source_id="src_test_extract", title="Test GO")
    ver = DocumentVersion(
        id="ver_test_1",
        document_id="doc_test_1",
        source_url="https://test.uk.gov.in/go.pdf",
        mime_type="application/pdf",
        original_object_key="raw/ver_test_1.pdf",
        sha256="a" * 64,
        byte_size=1024,
    )
    p1 = DocumentPage(
        id="page_1",
        version_id="ver_test_1",
        page_number=1,
        clean_text="Clean page 1 text",
        raw_text="Raw page 1 text",
        is_scanned=0,
        word_count=50,
        text_confidence=0.98,
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    p2 = DocumentPage(
        id="page_2",
        version_id="ver_test_1",
        page_number=2,
        clean_text="Clean page 2 text",
        raw_text="Raw page 2 text",
        is_scanned=1,
        word_count=40,
        text_confidence=0.65,
        review_status=ReviewStatus.FLAGGED.value,
    )
    prun = ProcessingRun(
        id="prun_test_1",
        version_id="ver_test_1",
        parser_version="2.0.0",
        ocr_engine="TESSERACT",
        config_hash="abc" * 20,
        result="SUCCESS",
    )
    session.add_all([source, doc, ver, p1, p2, prun])
    session.commit()
    session.close()

    # Test quality-report
    res_qr = cli_runner.invoke(cli, ["extract", "quality-report", "--version-id", "ver_test_1"])
    assert res_qr.exit_code == 0
    assert "AUTO_APPROVED" in res_qr.output
    assert "FLAGGED" in res_qr.output
    assert "0.98" in res_qr.output
    assert "0.65" in res_qr.output
    assert "Total Pages:         2" in res_qr.output
    assert "Flagged Count:       1" in res_qr.output
    assert "Auto-Approved Count: 1" in res_qr.output

    # Test quality-report missing version
    res_qr_missing = cli_runner.invoke(cli, ["extract", "quality-report", "--version-id", "nonexistent"])
    assert res_qr_missing.exit_code == 1
    assert "not found" in res_qr_missing.output

    # Test processing-runs
    res_pr = cli_runner.invoke(cli, ["extract", "processing-runs", "--version-id", "ver_test_1"])
    assert res_pr.exit_code == 0
    assert "prun_test_1" in res_pr.output
    assert "TESSERACT" in res_pr.output
    assert "2.0.0" in res_pr.output
    assert "SUCCESS" in res_pr.output

    # Test processing-runs missing version
    res_pr_missing = cli_runner.invoke(cli, ["extract", "processing-runs", "--version-id", "nonexistent"])
    assert res_pr_missing.exit_code == 1
    assert "not found" in res_pr_missing.output


def test_cli_review_commands(cli_runner: CliRunner):
    from adam.db.session import get_session
    from adam.db.models import Document, DocumentVersion, DocumentPage, ReviewAnnotation, AuditEvent, Source
    from adam.vocabularies import ReviewStatus

    session = get_session()
    source = Source(
        id="src_test_rev",
        department_id="FINANCE_TREASURY",
        name="Test Portal",
        permitted_domains=["test.uk.gov.in"],
        permitted_path_prefixes=["/"],
        written_authority_ref="AUTH-2",
        owner_name="Test Owner",
        owner_contact="test@uk.gov.in",
        status="APPROVED",
    )
    doc = Document(id="doc_test_2", source_id="src_test_rev", title="Test GO 2")
    ver = DocumentVersion(
        id="ver_test_2",
        document_id="doc_test_2",
        source_url="https://test.uk.gov.in/go2.pdf",
        mime_type="application/pdf",
        original_object_key="raw/ver_test_2.pdf",
        sha256="b" * 64,
        byte_size=1024,
    )
    p1 = DocumentPage(
        id="page_rev_1",
        version_id="ver_test_2",
        page_number=1,
        clean_text="Original clean 1",
        raw_text="Original raw 1",
        selected_text="Original clean 1",
        text_confidence=0.72,
        review_status=ReviewStatus.FLAGGED.value,
    )
    p2 = DocumentPage(
        id="page_rev_2",
        version_id="ver_test_2",
        page_number=2,
        clean_text="Original clean 2",
        raw_text="Original raw 2",
        selected_text="Original clean 2",
        text_confidence=0.55,
        review_status=ReviewStatus.FLAGGED.value,
    )
    session.add_all([source, doc, ver, p1, p2])
    session.commit()
    session.close()

    # 1. review list (default FLAGGED)
    res_list = cli_runner.invoke(cli, ["review", "list"])
    assert res_list.exit_code == 0
    assert "page_rev_1" in res_list.output
    assert "page_rev_2" in res_list.output
    assert "FLAGGED" in res_list.output

    # Test review list with filter
    res_list_filtered = cli_runner.invoke(cli, ["review", "list", "--version-id", "ver_test_2", "--status", "FLAGGED"])
    assert res_list_filtered.exit_code == 0
    assert "page_rev_1" in res_list_filtered.output

    # 2. review approve
    res_app = cli_runner.invoke(cli, ["review", "approve", "page_rev_1", "--reviewer", "officer_alice"])
    assert res_app.exit_code == 0
    assert "Page approved: page_rev_1" in res_app.output
    assert "REVIEWED" in res_app.output

    # Verify in DB
    session = get_session()
    p1_db = session.query(DocumentPage).filter(DocumentPage.id == "page_rev_1").first()
    assert p1_db.review_status == "REVIEWED"
    # Verify AuditEvent
    audit = session.query(AuditEvent).filter(
        AuditEvent.entity_type == "DOCUMENT_PAGE",
        AuditEvent.entity_id == "page_rev_1",
    ).first()
    assert audit is not None
    assert audit.action == "REVIEW_APPROVE"
    assert audit.actor == "officer_alice"
    session.close()

    # 3. review correct
    corrected_text = "Corrected transcript text for page 2"
    res_corr = cli_runner.invoke(
        cli,
        ["review", "correct", "page_rev_2", "--text", corrected_text, "--reviewer", "officer_bob"],
    )
    assert res_corr.exit_code == 0
    assert "Page corrected: page_rev_2" in res_corr.output
    assert "CORRECTED" in res_corr.output

    # Verify DB: ReviewAnnotation, page status, original text NOT modified
    session = get_session()
    p2_db = session.query(DocumentPage).filter(DocumentPage.id == "page_rev_2").first()
    assert p2_db.review_status == "CORRECTED"
    assert p2_db.clean_text == "Original clean 2"
    assert p2_db.raw_text == "Original raw 2"
    assert p2_db.selected_text == corrected_text

    annotation = session.query(ReviewAnnotation).filter(ReviewAnnotation.page_id == "page_rev_2").first()
    assert annotation is not None
    assert annotation.reviewer == "officer_bob"
    assert annotation.corrected_text == corrected_text

    audit_corr = session.query(AuditEvent).filter(
        AuditEvent.entity_type == "DOCUMENT_PAGE",
        AuditEvent.entity_id == "page_rev_2",
    ).first()
    assert audit_corr is not None
    assert audit_corr.actor == "officer_bob"
    session.close()

    # 4. review missing page
    res_app_missing = cli_runner.invoke(cli, ["review", "approve", "nonexistent"])
    assert res_app_missing.exit_code == 1
    assert "not found" in res_app_missing.output

    res_corr_missing = cli_runner.invoke(cli, ["review", "correct", "nonexistent", "--text", "foo"])
    assert res_corr_missing.exit_code == 1
    assert "not found" in res_corr_missing.output
