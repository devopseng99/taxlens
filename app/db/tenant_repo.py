"""Tenant repository — CRUD for the tenants table."""

import uuid
from datetime import datetime, timezone

from db.connection import execute, fetchone, fetchall


async def create_tenant(name: str, slug: str, plan: str = "starter") -> dict:
    """Create a new tenant. Returns the tenant dict."""
    tenant_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await execute(
        "INSERT INTO tenants (id, name, slug, plan_tier, status, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, 'active', %s, %s)",
        (tenant_id, name, slug, plan, now, now),
    )
    return {"id": tenant_id, "name": name, "slug": slug, "plan": plan,
            "status": "active", "created_at": now, "updated_at": now}


async def get_tenant(tenant_id: str) -> dict | None:
    return await fetchone("SELECT * FROM tenants WHERE id = %s", (tenant_id,))


async def get_tenant_by_slug(slug: str) -> dict | None:
    return await fetchone("SELECT * FROM tenants WHERE slug = %s", (slug,))


async def list_tenants(status: str | None = None) -> list[dict]:
    if status:
        return await fetchall("SELECT * FROM tenants WHERE status = %s ORDER BY created_at DESC", (status,))
    return await fetchall("SELECT * FROM tenants ORDER BY created_at DESC")


async def update_tenant(tenant_id: str, **fields) -> int:
    """Update tenant fields. Pass only the fields to change."""
    if not fields:
        return 0
    fields["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [tenant_id]
    return await execute(f"UPDATE tenants SET {set_clause} WHERE id = %s", tuple(values))


async def get_tenant_stats(tenant_id: str) -> dict:
    """Get aggregate counts for a tenant."""
    users = await fetchone("SELECT COUNT(*) AS cnt FROM users WHERE tenant_id = %s", (tenant_id,))
    drafts = await fetchone("SELECT COUNT(*) AS cnt FROM tax_drafts WHERE tenant_id = %s", (tenant_id,))
    docs = await fetchone("SELECT COUNT(*) AS cnt FROM documents WHERE tenant_id = %s", (tenant_id,))
    plaid = await fetchone("SELECT COUNT(*) AS cnt FROM plaid_items WHERE tenant_id = %s", (tenant_id,))
    return {
        "users": users["cnt"] if users else 0,
        "drafts": drafts["cnt"] if drafts else 0,
        "documents": docs["cnt"] if docs else 0,
        "plaid_items": plaid["cnt"] if plaid else 0,
    }
