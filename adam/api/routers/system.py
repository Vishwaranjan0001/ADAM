"""System metadata, model registry, and taxonomy endpoints."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from adam.api.deps import get_db
from adam.model.registry import CANONICAL_MODELS, ModelRegistry
from adam.model.runtime import OllamaModelRuntime
from adam.vocabularies import (
    AuthorityLevel,
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ModelStatus,
)

PRECEDENT_RELATION_TYPES = [
    "SUPERSEDES",
    "AMENDS",
    "IN_CONTINUATION_OF",
    "READ_WITH",
    "REFERS_TO",
]

router = APIRouter()

DEPARTMENT_LABELS: Dict[str, str] = {
    DepartmentId.FINANCE_TREASURY.value: "Finance & Treasury",
    DepartmentId.RURAL_DEVELOPMENT.value: "Rural Development & Panchayati Raj",
    DepartmentId.AUDIT_DIRECTORATE.value: "Audit Directorate",
    DepartmentId.BOARD_OF_REVENUE.value: "Board of Revenue",
    DepartmentId.GENERAL_ADMINISTRATION.value: "General Administration (GAD)",
    DepartmentId.LEGAL_AFFAIRS.value: "Law & Justice",
    DepartmentId.OPEN_GOVERNMENT_DATA.value: "Open Government Data Portal",
    DepartmentId.UNKNOWN.value: "Other / Unspecified",
}


@router.get("/system/models")
def get_models(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Return all approved release-controlled models from the model registry."""
    registry = ModelRegistry(db)
    models = registry.list_all()
    if not models:
        # Fallback to canonical models if database has not yet been seeded
        models = list(CANONICAL_MODELS.values())

    return [
        {
            "id": m.id,
            "name": m.name,
            "revision": m.revision,
            "quantization": m.quantization,
            "file_size_mb": round(m.file_size_bytes / (1024 * 1024), 1) if m.file_size_bytes else 0,
            "context_window": m.context_window,
            "languages": m.languages,
            "is_primary": m.is_primary,
            "is_fallback": m.is_fallback,
            "is_comparator": m.is_comparator,
            "license_id": m.license_id,
            "license_status": str(m.license_status.value if hasattr(m.license_status, 'value') else m.license_status),
            "status": str(m.status.value if hasattr(m.status, 'value') else m.status),
            "serving_runtime": m.serving_runtime,
            "is_installed": OllamaModelRuntime(m).is_model_present(),
            "unavailable_reason": None if OllamaModelRuntime(m).is_model_present() else "Not installed in Ollama",
        }
        for m in models
    ]


@router.get("/system/vocabularies")
def get_vocabularies() -> Dict[str, Any]:
    """Return controlled taxonomies for departments, classifications, and document types."""
    departments = [
        {
            "id": dept.value,
            "label": DEPARTMENT_LABELS.get(dept.value, dept.value.replace("_", " ").title()),
        }
        for dept in DepartmentId
        if dept != DepartmentId.UNKNOWN
    ]

    classifications = [c.value for c in Classification]
    doc_types = [d.value for d in DocType if d != DocType.UNKNOWN]
    precedent_types = PRECEDENT_RELATION_TYPES

    return {
        "departments": departments,
        "classifications": classifications,
        "doc_types": doc_types,
        "precedent_types": precedent_types,
    }
