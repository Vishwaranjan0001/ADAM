"""Tests for controlled vocabularies and unknown field preservation."""

from adam.vocabularies import (
    DocType,
    DepartmentId,
    Classification,
    AuthorityLevel,
    LifecycleStatus,
    ProvenanceStatus,
    SourceStatus,
)


def test_controlled_vocabularies_known_values():
    assert DocType.GO == "GO"
    assert DocType.RTI_MANUAL == "RTI_MANUAL"
    assert DepartmentId.FINANCE_TREASURY == "FINANCE_TREASURY"
    assert Classification.PUBLIC == "PUBLIC"
    assert AuthorityLevel.STATE_CABINET == "STATE_CABINET"
    assert LifecycleStatus.ACTIVE == "ACTIVE"
    assert ProvenanceStatus.VERIFIED == "VERIFIED"
    assert SourceStatus.APPROVED == "APPROVED"


def test_controlled_vocabularies_preserve_unknowns():
    """Verify requirement: preserve unknown fields rather than inventing values."""
    custom_type = "Special_Commission_Gazette_Notice"
    preserved = DocType.validate_or_preserve(custom_type)
    assert preserved == custom_type

    # Standardized existing value maps correctly
    assert DocType.validate_or_preserve("go") == "GO"
    assert DocType.validate_or_preserve("rti manual") == "RTI_MANUAL"

    custom_dept = "FOREST_AND_WILDLIFE_DIRECTORATE"
    preserved_dept = DepartmentId.validate_or_preserve(custom_dept)
    assert preserved_dept == custom_dept

    # None or empty defaults to UNKNOWN
    assert DocType.validate_or_preserve(None) == DocType.UNKNOWN.value
    assert DepartmentId.validate_or_preserve("") == DepartmentId.UNKNOWN.value


def test_classification_validation():
    assert Classification.is_valid("PUBLIC") is True
    assert Classification.is_valid("CONFIDENTIAL") is True
    assert Classification.is_valid("SECRET_UNAUTHORIZED") is False
