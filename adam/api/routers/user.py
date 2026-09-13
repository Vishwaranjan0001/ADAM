"""User profile and persistent preferences endpoints."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from adam.api.deps import get_db, get_user_context
from adam.memory.preferences import UserPreferenceManager
from adam.rag.models import UserContext

router = APIRouter()


class SetPreferenceRequest(BaseModel):
    opt_in: bool = True
    purpose: str = "UI display language and response formatting"
    preferences: Dict[str, Any] = {}


@router.get("/user/profile")
def get_user_profile(user_ctx: UserContext = Depends(get_user_context)) -> Dict[str, Any]:
    """Return active authenticated user context and clearance governance levels."""
    return {
        "user_id": user_ctx.user_id,
        "roles": user_ctx.roles,
        "department_id": user_ctx.department_id,
        "clearance_level": user_ctx.clearance_level,
        "is_admin": user_ctx.is_admin(),
    }


@router.get("/user/preferences")
def get_user_preferences(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Return decrypted user preferences if user has opted in."""
    from adam.db.models import UserPreference
    pref_row = db.query(UserPreference).filter(UserPreference.user_id == user_ctx.user_id.strip()).first()
    if not pref_row or pref_row.opt_in != 1:
        return {"opt_in": False, "purpose": None, "preferences": {}}

    mgr = UserPreferenceManager(db)
    pref_data = mgr.get_preference(user_ctx.user_id) or {}

    return {
        "opt_in": bool(pref_row.opt_in),
        "purpose": pref_row.purpose,
        "preferences": pref_data,
        "updated_at": pref_row.updated_at.isoformat() if pref_row.updated_at else None,
    }


@router.post("/user/preferences")
def set_user_preferences(
    req: SetPreferenceRequest,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Persist encrypted user preferences with explicit opt-in and purpose limitation."""
    mgr = UserPreferenceManager(db)
    pref = mgr.set_preference(
        user_id=user_ctx.user_id,
        purpose=req.purpose,
        preferences=req.preferences,
        opt_in=req.opt_in,
    )

    return {
        "success": True,
        "user_id": user_ctx.user_id,
        "opt_in": bool(pref.opt_in),
        "purpose": pref.purpose,
        "preferences": req.preferences,
    }


@router.delete("/user/preferences")
def delete_user_preferences(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> Dict[str, Any]:
    """Remove user preferences under user deletion rights."""
    mgr = UserPreferenceManager(db)
    mgr.delete_preference(user_ctx.user_id)
    return {"success": True, "user_id": user_ctx.user_id}
