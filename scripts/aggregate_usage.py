#!/usr/bin/env python3
"""Usage aggregation script — aggregate usage_events → usage_daily, prune old events.

Uses PostgREST HTTP API (no direct DB connection needed).

Run as K8s CronJob (hourly) or manually:
    python scripts/aggregate_usage.py
"""

import asyncio
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aggregate_usage")

POSTGREST_URL = os.getenv("POSTGREST_URL", "")
JWT_SECRET = os.getenv("DB_JWT_SECRET", "")


def mint_admin_jwt() -> str:
    import jwt
    return jwt.encode(
        {"role": "app_admin", "tenant_id": "__admin__", "exp": int(time.time()) + 300},
        JWT_SECRET, algorithm="HS256",
    )


async def aggregate():
    if not POSTGREST_URL or not JWT_SECRET:
        logger.warning("POSTGREST_URL or DB_JWT_SECRET not set — skipping aggregation")
        return

    import httpx

    token = mint_admin_jwt()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(base_url=POSTGREST_URL, timeout=30.0) as client:
        # 1. Get events from last 2 hours grouped by tenant/type/date
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        resp = await client.get(
            "/usage_events",
            params={"created_at": f"gte.{cutoff}", "select": "tenant_id,event_type,created_at"},
            headers=headers,
        )
        resp.raise_for_status()
        events = resp.json()

        if not events:
            return

        # Group by tenant_id + event_type + date
        groups: dict[tuple, int] = {}
        for e in events:
            date_str = e["created_at"][:10]  # YYYY-MM-DD
            key = (e["tenant_id"], e["event_type"], date_str)
            groups[key] = groups.get(key, 0) + 1

        logger.warning("Aggregating %d groups from %d events", len(groups), len(events))

        # 2. Upsert into usage_daily
        now = datetime.now(timezone.utc).isoformat()
        for (tenant_id, event_type, event_date), count in groups.items():
            # Check existing
            resp = await client.get(
                "/usage_daily",
                params={
                    "tenant_id": f"eq.{tenant_id}",
                    "event_type": f"eq.{event_type}",
                    "event_date": f"eq.{event_date}",
                },
                headers=headers,
            )
            existing = resp.json()

            if existing:
                # Update count
                await client.patch(
                    "/usage_daily",
                    params={
                        "tenant_id": f"eq.{tenant_id}",
                        "event_type": f"eq.{event_type}",
                        "event_date": f"eq.{event_date}",
                    },
                    json={"event_count": count, "updated_at": now},
                    headers=headers,
                )
            else:
                await client.post(
                    "/usage_daily",
                    json={
                        "id": uuid.uuid4().hex,
                        "tenant_id": tenant_id,
                        "event_type": event_type,
                        "event_date": event_date,
                        "event_count": count,
                        "updated_at": now,
                    },
                    headers=headers,
                )

        # 3. Prune events older than 30 days
        prune_before = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        resp = await client.delete(
            "/usage_events",
            params={"created_at": f"lt.{prune_before}"},
            headers={**headers, "Prefer": "return=representation"},
        )
        pruned = len(resp.json()) if resp.status_code == 200 else 0
        if pruned:
            logger.warning("Pruned %d events older than 30 days", pruned)

    logger.warning("Usage aggregation complete")


if __name__ == "__main__":
    asyncio.run(aggregate())
