"""Dolt version control helpers — commit, log, diff, history."""

import logging
from db.connection import get_conn, DOLT_ENABLED

logger = logging.getLogger(__name__)


async def dolt_commit(message: str) -> str | None:
    """Stage all changes and commit to Dolt. Returns commit hash or None."""
    if not DOLT_ENABLED:
        return None
    try:
        import aiomysql
        async with get_conn() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("CALL dolt_add('.')")
                await cur.execute("CALL dolt_commit('-m', %s, '--allow-empty')", (message,))
                row = await cur.fetchone()
                commit_hash = row.get("hash", "") if row else ""
                logger.info(f"Dolt commit: {commit_hash[:8]} — {message}")
                return commit_hash
    except Exception as e:
        logger.warning(f"Dolt commit failed: {e}")
        return None


async def dolt_log(limit: int = 20) -> list[dict]:
    """Get recent Dolt commit log."""
    if not DOLT_ENABLED:
        return []
    try:
        import aiomysql
        async with get_conn() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT commit_hash, committer, message, date "
                    "FROM dolt_log ORDER BY date DESC LIMIT %s",
                    (limit,),
                )
                rows = await cur.fetchall()
                return [
                    {
                        "hash": r["commit_hash"],
                        "committer": r["committer"],
                        "message": r["message"],
                        "date": str(r["date"]),
                    }
                    for r in rows
                ]
    except Exception as e:
        logger.warning(f"Dolt log failed: {e}")
        return []


async def dolt_diff(from_commit: str, to_commit: str, table: str) -> list[dict]:
    """Get row-level diff between two commits for a specific table."""
    if not DOLT_ENABLED:
        return []
    try:
        import aiomysql
        async with get_conn() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"SELECT * FROM dolt_diff('{from_commit}', '{to_commit}', '{table}')"
                )
                return await cur.fetchall()
    except Exception as e:
        logger.warning(f"Dolt diff failed: {e}")
        return []


async def dolt_history(table: str, pk_column: str, pk_value: str,
                       limit: int = 20) -> list[dict]:
    """Get version history for a specific row across commits."""
    if not DOLT_ENABLED:
        return []
    try:
        import aiomysql
        async with get_conn() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"SELECT *, dolt_diff_type FROM dolt_history_{table} "
                    f"WHERE {pk_column} = %s ORDER BY commit_date DESC LIMIT %s",
                    (pk_value, limit),
                )
                return await cur.fetchall()
    except Exception as e:
        logger.warning(f"Dolt history failed: {e}")
        return []


async def tenant_log(tenant_id: str, limit: int = 20) -> list[dict]:
    """Get Dolt log entries relevant to a specific tenant.
    Filters by commit message containing the tenant_id.
    """
    all_log = await dolt_log(limit * 3)  # Over-fetch to filter
    return [e for e in all_log if tenant_id in e.get("message", "")][:limit]
