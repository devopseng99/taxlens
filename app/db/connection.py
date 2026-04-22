"""Dolt (MySQL-compatible) async connection pool via aiomysql."""

import os
import logging
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

# Connection pool singleton
_pool = None

# Dolt connection config from environment
DOLT_HOST = os.getenv("DOLT_HOST", "")
DOLT_PORT = int(os.getenv("DOLT_PORT", "3306"))
DOLT_DATABASE = os.getenv("DOLT_DATABASE", "taxlens")
DOLT_USER = os.getenv("DOLT_USER", "root")
DOLT_PASSWORD = os.getenv("DOLT_PASSWORD", "")

# Dolt is available only when DOLT_HOST is configured
DOLT_ENABLED = bool(DOLT_HOST)


async def init_pool():
    """Initialize the connection pool. Call once on app startup."""
    global _pool
    if not DOLT_ENABLED:
        logger.info("Dolt not configured (DOLT_HOST empty) — running in file-only mode")
        return

    import aiomysql
    _pool = await aiomysql.create_pool(
        host=DOLT_HOST,
        port=DOLT_PORT,
        user=DOLT_USER,
        password=DOLT_PASSWORD,
        db=DOLT_DATABASE,
        minsize=2,
        maxsize=5,
        autocommit=True,
        charset="utf8mb4",
    )
    logger.info(f"Dolt connection pool initialized: {DOLT_HOST}:{DOLT_PORT}/{DOLT_DATABASE}")


async def close_pool():
    """Close the connection pool. Call on app shutdown."""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("Dolt connection pool closed")


def get_pool():
    """Get the connection pool. Returns None if Dolt is not enabled."""
    return _pool


@asynccontextmanager
async def get_conn():
    """Acquire a connection from the pool as an async context manager."""
    if not _pool:
        raise RuntimeError("Dolt connection pool not initialized. Is DOLT_HOST set?")
    async with _pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def get_cursor(conn=None):
    """Acquire a cursor. If conn is None, acquires one from the pool."""
    if conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            yield cur
    else:
        import aiomysql
        async with get_conn() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                yield cur


async def execute(sql: str, args: tuple = (), conn=None) -> int:
    """Execute a single statement. Returns rows affected."""
    import aiomysql
    if conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return cur.rowcount
    else:
        async with get_conn() as c:
            async with c.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, args)
                return cur.rowcount


async def fetchone(sql: str, args: tuple = (), conn=None) -> dict[str, Any] | None:
    """Execute and fetch one row as a dict."""
    import aiomysql
    if conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return await cur.fetchone()
    else:
        async with get_conn() as c:
            async with c.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, args)
                return await cur.fetchone()


async def fetchall(sql: str, args: tuple = (), conn=None) -> list[dict[str, Any]]:
    """Execute and fetch all rows as dicts."""
    import aiomysql
    if conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return await cur.fetchall()
    else:
        async with get_conn() as c:
            async with c.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, args)
                return await cur.fetchall()
