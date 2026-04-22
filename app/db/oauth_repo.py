"""OAuth client and token repository — for MCP OAuth 2.0 server."""

import hashlib
import secrets
import json
from datetime import datetime, timezone

from db.connection import execute, fetchone, fetchall


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def register_client(tenant_id: str, client_name: str,
                          redirect_uris: list[str],
                          grant_types: list[str] = None,
                          scopes: list[str] = None) -> dict:
    """Register a new OAuth client. Returns client_id + client_secret (shown once)."""
    import uuid
    client_id = uuid.uuid4().hex
    client_secret = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    await execute(
        "INSERT INTO oauth_clients "
        "(client_id, tenant_id, client_secret_hash, client_name, redirect_uris, "
        "grant_types, scopes, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s)",
        (client_id, tenant_id, _hash(client_secret), client_name,
         json.dumps(redirect_uris),
         json.dumps(grant_types or ["authorization_code", "refresh_token"]),
         json.dumps(scopes or ["compute", "drafts", "documents"]),
         now),
    )
    return {
        "client_id": client_id,
        "client_secret": client_secret,  # Only returned at creation
        "tenant_id": tenant_id,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "scopes": scopes or ["compute", "drafts", "documents"],
        "created_at": now,
    }


async def get_client(client_id: str) -> dict | None:
    return await fetchone(
        "SELECT * FROM oauth_clients WHERE client_id = %s AND status = 'active'",
        (client_id,),
    )


async def validate_client_secret(client_id: str, client_secret: str) -> dict | None:
    """Validate client credentials. Returns client row or None."""
    row = await get_client(client_id)
    if row and row["client_secret_hash"] == _hash(client_secret):
        return row
    return None


async def list_clients(tenant_id: str) -> list[dict]:
    return await fetchall(
        "SELECT client_id, tenant_id, client_name, redirect_uris, grant_types, "
        "scopes, status, created_at "
        "FROM oauth_clients WHERE tenant_id = %s ORDER BY created_at DESC",
        (tenant_id,),
    )


async def revoke_client(client_id: str) -> int:
    return await execute(
        "UPDATE oauth_clients SET status = 'revoked' WHERE client_id = %s",
        (client_id,),
    )


async def rotate_client_secret(client_id: str) -> dict | None:
    """Generate a new secret for an existing client. Returns new secret (shown once)."""
    new_secret = secrets.token_urlsafe(48)
    rows = await execute(
        "UPDATE oauth_clients SET client_secret_hash = %s WHERE client_id = %s AND status = 'active'",
        (_hash(new_secret), client_id),
    )
    if rows:
        return {"client_id": client_id, "client_secret": new_secret}
    return None


# --- Token operations ---

async def save_token(token_hash: str, client_id: str, tenant_id: str,
                     token_type: str, scopes: list[str] = None,
                     expires_at: int = None, user_id: str = None,
                     code_challenge: str = None,
                     code_challenge_method: str = None,
                     redirect_uri: str = None) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await execute(
        "INSERT INTO oauth_tokens "
        "(token_hash, client_id, tenant_id, user_id, token_type, scopes, "
        "expires_at, code_challenge, code_challenge_method, redirect_uri, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (token_hash, client_id, tenant_id, user_id, token_type,
         json.dumps(scopes or []), expires_at, code_challenge,
         code_challenge_method, redirect_uri, now),
    )


async def load_token(token_hash: str, token_type: str = None) -> dict | None:
    if token_type:
        return await fetchone(
            "SELECT * FROM oauth_tokens WHERE token_hash = %s AND token_type = %s",
            (token_hash, token_type),
        )
    return await fetchone(
        "SELECT * FROM oauth_tokens WHERE token_hash = %s",
        (token_hash,),
    )


async def revoke_token(token_hash: str) -> int:
    return await execute("DELETE FROM oauth_tokens WHERE token_hash = %s", (token_hash,))


async def revoke_all_tokens(client_id: str) -> int:
    return await execute("DELETE FROM oauth_tokens WHERE client_id = %s", (client_id,))
