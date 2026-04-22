#!/usr/bin/env python3
"""Usage aggregation script — aggregate usage_events → usage_daily, prune old events.

Run as K8s CronJob (hourly) or manually:
    python scripts/aggregate_usage.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

# Add app directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aggregate_usage")


async def aggregate():
    """Aggregate usage_events into usage_daily and prune old events."""
    from db.connection import init_pool, close_pool, get_conn, DOLT_ENABLED

    if not DOLT_ENABLED:
        logger.info("Dolt not enabled — nothing to aggregate")
        return

    await init_pool()

    try:
        import aiomysql
        import uuid
        async with get_conn() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # 1. Aggregate events from the last 2 hours into daily counts
                cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
                logger.info("Aggregating events since %s", cutoff)

                await cur.execute(
                    "SELECT tenant_id, event_type, DATE(created_at) as event_date, "
                    "COUNT(*) as cnt "
                    "FROM usage_events WHERE created_at >= %s "
                    "GROUP BY tenant_id, event_type, DATE(created_at)",
                    (cutoff,),
                )
                rows = await cur.fetchall()
                logger.info("Found %d aggregation groups", len(rows))

                now = datetime.now(timezone.utc)
                for row in rows:
                    # Upsert into usage_daily
                    await cur.execute(
                        "SELECT id, event_count FROM usage_daily "
                        "WHERE tenant_id = %s AND event_type = %s AND event_date = %s",
                        (row["tenant_id"], row["event_type"], row["event_date"]),
                    )
                    existing = await cur.fetchone()

                    if existing:
                        # Update count to match (idempotent — re-count from events)
                        await cur.execute(
                            "SELECT COUNT(*) as cnt FROM usage_events "
                            "WHERE tenant_id = %s AND event_type = %s "
                            "AND DATE(created_at) = %s",
                            (row["tenant_id"], row["event_type"], row["event_date"]),
                        )
                        full_count = (await cur.fetchone())["cnt"]
                        await cur.execute(
                            "UPDATE usage_daily SET event_count = %s, updated_at = %s "
                            "WHERE id = %s",
                            (full_count, now, existing["id"]),
                        )
                    else:
                        await cur.execute(
                            "INSERT INTO usage_daily "
                            "(id, tenant_id, event_type, event_date, event_count, updated_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (uuid.uuid4().hex, row["tenant_id"], row["event_type"],
                             row["event_date"], row["cnt"], now),
                        )

                logger.info("Aggregated %d groups into usage_daily", len(rows))

                # 2. Prune events older than 30 days
                prune_before = datetime.now(timezone.utc) - timedelta(days=30)
                await cur.execute(
                    "DELETE FROM usage_events WHERE created_at < %s",
                    (prune_before,),
                )
                pruned = cur.rowcount
                if pruned:
                    logger.info("Pruned %d events older than 30 days", pruned)

                # 3. Commit
                await cur.execute("CALL dolt_add('.')")
                await cur.execute("CALL dolt_commit('-m', %s, '--allow-empty')",
                                  ("cron: usage aggregation",))

    except Exception as e:
        logger.error("Aggregation failed: %s", e)
        raise
    finally:
        await close_pool()

    logger.info("Usage aggregation complete")


if __name__ == "__main__":
    asyncio.run(aggregate())
