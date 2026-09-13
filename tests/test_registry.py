"""Tests for source onboarding, governance, and audit trail preservation."""

import pytest
from sqlalchemy.orm import Session

from adam.ingest.registry import (
    SourceRegistry,
    SourceOnboardingSheet,
    SourceRegistryError,
    SourceNotFoundError,
    InvalidSourceStateError,
)
from adam.vocabularies import SourceStatus, Classification, RefreshCadence


def test_onboard_source_workflow(db_session: Session, sample_source_sheet: SourceOnboardingSheet):
    registry = SourceRegistry(db_session)
    source = registry.onboard(sample_source_sheet, actor="records_officer_1")

    assert source.id == sample_source_sheet.id
    assert source.status == SourceStatus.PENDING_APPROVAL.value
    assert source.owner_name == "Director of Treasuries, UK"

    # Verify initial audit trail
    history = registry.get_audit_history(source.id)
    assert len(history) == 1
    assert history[0].action == "ONBOARD"
    assert history[0].actor == "records_officer_1"


def test_approve_pause_remove_governance_cycle(
    db_session: Session, sample_source_sheet: SourceOnboardingSheet
):
    """Acceptance criteria 3: A source owner can see, approve, pause and remove a connector

    without deleting audit history.
    """
    registry = SourceRegistry(db_session)
    source = registry.onboard(sample_source_sheet, actor="records_officer_1")

    # 1. Approve
    approved = registry.approve(source.id, approver="it_secretary", notes="Authorized via GO-123")
    assert approved.status == SourceStatus.APPROVED.value
    assert approved.is_active() is True

    # 2. Pause
    paused = registry.pause(source.id, actor="it_secretary", reason="Routine portal maintenance")
    assert paused.status == SourceStatus.PAUSED.value
    assert paused.is_active() is False

    # 3. Re-approve
    reapproved = registry.approve(source.id, approver="it_secretary", notes="Maintenance complete")
    assert reapproved.status == SourceStatus.APPROVED.value

    # 4. Remove
    removed = registry.remove(source.id, actor="commissioner", reason="Decommissioned portal")
    assert removed.status == SourceStatus.REMOVED.value
    assert removed.is_active() is False

    # Verify audit history was completely preserved
    history = registry.get_audit_history(source.id)
    actions = [h.action for h in history]
    assert actions == ["ONBOARD", "APPROVE", "PAUSE", "APPROVE", "REMOVE"]

    # Verify removed source cannot be re-approved without new onboarding
    with pytest.raises(InvalidSourceStateError):
        registry.approve(source.id, approver="it_secretary")


def test_onboarding_validation_rejects_malformed_inputs():
    sheet = SourceOnboardingSheet(
        name="",  # Missing name
        department_id="FINANCE_TREASURY",
        owner_name="Owner",
        owner_contact="owner@gov.in",
        written_authority_ref="REF-1",
        permitted_domains=["ekosh.uk.gov.in"],
        permitted_path_prefixes=["/government-orders/"],
    )
    with pytest.raises(ValueError, match="Source name is required"):
        sheet.validate()

    sheet.name = "Valid Name"
    sheet.permitted_domains = ["https://ekosh.uk.gov.in"]  # Should be hostname only
    with pytest.raises(ValueError, match="Invalid permitted domain"):
        sheet.validate()

    sheet.permitted_domains = ["ekosh.uk.gov.in"]
    sheet.permitted_path_prefixes = ["government-orders/"]  # Missing leading slash
    with pytest.raises(ValueError, match="must start with '/'"):
        sheet.validate()
