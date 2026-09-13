"""ADAM Gateway Middlewares: Trace ID injection, Rate Limiting, and Structured Error Formatting."""

import time
import uuid
from typing import Dict, Tuple, Optional
from collections import defaultdict

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a unique trace_id propagated through request.state and response headers."""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        request.state.trace_id = trace_id

        response: Response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


class InMemoryTokenBucketRateLimiter:
    """Sliding-window token bucket rate limiter tracking requests per client key."""

    def __init__(self, requests_per_minute: int = 60, burst_capacity: int = 15):
        self.rate = requests_per_minute  # tokens per minute
        self.capacity = burst_capacity + requests_per_minute
        self.tokens: Dict[str, float] = defaultdict(lambda: float(self.capacity))
        self.last_updated: Dict[str, float] = defaultdict(time.time)
        self.fill_rate = requests_per_minute / 60.0  # tokens per second

    def is_allowed(self, key: str, cost: float = 1.0) -> Tuple[bool, int]:
        """Check if request is permitted.

        Returns (allowed: bool, retry_after_seconds: int).
        """
        now = time.time()
        last = self.last_updated[key]
        elapsed = max(0.0, now - last)

        # Refill tokens based on elapsed time
        current_tokens = min(self.capacity, self.tokens[key] + elapsed * self.fill_rate)
        self.tokens[key] = current_tokens
        self.last_updated[key] = now

        if current_tokens >= cost:
            self.tokens[key] -= cost
            return True, 0

        # Calculate wait time needed for at least 1 token
        needed = cost - current_tokens
        retry_after = max(1, int(needed / self.fill_rate))
        return False, retry_after

    def reset(self, key: Optional[str] = None):
        """Reset rate limiter state (useful for tests)."""
        if key:
            self.tokens.pop(key, None)
            self.last_updated.pop(key, None)
        else:
            self.tokens.clear()
            self.last_updated.clear()


# Global default rate limiter (60 req/min, burst +10)
global_rate_limiter = InMemoryTokenBucketRateLimiter(requests_per_minute=60, burst_capacity=10)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-user/tenant rate limits and return HTTP 429 with Retry-After when exceeded."""

    def __init__(self, app, limiter: Optional[InMemoryTokenBucketRateLimiter] = None, enabled: bool = True):
        super().__init__(app)
        self.limiter = limiter or global_rate_limiter
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # Exclude internal health checks, docs, and favicon
        path = request.url.path
        if path in ("/docs", "/openapi.json", "/redoc", "/favicon.ico", "/api/health"):
            return await call_next(request)

        # Identify client by user_id, tenant_id, or client IP
        client_key = (
            request.headers.get("X-User-Id")
            or request.headers.get("X-Tenant-Id")
            or (request.client.host if request.client else "unknown")
        )

        allowed, retry_after = self.limiter.is_allowed(client_key)
        if not allowed:
            trace_id = getattr(request.state, "trace_id", uuid.uuid4().hex)
            payload = {
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded. Please retry after {retry_after} seconds.",
                    "trace_id": trace_id,
                    "details": {"retry_after": retry_after},
                }
            }
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=payload,
                headers={"Retry-After": str(retry_after), "X-Trace-Id": trace_id},
            )

        return await call_next(request)


def format_error_response(status_code: int, code: str, message: str, trace_id: str, details: Optional[Dict] = None) -> JSONResponse:
    """Generate structured JSON error adhering to core specification."""
    payload = {
        "error": {
            "code": code,
            "message": message,
            "trace_id": trace_id,
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status_code, content=payload, headers={"X-Trace-Id": trace_id})
