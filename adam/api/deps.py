"""FastAPI dependency providers for ADAM API server."""
from typing import Generator, Optional
from fastapi import Header, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from adam.db.session import get_engine, get_session
from adam.rag.models import UserContext
from adam.vocabularies import Classification


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy database session, closing on teardown."""
    session = get_session(get_engine())
    try:
        yield session
    finally:
        session.close()


def get_user_context(
    x_user_id: str = Header(default="anonymous"),
    x_user_role: str = Header(default="PUBLIC"),
    x_clearance_level: str = Header(default="PUBLIC"),
    x_department_id: Optional[str] = Header(default=None),
) -> UserContext:
    """Build a UserContext from request headers. Falls back to PUBLIC clearance on invalid values."""
    valid_levels = {c.value for c in Classification}
    clearance = x_clearance_level if x_clearance_level in valid_levels else Classification.PUBLIC.value

    return UserContext(
        user_id=x_user_id,
        roles=[x_user_role],
        department_id=x_department_id,
        clearance_level=clearance,
    )


def get_trace_id(request: Request) -> str:
    """Retrieve or generate trace ID for the active request."""
    return getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"


def require_roles(*allowed_roles: str):
    """Dependency enforcing role-based access control."""
    def _role_checker(user_ctx: UserContext = Depends(get_user_context)) -> UserContext:
        user_roles = [r.upper() for r in (user_ctx.roles or [])]
        allowed = [r.upper() for r in allowed_roles]
        if not any(r in allowed for r in user_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Requires one of roles: {list(allowed_roles)}",
            )
        return user_ctx
    return _role_checker
