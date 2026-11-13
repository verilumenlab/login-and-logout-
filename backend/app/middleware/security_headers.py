"""
Enterprise Security Headers Middleware (Phase 14)
Enforces HTTP security headers across all responses to mitigate XSS, Clickjacking,
MIME-confusion, and protocol downgrade attacks.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Strict Content Security Policy
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' http://localhost:8000 ws://localhost:8000 http://localhost:3000; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none';"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # 1. Anti-Clickjacking: Disallow embedding in iframes
        response.headers["X-Frame-Options"] = "DENY"

        # 2. Anti-MIME-confusion: Prevent browsers from MIME-sniffing away from declared content-type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 3. Content Security Policy
        response.headers["Content-Security-Policy"] = CSP_POLICY

        # 4. HTTP Strict Transport Security (HSTS) - 1 year with subdomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # 5. Referrer Policy: Leak only origin on cross-origin requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 6. Permissions Policy: Restrict dangerous browser features
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=(), payment=()"

        # 7. XSS Filter (legacy protection for older user agents)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 8. Suppress Server banner to prevent server fingerprinting
        if "server" in response.headers:
            del response.headers["server"]
        response.headers["Server"] = "Enterprise-Secure-Gateway"

        return response

