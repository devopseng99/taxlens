"""Plaid item repository — CRUD for the plaid_items table."""

from datetime import datetime, timezone

from db.connection import execute, fetchone, fetchall


async def save_item(item_id: str, tenant_id: str, username: str,
                    institution_name: str, encrypted_token: str,
                    environment: str = "sandbox") -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await execute(
        "INSERT INTO plaid_items "
        "(item_id, tenant_id, username, institution_name, encrypted_token, "
        "environment, has_sync, connected_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, 0, %s)",
        (item_id, tenant_id, username, institution_name, encrypted_token,
         environment, now),
    )
    return {
        "item_id": item_id, "tenant_id": tenant_id, "username": username,
        "institution_name": institution_name, "environment": environment,
        "has_sync": False, "connected_at": now,
    }


async def get_item(tenant_id: str, item_id: str) -> dict | None:
    return await fetchone(
        "SELECT * FROM plaid_items WHERE item_id = %s AND tenant_id = %s",
        (item_id, tenant_id),
    )


async def list_items(tenant_id: str, username: str | None = None) -> list[dict]:
    if username:
        return await fetchall(
            "SELECT item_id, tenant_id, username, institution_name, environment, "
            "has_sync, connected_at, last_synced_at "
            "FROM plaid_items WHERE tenant_id = %s AND username = %s ORDER BY connected_at DESC",
            (tenant_id, username),
        )
    return await fetchall(
        "SELECT item_id, tenant_id, username, institution_name, environment, "
        "has_sync, connected_at, last_synced_at "
        "FROM plaid_items WHERE tenant_id = %s ORDER BY connected_at DESC",
        (tenant_id,),
    )


async def update_sync_status(tenant_id: str, item_id: str) -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return await execute(
        "UPDATE plaid_items SET has_sync = 1, last_synced_at = %s "
        "WHERE item_id = %s AND tenant_id = %s",
        (now, item_id, tenant_id),
    )


async def delete_item(tenant_id: str, item_id: str) -> int:
    return await execute(
        "DELETE FROM plaid_items WHERE item_id = %s AND tenant_id = %s",
        (item_id, tenant_id),
    )
