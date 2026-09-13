"""Phase 09: Contract and OpenAPI Test Suite.

Verifies:
1. FastAPI OpenAPI 3.1 schema conformity and route coverage
2. Retry and idempotency semantics using Idempotency-Key
3. Stealth auth and error non-disclosure
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from adam.api.app import create_app
from adam.db.models import Base, FeedbackRecord, IdempotencyRecord
from adam.vocabularies import Classification


@pytest.fixture
def contract_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def contract_session(contract_engine):
    factory = sessionmaker(bind=contract_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(contract_engine):
    """Test client with test DB dependency override."""
    app = create_app()
    from adam.api import deps

    def override_db():
        factory = sessionmaker(bind=contract_engine, autoflush=False, expire_on_commit=False)
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_openapi_schema_conformance():
    """Validate OpenAPI schema specification generation and paths."""
    app = create_app()
    schema = app.openapi()

    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "ADAM API"
    assert "paths" in schema

    paths = schema["paths"]
    # Check core endpoints exist in schema
    assert "/api/chat" in paths
    assert "/api/sessions" in paths
    assert "/api/voice/transcribe" in paths
    assert "/api/voice/synthesize" in paths
    assert "/v1/chat" in paths
    assert "/v1/feedback" in paths
    assert "/v1/ingestions" in paths
    assert "/v1/search" in paths
    assert "/v1/documents/{doc_id}/versions/{version_id}/pages/{page_num}" in paths

    # Check components
    assert "components" in schema
    assert "schemas" in schema["components"]


def test_idempotency_key_deduplication(client, contract_session):
    """Verify that repeating a request with the same Idempotency-Key returns the cached response."""
    payload = {
        "trace_id": "trace_idemp_001",
        "feedback_type": "CORRECTION",
        "comment": "Initial review note",
        "correction_text": "Updated amount is Rs 1800",
        "rating": 5,
    }
    headers = {
        "X-User-Id": "officer_audit_01",
        "X-User-Role": "OFFICER",
        "Idempotency-Key": "idemp-key-audit-9999",
    }

    # First call -> creates record
    res1 = client.post("/v1/feedback", json=payload, headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    first_feedback_id = data1["feedback_id"]

    # Verify 1 feedback record exists
    records_count_1 = contract_session.query(FeedbackRecord).filter(FeedbackRecord.trace_id == "trace_idemp_001").count()
    assert records_count_1 == 1

    # Second call with identical Idempotency-Key -> returns cached response without duplicate creation
    res2 = client.post("/v1/feedback", json=payload, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["feedback_id"] == first_feedback_id

    # Verify no duplicate record was created
    records_count_2 = contract_session.query(FeedbackRecord).filter(FeedbackRecord.trace_id == "trace_idemp_001").count()
    assert records_count_2 == 1


def test_auth_and_stealth_error_nondisclosure(client):
    """Verify 404 stealth behavior on unauthorized or missing resources without revealing existence."""
    # Attempt to access non-existent or restricted document page
    res = client.get(
        "/v1/documents/doc_nonexistent_secret/versions/ver_999/pages/1",
        headers={
            "X-User-Id": "unauthorized_user",
            "X-User-Role": "PUBLIC",
            "X-Clearance-Level": Classification.PUBLIC.value,
        },
    )
    # Must return 404 with generic detail, not disclosing internal errors, table structures, or stack traces
    assert res.status_code == 404
    data = res.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message"] == "Document or page not found"
    assert "sqlite" not in str(data).lower()
    assert "traceback" not in str(data).lower()


def test_validation_error_nondisclosure(client):
    """Verify 422 validation errors do not leak server paths, secrets, or internal variables."""
    # Send malformed request to /v1/feedback
    res = client.post(
        "/v1/feedback",
        json={"invalid_field": 123},  # missing required trace_id
        headers={"X-User-Id": "officer_1"},
    )
    assert res.status_code == 422
    body = res.text
    assert "traceback" not in body.lower()
    assert "File \"" not in body
    assert "password" not in body.lower()
