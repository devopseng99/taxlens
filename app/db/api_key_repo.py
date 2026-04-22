"""API key repository — create, validate, revoke keys."""

import hashlib
import secrets
import uuid
import json
from datetime import datetime, timezone

from db.connection import execute, fetchone, fetchall


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a tlk_ prefixed API key."""
    return f"tlk_{secrets.token_urlsafe(32)}"


async def create_key(tenant_id: str, user_id: str | None = None,
                     name: str = None, scopes: list[str] | None = None) -> dict:
    """Create a new API key. Returns the key (shown once) and metadata."""
    key_id = uuid.uuid4().hex
    raw_key = generate_api_key()
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:12]  # "tlk_" + 8 chars
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    scopes_json = json.dumps(scopes or [])

    await execute(
        "INSERT INTO api_keys (id, tenant_id, user_id, key_hash, key_prefix, name, scopes, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s)",
        (key_id, tenant_id, user_id, key_hash, key_prefix, name, scopes_json, now),
    )
    return {
        "id": key_id,
        "key": raw_key,  # Only returned at creation time
        "key_prefix": key_prefix,
        "tenant_id": tenant_id,
        "name": name,
        "scopes": scopes or [],
        "created_at": now,
    }


async def validate_key(raw_key: str) -> dict | None:
    """Validate an API key. Returns key row with tenant info, or None if invalid."""
    key_hash = _hash_key(raw_key)
    row = await fetchone(
        "SELECT k.*, t.slug AS tenant_slug, t.status AS tenant_status "
        "FROM api_keys k JOIN tenants t ON k.tenant_id = t.id "
        "WHERE k.key_hash = %s AND k.status = 'active'",
        (key_hash,),
    )
    if row and row.get("tenant_status") == "active":
        # Update last_used_at (fire and forget)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        await execute("UPDATE api_keys SET last_used_at = %s WHERE id = %s", (now, row["id"]))
        return row
    return None


async def list_keys(tenant_id: str) -> list[dict]:
    """List all keys for a tenant (without hashes)."""
    rows = await fetchall(
        "SELECT id, tenant_id, user_id, key_prefix, name, scopes, status, created_at, last_used_at, expires_at "
        "FROM api_keys WHERE tenant_id = %s ORDER BY created_at DESC",
        (tenant_id,),
    )
    return rows


async def revoke_key(key_id: str) -> int:
    return await execute("UPDATE api_keys SET status = 'revoked' WHERE id = %s", (key_id,))
