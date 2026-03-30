"""Rate limiting middleware for Gridalytics API."""

import time
from collections import defaultdict

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter with tiered limits per endpoint category.

    Limits:
    - /api/v1/forecast/*: 30 req/min (predictions are compute-heavy)
    - /api/v1/admin/*: 10 req/min
    - All other endpoints: 120 req/min
    """

    def __init__(self, app):
        super().__init__(app)
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        now = time.time()

        # Determine rate limit by path category
        if "/forecast/" in path:
            limit, window = 30, 60
        elif "/admin/" in path:
            limit, window = 10, 60
        else:
            limit, window = 120, 60

        # Key: IP + path category
        parts = path.split("/")
        category = parts[3] if len(parts) > 3 else "default"
        key = f"{client_ip}:{category}"

        # Clean expired entries
        self.requests[key] = [t for t in self.requests[key] if now - t < window]

        if len(self.requests[key]) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")

        self.requests[key].append(now)
        response = await call_next(request)

        # Add rate limit headers
        remaining = limit - len(self.requests[key])
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(now + window))

        return response
