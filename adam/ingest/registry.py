"""Source registry, onboarding workflow, and governance management."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from adam.db.models import Source, AuditEvent
from adam.vocabularies import (
    DepartmentId,
    Classification,
    SourceStatus,
    RefreshCadence,
)


class SourceRegistryError(Exception):
    """Base exception for source registry and governance errors."""
    pass


class SourceNotFoundError(SourceRegistryError):
    """Raised when source ID is not found."""
    pass


class InvalidSourceStateError(SourceRegistryError):
    """Raised when operation is invalid for current source state."""
    pass


@dataclass
class SourceOnboardingSheet:
    """Department-approved onboarding sheet for a public or departmental records portal."""
    name: str
    department_id: str
    owner_name: str
    owner_contact: str
    written_authority_ref: str
    permitted_domains: List[str]
    permitted_path_prefixes: List[str]
    access_classification: str = Classification.PUBLIC.value
    refresh_cadence: str = RefreshCadence.WEEKLY.value
    rate_limit_per_minute: int = 30
    retention_policy: str = "PERMANENT"
    terms_and_conditions: Optional[str] = None
    id: Optional[str] = None

    def validate(self) -> None:
        """Validate all required fields of the onboarding sheet."""
        if not self.name or not self.name.strip():
            raise ValueError("Source name is required.")
        if not self.owner_name or not self.owner_name.strip():
            raise ValueError("Departmental owner name is required.")
        if not self.owner_contact or not self.owner_contact.strip():
            raise ValueError("Departmental owner contact is required.")
        if not self.written_authority_ref or not self.written_authority_ref.strip():
            raise ValueError("Written authority reference is required.")
        if not self.permitted_domains:
            raise ValueError("At least one permitted government domain must be specified.")
        for domain in self.permitted_domains:
            if not domain or "/" in domain or ":" in domain:
                # clean domain should be hostname only
                raise ValueError(f"Invalid permitted domain: '{domain}'. Must be a valid hostname without scheme or path.")
        if not self.permitted_path_prefixes:
            raise ValueError("At least one permitted path prefix must be specified.")
        for path in self.permitted_path_prefixes:
            if not path.startswith("/"):
                raise ValueError(f"Permitted path prefix must start with '/': '{path}'")
        if self.rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute must be positive.")


class SourceRegistry:
    """Manages source onboarding, authorization lifecycle, and audit preservation."""

    def __init__(self, session: Session):
        self.session = session

    def onboard(self, sheet: SourceOnboardingSheet, actor: str = "system") -> Source:
        """Onboard a new source with PENDING_APPROVAL status and record audit log."""
        sheet.validate()

        source_id = sheet.id or f"src_{uuid.uuid4().hex[:12]}"
        existing = self.session.query(Source).filter(Source.id == source_id).first()
        if existing:
            raise SourceRegistryError(f"Source with id '{source_id}' already exists.")

        dept_id = DepartmentId.validate_or_preserve(sheet.department_id)
        classification = sheet.access_classification
        if not Classification.is_valid(classification):
            classification = Classification.PUBLIC.value

        source = Source(
            id=source_id,
            name=sheet.name.strip(),
            department_id=dept_id,
            owner_name=sheet.owner_name.strip(),
            owner_contact=sheet.owner_contact.strip(),
            written_authority_ref=sheet.written_authority_ref.strip(),
            permitted_domains=sheet.permitted_domains,
            permitted_path_prefixes=sheet.permitted_path_prefixes,
            access_classification=classification,
            refresh_cadence=sheet.refresh_cadence,
            rate_limit_per_minute=sheet.rate_limit_per_minute,
            retention_policy=sheet.retention_policy,
            status=SourceStatus.PENDING_APPROVAL.value,
        )
        self.session.add(source)

        audit = AuditEvent(
            entity_type="SOURCE",
            entity_id=source_id,
            action="ONBOARD",
            actor=actor,
            details_json={
                "name": source.name,
                "department_id": source.department_id,
                "owner": source.owner_name,
                "written_authority_ref": source.written_authority_ref,
                "permitted_domains": source.permitted_domains,
                "permitted_path_prefixes": source.permitted_path_prefixes,
                "status": source.status,
            },
        )
        self.session.add(audit)
        self.session.flush()
        return source

    def approve(self, source_id: str, approver: str, notes: Optional[str] = None) -> Source:
        """Approve an onboarded or paused source for automated crawling."""
        source = self.get_or_raise(source_id)
        if source.status == SourceStatus.REMOVED.value:
            raise InvalidSourceStateError(
                f"Cannot approve removed source '{source_id}'. Onboard a new source instead."
            )

        prev_status = source.status
        source.status = SourceStatus.APPROVED.value
        source.updated_at = datetime.now(timezone.utc)

        audit = AuditEvent(
            entity_type="SOURCE",
            entity_id=source_id,
            action="APPROVE",
            actor=approver,
            details_json={
                "previous_status": prev_status,
                "new_status": source.status,
                "notes": notes,
            },
        )
        self.session.add(audit)
        self.session.flush()
        return source

    def pause(self, source_id: str, actor: str, reason: str) -> Source:
        """Pause connector execution without deleting source or audit history."""
        source = self.get_or_raise(source_id)
        if source.status == SourceStatus.REMOVED.value:
            raise InvalidSourceStateError(f"Cannot pause removed source '{source_id}'.")

        prev_status = source.status
        source.status = SourceStatus.PAUSED.value
        source.updated_at = datetime.now(timezone.utc)

        audit = AuditEvent(
            entity_type="SOURCE",
            entity_id=source_id,
            action="PAUSE",
            actor=actor,
            details_json={
                "previous_status": prev_status,
                "new_status": source.status,
                "reason": reason,
            },
        )
        self.session.add(audit)
        self.session.flush()
        return source

    def remove(self, source_id: str, actor: str, reason: str) -> Source:
        """Soft-remove connector. Preserves all past audit events, documents, and versions intact."""
        source = self.get_or_raise(source_id)
        prev_status = source.status
        source.status = SourceStatus.REMOVED.value
        source.updated_at = datetime.now(timezone.utc)

        audit = AuditEvent(
            entity_type="SOURCE",
            entity_id=source_id,
            action="REMOVE",
            actor=actor,
            details_json={
                "previous_status": prev_status,
                "new_status": source.status,
                "reason": reason,
            },
        )
        self.session.add(audit)
        self.session.flush()
        return source

    def get(self, source_id: str) -> Optional[Source]:
        """Fetch source by ID."""
        return self.session.query(Source).filter(Source.id == source_id).first()

    def get_or_raise(self, source_id: str) -> Source:
        """Fetch source by ID or raise SourceNotFoundError."""
        src = self.get(source_id)
        if not src:
            raise SourceNotFoundError(f"Source with id '{source_id}' not found.")
        return src

    def list(
        self,
        department_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Source]:
        """List sources with optional filters."""
        query = self.session.query(Source)
        if department_id:
            query = query.filter(Source.department_id == department_id)
        if status:
            query = query.filter(Source.status == status)
        return query.order_by(Source.created_at.desc()).all()

    def get_audit_history(self, source_id: str) -> List[AuditEvent]:
        """Retrieve complete immutable audit history for a source."""
        return (
            self.session.query(AuditEvent)
            .filter(AuditEvent.entity_type == "SOURCE", AuditEvent.entity_id == source_id)
            .order_by(AuditEvent.timestamp.asc())
            .all()
        )
