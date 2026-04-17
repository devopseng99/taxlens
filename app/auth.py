"""TaxLens API authentication — API key validation.

Keys are configured via environment variable TAXLENS_API_KEYS (comma-separated).
When no keys are configured, auth is DISABLED (open access for dev).

Usage in routes:
    from auth import require_auth
    @app.get("/protected")
    async def protected(user: str = Depends(require_auth)):
        ...
"""

import os
import hashlib
import secrets
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

# API key header name
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Load valid API keys from env (comma-separated)
_raw_keys = os.getenv("TAXLENS_API_KEYS", "")
VALID_KEYS: set[str] = {k.strip() for k in _raw_keys.split(",") if k.strip()}

# Auth enabled only when keys are configured
AUTH_ENABLED = len(VALID_KEYS) > 0


def _hash_key(key: str) -> str:
    """SHA-256 hash for constant-time comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


# Pre-hash valid keys for constant-time comparison
_VALID_HASHES = {_hash_key(k) for k in VALID_KEYS}


async def require_auth(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Dependency that validates the API key.

    Returns the key (or "anonymous" if auth is disabled).
    Raises 401 if auth is enabled and key is missing/invalid.
    """
    if not AUTH_ENABLED:
        return "anonymous"

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
        )

    # Constant-time comparison via hash
    if _hash_key(api_key) not in _VALID_HASHES:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key.",
        )

    return api_key


def generate_api_key() -> str:
    """Generate a secure random API key (for admin tooling)."""
    return f"tlk_{secrets.token_urlsafe(32)}"
