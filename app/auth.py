"""TaxLens API authentication — multi-tenant with Dolt-backed keys + env-var fallback.

When Dolt is configured (DOLT_HOST set):
  - API keys validated against the api_keys table via TenantContextMiddleware
  - Tenant context available in request.state.tenant_id

When Dolt is NOT configured (dev/legacy mode):
  - Falls back to TAXLENS_API_KEYS env var (comma-separated)
  - Auth disabled entirely when no keys are configured

Usage in routes:
    from auth import require_auth
    @app.get("/protected")
    async def protected(user: str = Depends(require_auth)):
        ...
"""

import os
import hashlib
import secrets
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from db.connection import DOLT_ENABLED

# API key header name
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# --- Legacy env-var fallback ---
_raw_keys = os.getenv("TAXLENS_API_KEYS", "")
VALID_KEYS: set[str] = {k.strip() for k in _raw_keys.split(",") if k.strip()}

# Auth enabled when either Dolt or legacy keys exist
AUTH_ENABLED = DOLT_ENABLED or len(VALID_KEYS) > 0

# Pre-hash valid keys for constant-time comparison (legacy mode)
_VALID_HASHES = {hashlib.sha256(k.encode()).hexdigest() for k in VALID_KEYS}

# Admin key from env
ADMIN_KEY = os.getenv("TAXLENS_ADMIN_KEY", "")


async def require_auth(request: Request, api_key: str = Security(API_KEY_HEADER)) -> str:
    """Dependency that validates the API key.

    Returns the key (or "anonymous" if auth is disabled).
    Raises 401/403 if auth is enabled and key is missing/invalid.
    """
    # If Dolt enabled, TenantContextMiddleware already validated
    if DOLT_ENABLED:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id and tenant_id not in (None, "__admin__"):
            return api_key or "authenticated"
        if tenant_id == "__admin__":
            return "admin"
        if not api_key:
            raise HTTPException(401, "Missing API key. Provide X-API-Key header.")
        raise HTTPException(403, "Invalid API key.")

    # Legacy mode: env-var based auth
    if not AUTH_ENABLED:
        return "anonymous"

    if not api_key:
        raise HTTPException(401, "Missing API key. Provide X-API-Key header.")

    if hashlib.sha256(api_key.encode()).hexdigest() not in _VALID_HASHES:
        raise HTTPException(403, "Invalid API key.")

    return api_key


async def require_admin(request: Request) -> str:
    """Dependency for admin-only endpoints. Validates X-Admin-Key header."""
    if not ADMIN_KEY:
        raise HTTPException(503, "Admin API not configured. Set TAXLENS_ADMIN_KEY.")
    admin_key = request.headers.get("X-Admin-Key", "")
    if not admin_key:
        raise HTTPException(401, "Missing admin key. Provide X-Admin-Key header.")
    if admin_key != ADMIN_KEY:
        raise HTTPException(403, "Invalid admin key.")
    return "admin"


def get_tenant_id(request: Request) -> str:
    """Get tenant_id from request state. Returns 'default' in legacy mode."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or tenant_id == "__admin__":
        if not DOLT_ENABLED:
            return "default"
        raise HTTPException(401, "Tenant context not established.")
    return tenant_id


def generate_api_key() -> str:
    """Generate a secure random API key (for admin tooling)."""
    return f"tlk_{secrets.token_urlsafe(32)}"
