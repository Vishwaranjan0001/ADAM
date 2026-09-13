"""Tests for user preference management with opt-in, purpose limitation, and user delete controls."""

import pytest

from adam.db.models import AuditEvent, UserPreference
from adam.memory.preferences import (
    OptInRequiredError,
    PurposeLimitationError,
    UserPreferenceManager,
)


def test_user_preference_requires_opt_in(db_session):
    """Verify that attempting to save preferences without explicit opt-in is rejected."""
    manager = UserPreferenceManager(db_session)

    with pytest.raises(OptInRequiredError, match="explicit user opt-in consent"):
        manager.set_preference(
            user_id="officer_pref",
            purpose="Interface display formatting",
            preferences={"language": "hi", "dense_tables": True},
            opt_in=False,
        )


def test_user_preference_requires_purpose_limitation(db_session):
    """Verify that preferences cannot be stored without a stated, valid administrative purpose."""
    manager = UserPreferenceManager(db_session)

    with pytest.raises(PurposeLimitationError, match="stated purpose is required"):
        manager.set_preference(
            user_id="officer_pref",
            purpose="",  # Empty purpose
            preferences={"language": "en"},
            opt_in=True,
        )


def test_user_preference_crud_and_user_delete_control(db_session):
    """Verify storing, retrieving, and permanently deleting persistent preferences."""
    manager = UserPreferenceManager(db_session)

    # 1. Set preference with opt-in and stated purpose
    pref = manager.set_preference(
        user_id="officer_pref",
        purpose="Administrative UI language and notification density",
        preferences={"language": "hi", "font_size": "large"},
        opt_in=True,
    )
    assert pref.opt_in == 1

    # 2. Get preference
    retrieved = manager.get_preference("officer_pref")
    assert retrieved is not None
    assert retrieved["language"] == "hi"
    assert retrieved["font_size"] == "large"

    # 3. User-visible delete control permanently removes preferences
    deleted = manager.delete_preference("officer_pref")
    assert deleted is True

    # 4. Verify gone
    assert manager.get_preference("officer_pref") is None
    assert db_session.query(UserPreference).filter(UserPreference.user_id == "officer_pref").count() == 0

    # 5. Verify deletion audit record exists
    del_audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "USER_PREFERENCE", AuditEvent.action == "DELETE_PREFERENCE")
        .first()
    )
    assert del_audit is not None
