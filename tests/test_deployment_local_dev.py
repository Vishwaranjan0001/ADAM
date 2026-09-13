"""Tests for Phase 08: Native Local Development & Deployment specifications.

Verifies:
1. Sub-2-second mini public pilot corpus bootstrap (zero PII, 5 departments, idempotency)
2. Native system health diagnostics (adam dev doctor)
3. Disk cache ceiling enforcement (adam dev cache-clean)
4. Heavy worker mutual exclusion locking
5. Docker Compose multi-profile syntax (core, inference, ocr, eval)
"""

import os
import time
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adam.agent.coordinator import HeavyWorkerCoordinator, HeavyTaskType, ResourceContentionError
from adam.bootstrap import bootstrap_mini_corpus, MINI_CORPUS_SPEC
from adam.db.models import Base, Document, DocumentChunk, DocumentPage, DocumentVersion, Source
from adam.dev import run_doctor, clean_cache
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import Classification


@pytest.fixture
def dev_test_db(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    yield session
    session.close()


def test_bootstrap_sub_two_seconds_and_schema_integrity(dev_test_db, tmp_path):
    """Verify that mini pilot corpus bootstraps in under 2 seconds with zero PII."""
    storage = LocalStorageBackend(tmp_path / "bootstrap_storage")

    start = time.perf_counter()
    res = bootstrap_mini_corpus(dev_test_db, storage=storage, force=True)
    duration_s = time.perf_counter() - start

    # Acceptance criterion: Fast developer bootstrap (< 2.0s)
    assert duration_s < 2.0
    assert res["status"] == "BOOTSTRAPPED_SUCCESS"
    assert res["documents_created"] == 5
    assert res["chunks_created"] == 5

    # Verify all created documents are strictly PUBLIC
    docs = dev_test_db.query(Document).filter(Document.id.like("doc_pilot_%")).all()
    assert len(docs) == 5
    for d in docs:
        assert d.classification == Classification.PUBLIC.value
        assert "pilot" in d.id

    # Verify chunks exist with valid content
    chunks = dev_test_db.query(DocumentChunk).all()
    assert len(chunks) >= 5
    for c in chunks:
        assert c.content is not None
        assert len(c.content) > 20
        assert c.classification == Classification.PUBLIC.value

    # Test Idempotency: second run completes in < 0.2s without duplicating
    start_idemp = time.perf_counter()
    res_idemp = bootstrap_mini_corpus(dev_test_db, storage=storage, force=False)
    duration_idemp = time.perf_counter() - start_idemp

    assert duration_idemp < 0.2
    assert res_idemp["status"] == "ALREADY_BOOTSTRAPPED"
    assert dev_test_db.query(Document).filter(Document.id.like("doc_pilot_%")).count() == 5


def test_dev_doctor_system_diagnostics():
    """Verify system diagnostics runs cleanly and reports memory, disk, and engines."""
    report = run_doctor()
    assert "status" in report
    assert report["status"] in ("HEALTHY", "WARNING", "CRITICAL")
    assert report["profile"] == "MACBOOK_AIR_8GB"

    # Memory check
    mem = report["memory"]
    assert "total_ram_gb" in mem
    assert "available_ram_gb" in mem
    assert mem["macos_headroom_gb"] == 2.0

    # Disk check
    disk = report["disk"]
    assert "free_space_gb" in disk
    assert disk["cache_ceiling_mb"] == 2048.0

    # Database check
    assert report["database"]["connected"] is True

    # Engines check
    eng = report["engines"]
    assert "ocr_engine" in eng
    assert "stt_engine" in eng
    assert "tts_engine" in eng


def test_dev_cache_clean_enforces_ceiling(tmp_path, monkeypatch):
    """Verify that clean_cache prunes temporary files when ceiling is exceeded."""
    test_storage_dir = tmp_path / "cache_storage"
    test_storage_dir.mkdir()
    tmp_dir = test_storage_dir / "tmp"
    tmp_dir.mkdir()

    # Create dummy files: 3 files of 1MB each = 3MB
    one_mb = b"0" * (1024 * 1024)
    (tmp_dir / "old_temp1.bin").write_bytes(one_mb)
    time.sleep(0.01)
    (tmp_dir / "old_temp2.bin").write_bytes(one_mb)
    time.sleep(0.01)
    (tmp_dir / "old_temp3.bin").write_bytes(one_mb)

    monkeypatch.setattr("adam.dev.STORAGE_DIR", test_storage_dir)

    # Dry run test
    dry_res = clean_cache(cap_mb=2.0, dry_run=True)
    assert dry_res["current_size_mb"] >= 3.0
    assert dry_res["pruned_files"] >= 1
    assert dry_res["dry_run"] is True

    # Real clean test (cap at 2.0 MB -> should prune at least 1 file)
    clean_res = clean_cache(cap_mb=2.0, dry_run=False)
    assert clean_res["pruned_files"] >= 1
    assert clean_res["freed_mb"] >= 1.0


def test_heavy_worker_mutual_exclusion_lock():
    """Verify that active heavy worker lock prevents simultaneous heavy task execution."""
    coordinator = HeavyWorkerCoordinator()
    HeavyWorkerCoordinator.reset()
    coord = HeavyWorkerCoordinator()

    # Acquire chat inference lock
    with coord.acquire_worker(HeavyTaskType.CHAT_INFERENCE, task_id="test_chat_01"):
        assert coord.is_busy is True
        assert coord.active_task == HeavyTaskType.CHAT_INFERENCE

        # Attempting to run OCR simultaneously must be rejected
        with pytest.raises(ResourceContentionError):
            with coord.acquire_worker(HeavyTaskType.OCR_PROCESSING, task_id="test_ocr_02", timeout_seconds=0.0):
                pass

    # After releasing chat lock, worker becomes available
    assert coord.is_busy is False
    HeavyWorkerCoordinator.reset()


def test_docker_compose_and_dockerfiles_exist_and_valid():
    """Verify the clone-and-run development stack and its production overlay."""
    root_dir = Path(__file__).resolve().parent.parent

    compose_path = root_dir / "docker-compose.yml"
    assert compose_path.exists()
    compose_content = compose_path.read_text()

    # The default compose file must start the complete editable development stack.
    assert "postgres:" in compose_content
    assert "api:" in compose_content
    assert "ui:" in compose_content
    assert "--reload" in compose_content
    assert "healthcheck:" in compose_content
    assert (root_dir / "docker-compose.prod.yml").exists()

    # Verify Dockerfiles
    dockerfile_path = root_dir / "Dockerfile"
    assert dockerfile_path.exists()
    assert "tesseract-ocr" in dockerfile_path.read_text()

    ui_dockerfile_path = root_dir / "ui" / "Dockerfile"
    assert ui_dockerfile_path.exists()
    assert "node:20-alpine" in ui_dockerfile_path.read_text()
