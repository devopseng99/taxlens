"""Multi-tenant context middleware.

Extracts tenant_id from the request authentication (API key or Bearer token)
and injects it into request.state for downstream handlers.

Paths that skip tenant context: /health, /docs, /openapi.json, /mcp (MCP has its own auth).
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from db.connection import DOLT_ENABLED

logger = logging.getLogger(__name__)

# Paths that don't require tenant context
_SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/mcp", "/mcp/"}


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip tenant context for health/docs/MCP (MCP uses its own OAuth)
        if path in _SKIP_PATHS or path.startswith("/docs") or path.startswith("/openapi"):
            request.state.tenant_id = None
            request.state.tenant_slug = None
            request.state.user_id = None
            return await call_next(request)

        # If Dolt is not enabled, run in legacy single-tenant mode
        if not DOLT_ENABLED:
            request.state.tenant_id = "default"
            request.state.tenant_slug = "default"
            request.state.user_id = None
            return await call_next(request)

        # Extract API key from header
        api_key = request.headers.get("X-API-Key", "")

        if api_key:
            from db.api_key_repo import validate_key
            key_row = await validate_key(api_key)
            if key_row:
                request.state.tenant_id = key_row["tenant_id"]
                request.state.tenant_slug = key_row.get("tenant_slug", "")
                request.state.user_id = key_row.get("user_id")
                return await call_next(request)

        # Check Bearer token (OAuth access token)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            import hashlib
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            from db.oauth_repo import load_token
            token_row = await load_token(token_hash, token_type="access")
            if token_row:
                import time
                if token_row.get("expires_at") and token_row["expires_at"] < int(time.time()):
                    return JSONResponse({"detail": "Token expired"}, status_code=401)
                request.state.tenant_id = token_row["tenant_id"]
                request.state.tenant_slug = ""
                request.state.user_id = token_row.get("user_id")
                return await call_next(request)

        # Admin key bypass — admin endpoints handle their own auth
        admin_key = request.headers.get("X-Admin-Key", "")
        if admin_key and path.startswith("/admin"):
            request.state.tenant_id = "__admin__"
            request.state.tenant_slug = "__admin__"
            request.state.user_id = None
            return await call_next(request)

        # No valid auth found — let individual route handlers decide
        # (some routes like /health don't need auth)
        request.state.tenant_id = None
        request.state.tenant_slug = None
        request.state.user_id = None
        return await call_next(request)
