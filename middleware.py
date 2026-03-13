"""
Production middleware stack:
  • Privacy-safe request/response logging
  • Latency measurement (X-Process-Time header)
  • Sliding-window rate limiting keyed by API key
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Dict, List, Tuple

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from config import settings

logger = logging.getLogger("machine_health")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOGGING + LATENCY MIDDLEWARE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LoggingAndLatencyMiddleware(BaseHTTPMiddleware):
    """
    Logs every request with method, path, status code, and latency.
    Deliberately does NOT log request/response bodies (privacy-safe).
    Injects ``X-Process-Time`` header so clients can monitor latency.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()

        # Log incoming request (no body)
        logger.info(
            "→ %s %s  client=%s",
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
        )

        response: Response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"

        logger.info(
            "← %s %s  status=%s  latency=%.2fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        return response


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RATE LIMITER MIDDLEWARE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    In-memory sliding-window rate limiter.

    Keys requests by the ``X-API-Key`` header value (falls back to client IP).
    Returns HTTP 429 when the limit is exceeded.
    """

    def __init__(self, app, max_requests: int | None = None, window_seconds: int | None = None) -> None:  # noqa: ANN001
        super().__init__(app)
        self.max_requests: int = max_requests or settings.rate_limit_requests
        self.window_seconds: int = window_seconds or settings.rate_limit_window_seconds
        # key → list of timestamps
        self._buckets: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        key = request.headers.get("X-API-Key") or (
            request.client.host if request.client else "anonymous"
        )
        now = time.time()
        window_start = now - self.window_seconds

        # Prune expired timestamps
        bucket = self._buckets[key]
        self._buckets[key] = [ts for ts in bucket if ts > window_start]

        if len(self._buckets[key]) >= self.max_requests:
            logger.warning("Rate limit exceeded for key=%s", key[:8] + "…")
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )

        self._buckets[key].append(now)
        return await call_next(request)
