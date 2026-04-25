"""OAuth 2.0 Token Endpoint — RFC 6749 + PKCE (RFC 7636).

Supports three grant types:
- client_credentials: MCP agents authenticate with client_id + client_secret
- authorization_code: Browser clients exchange auth code (with PKCE S256) for tokens
- refresh_token: Rotate refresh token, issue new access + refresh pair

All tokens are stored as SHA256 hashes in oauth_tokens.
"""

import hashlib
import json
import logging
import os
import secrets
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import JSONResponse

from db.postgrest_client import postgrest, DB_ENABLED

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

# Token TTLs (seconds)
ACCESS_TOKEN_TTL = int(os.getenv("OAUTH_ACCESS_TOKEN_TTL", "3600"))       # 1 hour
REFRESH_TOKEN_TTL = int(os.getenv("OAUTH_REFRESH_TOKEN_TTL", "2592000"))  # 30 days
AUTH_CODE_TTL = 600  # 10 minutes

# Valid scopes
VALID_SCOPES = {"compute", "drafts", "documents", "mcp", "plaid"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _generate_token(prefix: str = "tlt") -> str:
    return f"{prefix}_{secrets.token_urlsafe(48)}"


def _admin_token() -> str:
    return postgrest.mint_jwt("__admin__", role="app_admin")


async def _validate_client(client_id: str, client_secret: str) -> dict:
    """Validate client credentials. Returns client row or raises 401."""
    token = _admin_token()
    rows = await postgrest.get(
        "oauth_clients",
        {"client_id": f"eq.{client_id}", "status": "eq.active"},
        token=token,
    )
    if not rows:
        raise HTTPException(401, {"error": "invalid_client",
                                   "error_description": "Unknown or revoked client."})
    client = rows[0]
    if client["client_secret_hash"] != _hash(client_secret):
        raise HTTPException(401, {"error": "invalid_client",
                                   "error_description": "Bad client secret."})
    return client


async def _issue_tokens(client_id: str, tenant_id: str, scopes: list[str],
                        user_id: str | None = None) -> dict:
    """Create access + refresh tokens and persist hashes."""
    access_raw = _generate_token("tla")
    refresh_raw = _generate_token("tlr")
    now = datetime.now(timezone.utc).isoformat()
    token = _admin_token()

    # Persist access token
    await postgrest.create("oauth_tokens", {
        "token_hash": _hash(access_raw),
        "client_id": client_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "token_type": "access",
        "scopes": json.dumps(scopes),
        "expires_at": int(time.time()) + ACCESS_TOKEN_TTL,
        "created_at": now,
    }, token=token)

    # Persist refresh token
    await postgrest.create("oauth_tokens", {
        "token_hash": _hash(refresh_raw),
        "client_id": client_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "token_type": "refresh",
        "scopes": json.dumps(scopes),
        "expires_at": int(time.time()) + REFRESH_TOKEN_TTL,
        "created_at": now,
    }, token=token)

    return {
        "access_token": access_raw,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_TTL,
        "refresh_token": refresh_raw,
        "scope": " ".join(scopes),
    }


async def _handle_client_credentials(client_id: str, client_secret: str,
                                      scope: str | None) -> dict:
    """RFC 6749 §4.4 — Client Credentials Grant."""
    client = await _validate_client(client_id, client_secret)
    allowed_scopes = set(client.get("scopes") or [])
    requested = set(scope.split()) if scope else allowed_scopes
    granted = requested & allowed_scopes & VALID_SCOPES
    if not granted:
        raise HTTPException(400, {"error": "invalid_scope",
                                   "error_description": "No valid scopes granted."})
    return await _issue_tokens(client_id, client["tenant_id"], sorted(granted))


async def _handle_authorization_code(client_id: str, client_secret: str,
                                      code: str, redirect_uri: str | None,
                                      code_verifier: str | None) -> dict:
    """RFC 6749 §4.1 + RFC 7636 PKCE — Authorization Code Grant."""
    client = await _validate_client(client_id, client_secret)
    token = _admin_token()

    # Look up the auth code
    code_hash = _hash(code)
    rows = await postgrest.get(
        "oauth_tokens",
        {"token_hash": f"eq.{code_hash}", "token_type": "eq.code",
         "client_id": f"eq.{client_id}"},
        token=token,
    )
    if not rows:
        raise HTTPException(400, {"error": "invalid_grant",
                                   "error_description": "Invalid or expired authorization code."})
    code_row = rows[0]

    # Check expiration
    if code_row.get("expires_at") and code_row["expires_at"] < int(time.time()):
        await postgrest.delete("oauth_tokens", {"token_hash": f"eq.{code_hash}"}, token=token)
        raise HTTPException(400, {"error": "invalid_grant",
                                   "error_description": "Authorization code expired."})

    # Verify redirect_uri matches
    if code_row.get("redirect_uri") and redirect_uri != code_row["redirect_uri"]:
        raise HTTPException(400, {"error": "invalid_grant",
                                   "error_description": "redirect_uri mismatch."})

    # Verify PKCE code_verifier (S256)
    if code_row.get("code_challenge"):
        if not code_verifier:
            raise HTTPException(400, {"error": "invalid_grant",
                                       "error_description": "code_verifier required for PKCE."})
        digest = hashlib.sha256(code_verifier.encode()).digest()
        challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
        if challenge != code_row["code_challenge"]:
            raise HTTPException(400, {"error": "invalid_grant",
                                       "error_description": "PKCE verification failed."})

    # Consume the code (delete it)
    await postgrest.delete("oauth_tokens", {"token_hash": f"eq.{code_hash}"}, token=token)

    scopes = code_row.get("scopes") or client.get("scopes") or []
    if isinstance(scopes, str):
        scopes = json.loads(scopes)

    return await _issue_tokens(client_id, code_row["tenant_id"], sorted(scopes),
                               user_id=code_row.get("user_id"))


async def _handle_refresh_token(client_id: str, client_secret: str,
                                 refresh_token: str, scope: str | None) -> dict:
    """RFC 6749 §6 — Refresh Token Grant with rotation."""
    client = await _validate_client(client_id, client_secret)
    token = _admin_token()

    refresh_hash = _hash(refresh_token)
    rows = await postgrest.get(
        "oauth_tokens",
        {"token_hash": f"eq.{refresh_hash}", "token_type": "eq.refresh",
         "client_id": f"eq.{client_id}"},
        token=token,
    )
    if not rows:
        raise HTTPException(400, {"error": "invalid_grant",
                                   "error_description": "Invalid refresh token."})
    refresh_row = rows[0]

    # Check expiration
    if refresh_row.get("expires_at") and refresh_row["expires_at"] < int(time.time()):
        await postgrest.delete("oauth_tokens", {"token_hash": f"eq.{refresh_hash}"}, token=token)
        raise HTTPException(400, {"error": "invalid_grant",
                                   "error_description": "Refresh token expired."})

    # Rotation: delete old refresh token
    await postgrest.delete("oauth_tokens", {"token_hash": f"eq.{refresh_hash}"}, token=token)

    # Scope narrowing allowed; widening forbidden
    allowed_scopes = set(refresh_row.get("scopes") or [])
    if scope:
        requested = set(scope.split())
        granted = requested & allowed_scopes
    else:
        granted = allowed_scopes

    if not granted:
        raise HTTPException(400, {"error": "invalid_scope",
                                   "error_description": "No valid scopes."})

    return await _issue_tokens(client_id, refresh_row["tenant_id"],
                               sorted(granted), user_id=refresh_row.get("user_id"))


# --- Authorization Code Creation (admin use) ---

async def create_authorization_code(client_id: str, tenant_id: str,
                                     scopes: list[str],
                                     redirect_uri: str | None = None,
                                     code_challenge: str | None = None,
                                     code_challenge_method: str | None = None,
                                     user_id: str | None = None) -> str:
    """Create an authorization code for the authorization_code flow.

    Called internally by the admin/authorization UI (not directly by clients).
    Returns the raw code string.
    """
    if code_challenge_method and code_challenge_method != "S256":
        raise ValueError("Only S256 code_challenge_method is supported.")

    code = _generate_token("tlc")
    token = _admin_token()
    now = datetime.now(timezone.utc).isoformat()

    await postgrest.create("oauth_tokens", {
        "token_hash": _hash(code),
        "client_id": client_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "token_type": "code",
        "scopes": json.dumps(scopes),
        "expires_at": int(time.time()) + AUTH_CODE_TTL,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "redirect_uri": redirect_uri,
        "created_at": now,
    }, token=token)

    return code


# --- Token Cleanup ---

async def cleanup_expired_tokens() -> int:
    """Delete expired tokens. Called by scheduled task."""
    token = _admin_token()
    now = int(time.time())
    count = await postgrest.delete(
        "oauth_tokens",
        {"expires_at": f"lt.{now}"},
        token=token,
    )
    if count:
        logger.info("Cleaned up %d expired OAuth tokens", count)
    return count


# --- Token Endpoint ---

@router.post("/oauth/token")
async def token_endpoint(
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(default=""),
    client_secret: str = Form(default=""),
    code: str = Form(default=""),
    redirect_uri: str = Form(default=""),
    code_verifier: str = Form(default=""),
    refresh_token: str = Form(default=""),
    scope: str = Form(default=""),
):
    """OAuth 2.0 Token Endpoint (RFC 6749).

    Accepts application/x-www-form-urlencoded as required by the spec.
    Supports: client_credentials, authorization_code, refresh_token.
    """
    if not DB_ENABLED:
        raise HTTPException(503, {"error": "server_error",
                                   "error_description": "Database not available."})

    if not client_id or not client_secret:
        raise HTTPException(401, {"error": "invalid_client",
                                   "error_description": "client_id and client_secret required."})

    if grant_type == "client_credentials":
        result = await _handle_client_credentials(
            client_id, client_secret, scope or None)

    elif grant_type == "authorization_code":
        if not code:
            raise HTTPException(400, {"error": "invalid_request",
                                       "error_description": "code is required."})
        result = await _handle_authorization_code(
            client_id, client_secret, code,
            redirect_uri or None, code_verifier or None)

    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(400, {"error": "invalid_request",
                                       "error_description": "refresh_token is required."})
        result = await _handle_refresh_token(
            client_id, client_secret, refresh_token, scope or None)

    else:
        raise HTTPException(400, {"error": "unsupported_grant_type",
                                   "error_description": f"Grant type '{grant_type}' not supported."})

    return JSONResponse(result, headers={
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
    })


# --- Token Introspection (for scope checks) ---

async def validate_token_scopes(token_raw: str, required_scope: str) -> bool:
    """Check if a Bearer token has the required scope.

    Called by route-level scope enforcement (not an endpoint).
    Returns True if the token has the scope, False otherwise.
    """
    token_hash = _hash(token_raw)
    admin = _admin_token()
    rows = await postgrest.get(
        "oauth_tokens",
        {"token_hash": f"eq.{token_hash}", "token_type": "eq.access"},
        token=admin,
    )
    if not rows:
        return False
    row = rows[0]
    if row.get("expires_at") and row["expires_at"] < int(time.time()):
        return False
    scopes = row.get("scopes") or []
    if isinstance(scopes, str):
        scopes = json.loads(scopes)
    return required_scope in scopes
