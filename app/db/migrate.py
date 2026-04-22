"""Schema migration — runs on app startup to ensure all tables exist."""

import logging
from pathlib import Path

from db.connection import get_conn, DOLT_ENABLED

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


async def run_migrations():
    """Execute schema.sql statements idempotently, then dolt_commit."""
    if not DOLT_ENABLED:
        logger.info("Dolt not enabled — skipping migrations")
        return

    sql_text = SCHEMA_FILE.read_text()

    # Strip comment lines, then split on semicolons
    lines = [l for l in sql_text.splitlines() if not l.strip().startswith("--")]
    clean_sql = "\n".join(lines)
    statements = [s.strip() for s in clean_sql.split(";") if s.strip()]

    async with get_conn() as conn:
        import aiomysql
        async with conn.cursor(aiomysql.DictCursor) as cur:
            for stmt in statements:
                try:
                    await cur.execute(stmt)
                except Exception as e:
                    # Log but continue — IF NOT EXISTS makes most errors benign
                    logger.warning(f"Migration statement warning: {e}")

            # Commit schema changes to Dolt version control
            try:
                await cur.execute("CALL dolt_add('.')")
                await cur.execute("CALL dolt_commit('-m', 'schema migration', '--allow-empty')")
                logger.info("Schema migration committed to Dolt")
            except Exception as e:
                # If nothing changed, dolt_commit may error — that's fine
                logger.debug(f"Dolt commit after migration: {e}")

    logger.info("Database migrations complete")
