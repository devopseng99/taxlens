"""flyway_schema_history table CRUD — tracks applied migrations."""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CREATE_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS flyway_schema_history (
    version INTEGER PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    installed_on TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    execution_time_ms INTEGER NOT NULL DEFAULT 0,
    success BOOLEAN NOT NULL DEFAULT TRUE
);
"""


async def ensure_history_table(conn) -> None:
    """Create flyway_schema_history if it doesn't exist."""
    await conn.execute(CREATE_HISTORY_TABLE)


async def get_applied(conn) -> list[dict]:
    """Get all applied migrations from history table."""
    rows = await conn.fetch(
        "SELECT version, description, checksum, installed_on, "
        "execution_time_ms, success FROM flyway_schema_history "
        "ORDER BY version"
    )
    return [dict(r) for r in rows]


async def record_migration(conn, version: int, description: str,
                           checksum: str, execution_time_ms: int,
                           success: bool) -> None:
    """Record a migration in the history table."""
    await conn.execute(
        "INSERT INTO flyway_schema_history "
        "(version, description, checksum, installed_on, execution_time_ms, success) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        version, description, checksum,
        datetime.now(timezone.utc), execution_time_ms, success,
    )
