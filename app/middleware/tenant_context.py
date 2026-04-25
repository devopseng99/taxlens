"""Multi-tenant context middleware.

Extracts tenant_id from the request authentication (API key or Bearer token)
and injects it into request.state for downstream handlers.

Uses an in-memory LRU cache for API key validation to avoid repeated
PostgREST roundtrips for the same key.

Uses pure ASGI middleware (not BaseHTTPMiddleware) to avoid deadlocks with
nested async httpx calls in the middleware chain.

Paths that skip tenant context: /health, /docs, /openapi.json, /mcp (MCP has its own auth).
"""

import hashlib
import logging
import time
from collections import OrderedDict
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from db.postgrest_client import postgrest, DB_ENABLED

logger = logging.getLogger(__name__)

# Paths that don't require tenant context
_SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/mcp", "/mcp/", "/metrics",
               "/oauth/token"}

# --- Auth Cache ---
_AUTH_CACHE_MAX = 256
_AUTH_CACHE_TTL = 60  # seconds
_auth_cache: OrderedDict[str, tuple[dict, float]] = OrderedDict()


def _cache_get(key_hash: str) -> dict | None:
    """Get cached auth result if not expired."""
    entry = _auth_cache.get(key_hash)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > _AUTH_CACHE_TTL:
        _auth_cache.pop(key_hash, None)
        return None
    _auth_cache.move_to_end(key_hash)
    return result


def _cache_put(key_hash: str, result: dict) -> None:
    """Cache an auth result with TTL."""
    _auth_cache[key_hash] = (result, time.monotonic())
    if len(_auth_cache) > _AUTH_CACHE_MAX:
        _auth_cache.popitem(last=False)


def _set_state(request: Request, tenant_id, tenant_slug="", user_id=None, db_token=None,
               username=None, role=None):
    request.state.tenant_id = tenant_id
    request.state.tenant_slug = tenant_slug
    request.state.user_id = user_id
    request.state.db_token = db_token
    request.state.username = username
    request.state.role = role


class TenantContextMiddleware:
    """Pure ASGI middleware — avoids BaseHTTPMiddleware deadlocks with async DB calls."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        # Skip tenant context for health/docs/MCP
        if path in _SKIP_PATHS or path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/postgrest-openapi") or path.startswith("/content/"):
            _set_state(request, None)
            await self.app(scope, receive, send)
            return

        # If DB is not enabled, run in legacy single-tenant mode
        if not DB_ENABLED:
            _set_state(request, "default", "default")
            await self.app(scope, receive, send)
            return

        # Extract API key from header
        api_key = request.headers.get("X-API-Key", "")

        if api_key:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()

            # Check cache first
            cached = _cache_get(key_hash)
            if cached:
                _set_state(
                    request, cached["tenant_id"],
                    cached.get("tenant_slug", ""),
                    cached.get("user_id"),
                    postgrest.mint_jwt(cached["tenant_id"], cached.get("user_id")),
                    cached.get("username"),
                    cached.get("role"),
                )
                await self.app(scope, receive, send)
                return

            # Validate via PostgREST RPC (anonymous, no JWT needed)
            try:
                rows = await postgrest.rpc("validate_api_key", {"p_key_hash": key_hash})
                if rows:
                    row = rows[0]
                    _cache_put(key_hash, row)
                    _set_state(
                        request, row["tenant_id"],
                        row.get("tenant_slug", ""),
                        row.get("user_id"),
                        postgrest.mint_jwt(row["tenant_id"], row.get("user_id")),
                        row.get("username"),
                        row.get("role"),
                    )
                    await self.app(scope, receive, send)
                    return
            except Exception as e:
                logger.warning("API key validation failed: %s", e)

        # Check Bearer token (OAuth access token)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            try:
                admin_token = postgrest.mint_jwt("__admin__", role="app_admin")
                rows = await postgrest.get(
                    "oauth_tokens",
                    {"token_hash": f"eq.{token_hash}", "token_type": "eq.access"},
                    token=admin_token,
                )
                if rows:
                    token_row = rows[0]
                    if token_row.get("expires_at") and token_row["expires_at"] < int(time.time()):
                        resp = JSONResponse({"detail": "Token expired"}, status_code=401)
                        await resp(scope, receive, send)
                        return
                    _set_state(
                        request, token_row["tenant_id"], "",
                        token_row.get("user_id"),
                        postgrest.mint_jwt(token_row["tenant_id"], token_row.get("user_id")),
                    )
                    await self.app(scope, receive, send)
                    return
            except Exception as e:
                logger.warning("Bearer token validation failed: %s", e)

        # Admin key bypass — admin endpoints handle their own auth
        admin_key = request.headers.get("X-Admin-Key", "")
        if admin_key and path.startswith("/admin"):
            _set_state(
                request, "__admin__", "__admin__", None,
                postgrest.mint_jwt("__admin__", role="app_admin"),
            )
            await self.app(scope, receive, send)
            return

        # Billing webhook + plans + free signup — no auth needed
        if (path.startswith("/billing/webhook") or path == "/billing/plans"
                or path == "/billing/onboarding/free"):
            _set_state(request, None)
            await self.app(scope, receive, send)
            return

        # No valid auth found — let individual route handlers decide
        _set_state(request, None)
        await self.app(scope, receive, send)
