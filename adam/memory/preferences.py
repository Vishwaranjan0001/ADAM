"""Persistent user preference manager with explicit opt-in, purpose limitation, and user delete controls.

Enforces:
- 'Persistent preferences require opt-in, purpose limitation and a user-visible delete control.'
- Field-level encryption for all stored preference data.
- Access and deletion are audited.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from adam.db.models import AuditEvent, UserPreference
from adam.memory.crypto import AuthenticatedCipher, get_cipher


class OptInRequiredError(ValueError):
    """Raised when an attempt is made to persist preferences without explicit opt-in consent."""
    pass


class PurposeLimitationError(ValueError):
    """Raised when preference storage lacks a stated, valid administrative purpose."""
    pass


class UserPreferenceManager:
    """Manages persistent user preferences governed by opt-in and purpose limitation."""

    def __init__(self, db: Session, cipher: Optional[AuthenticatedCipher] = None):
        self.db = db
        self.cipher = cipher or get_cipher()

    def set_preference(
        self,
        user_id: str,
        purpose: str,
        preferences: Dict[str, Any],
        opt_in: bool = True,
    ) -> UserPreference:
        """Store persistent preferences with verified opt-in and stated purpose."""
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required")

        if not opt_in:
            raise OptInRequiredError(
                "Persistent preferences require explicit user opt-in consent before storage."
            )

        if not purpose or len(purpose.strip()) < 5:
            raise PurposeLimitationError(
                "A specific, stated purpose is required to persist user preferences (e.g. 'Interface display and language formatting')."
            )

        now = datetime.now(timezone.utc)
        ciphertext = self.cipher.encrypt_json(preferences)

        pref = self.db.query(UserPreference).filter(UserPreference.user_id == user_id.strip()).first()
        if pref:
            pref.opt_in = 1
            pref.purpose = purpose.strip()
            pref.preference_data_ciphertext = ciphertext
            pref.updated_at = now
        else:
            pref = UserPreference(
                user_id=user_id.strip(),
                opt_in=1,
                purpose=purpose.strip(),
                preference_data_ciphertext=ciphertext,
                created_at=now,
                updated_at=now,
            )
            self.db.add(pref)
        self.db.flush()

        # Audit setting preference
        audit = AuditEvent(
            entity_type="USER_PREFERENCE",
            entity_id=pref.id,
            action="SET_PREFERENCE",
            actor=user_id,
            details_json={
                "purpose": purpose.strip(),
                "keys_stored": list(preferences.keys()),
            },
            timestamp=now,
        )
        self.db.add(audit)
        self.db.commit()

        return pref

    def get_preference(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt persistent preferences if opt-in is active."""
        pref = self.db.query(UserPreference).filter(UserPreference.user_id == user_id.strip()).first()
        if not pref or pref.opt_in != 1 or not pref.preference_data_ciphertext:
            return None

        data = self.cipher.decrypt_json(pref.preference_data_ciphertext)

        # Audit access without logging preference content
        audit = AuditEvent(
            entity_type="USER_PREFERENCE",
            entity_id=pref.id,
            action="GET_PREFERENCE",
            actor=user_id,
            details_json={"purpose": pref.purpose},
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(audit)
        self.db.commit()

        return data

    def delete_preference(self, user_id: str, actor: Optional[str] = None) -> bool:
        """User-visible delete control to permanently erase preferences."""
        pref = self.db.query(UserPreference).filter(UserPreference.user_id == user_id.strip()).first()
        if not pref:
            return False

        pref_id = pref.id
        self.db.delete(pref)

        # Audit deletion leaving zero residual data
        now = datetime.now(timezone.utc)
        audit = AuditEvent(
            entity_type="USER_PREFERENCE",
            entity_id=pref_id,
            action="DELETE_PREFERENCE",
            actor=actor or user_id,
            details_json={"user_id": user_id},
            timestamp=now,
        )
        self.db.add(audit)
        self.db.commit()

        return True
