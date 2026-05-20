
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("ocr.api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

class LatencyLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        t0       = time.perf_counter()
        response = await call_next(request)
        latency  = (time.perf_counter() - t0) * 1000.0

        response.headers["X-Process-Time-Ms"] = f"{latency:.1f}"

        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            "%s %s → %d  %.1f ms",
            request.method,
            request.url.path,
            response.status_code,
            latency,
        )
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):

    def __init__(
        self,
        app,
        max_requests: int = 30,
        window_seconds: float = 60.0,
        whitelist: list[str] | None = None,
    ):
        super().__init__(app)
        self.max_requests     = max_requests
        self.window_seconds   = window_seconds
        self.whitelist        = set(whitelist or ["/", "/docs", "/openapi.json", "/health"])

        self._windows: dict[str, deque] = {}

    def _get_ip(self, request: Request) -> str:

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.whitelist:
            return await call_next(request)

        ip  = self._get_ip(request)
        now = time.monotonic()

        if ip not in self._windows:
            self._windows[ip] = deque()

        window = self._windows[ip]

        while window and now - window[0] > self.window_seconds:
            window.popleft()

        if len(window) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - window[0])) + 1
            logger.warning("Rate limit superado para IP %s (%d req en %.0fs)", ip, len(window), self.window_seconds)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Demasiadas solicitudes. Intenta de nuevo en {retry_after} segundos.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
        return await call_next(request)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):

    HEADERS = {
        "X-Content-Type-Options":  "nosniff",
        "X-Frame-Options":         "DENY",
        "X-XSS-Protection":        "1; mode=block",
        "Referrer-Policy":         "strict-origin-when-cross-origin",

        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "font-src 'self' cdn.jsdelivr.net;"
        ),
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for key, value in self.HEADERS.items():
            response.headers.setdefault(key, value)
        return response

def add_middlewares(
    app: FastAPI,
    rate_limit_max: int = 30,
    rate_limit_window: float = 60.0,
) -> None:

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=rate_limit_max,
        window_seconds=rate_limit_window,
    )
    app.add_middleware(LatencyLoggingMiddleware)
    logger.info(
        "Middlewares registrados: Latency | RateLimit(%d req/%ds) | SecurityHeaders",
        rate_limit_max,
        int(rate_limit_window),
    )
