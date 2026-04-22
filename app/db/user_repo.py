"""User repository — CRUD for the users table."""

import uuid
from datetime import datetime, timezone

from db.connection import execute, fetchone, fetchall


async def create_user(tenant_id: str, username: str, email: str = None,
                      role: str = "member") -> dict:
    user_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await execute(
        "INSERT INTO users (id, tenant_id, username, email, role, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, tenant_id, username, email, role, now),
    )
    return {"id": user_id, "tenant_id": tenant_id, "username": username,
            "email": email, "role": role, "created_at": now}


async def get_user(user_id: str) -> dict | None:
    return await fetchone("SELECT * FROM users WHERE id = %s", (user_id,))


async def get_by_username(tenant_id: str, username: str) -> dict | None:
    return await fetchone(
        "SELECT * FROM users WHERE tenant_id = %s AND username = %s",
        (tenant_id, username),
    )


async def list_users(tenant_id: str) -> list[dict]:
    return await fetchall(
        "SELECT * FROM users WHERE tenant_id = %s ORDER BY created_at",
        (tenant_id,),
    )


async def delete_user(user_id: str) -> int:
    return await execute("DELETE FROM users WHERE id = %s", (user_id,))
