#!/usr/bin/env python3
"""Migrate data from Dolt (MySQL) to PostgreSQL via PostgREST.

Usage:
    python migrate_dolt_to_pg.py --dolt-host=IP --dolt-port=3306 \
        --postgrest-url=http://taxlens-postgrest:3000 --jwt-secret=SECRET

Reads all rows from each Dolt table and POSTs them to PostgREST.
Tables are migrated in dependency order (tenants first, FKs last).
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Tables in dependency order (parents before children)
TABLES = [
    "tenants",
    "users",
    "api_keys",
    "oauth_clients",
    "oauth_tokens",
    "tax_drafts",
    "documents",
    "plaid_items",
    "tenant_plans",
    "usage_events",
    "usage_daily",
    "billing_customers",
]

# Column type mappings (MySQL → PostgREST JSON)
BOOL_COLUMNS = {"has_ocr", "has_sync"}
DATETIME_COLUMNS = {
    "created_at", "updated_at", "uploaded_at", "connected_at",
    "last_synced_at", "last_used_at", "expires_at", "current_period_end",
}


def _convert_row(row: dict) -> dict:
    """Convert MySQL row values to PostgREST-compatible JSON."""
    converted = {}
    for key, val in row.items():
        if val is None:
            converted[key] = None
        elif key in BOOL_COLUMNS:
            converted[key] = bool(val)
        elif key in DATETIME_COLUMNS and hasattr(val, "isoformat"):
            converted[key] = val.isoformat()
        elif key == "expires_at" and isinstance(val, int):
            # oauth_tokens.expires_at is BIGINT (epoch)
            converted[key] = val
        elif isinstance(val, bytes):
            converted[key] = val.decode("utf-8", errors="replace")
        else:
            converted[key] = val
    return converted


async def migrate(dolt_host: str, dolt_port: int, dolt_db: str,
                  dolt_user: str, dolt_password: str,
                  postgrest_url: str, jwt_secret: str,
                  dry_run: bool = False):
    """Run the full migration."""
    import aiomysql
    import httpx
    import jwt as pyjwt

    # Connect to Dolt
    logger.info("Connecting to Dolt at %s:%d/%s...", dolt_host, dolt_port, dolt_db)
    pool = await aiomysql.create_pool(
        host=dolt_host, port=dolt_port, user=dolt_user,
        password=dolt_password, db=dolt_db,
        minsize=1, maxsize=3, autocommit=True, charset="utf8mb4",
    )

    # Mint admin JWT
    admin_token = pyjwt.encode(
        {"role": "app_admin", "tenant_id": "__admin__",
         "exp": int(time.time()) + 3600},
        jwt_secret, algorithm="HS256",
    )

    async with httpx.AsyncClient(base_url=postgrest_url, timeout=30.0) as client:
        total_rows = 0

        for table in TABLES:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(f"SELECT * FROM `{table}`")
                    rows = await cur.fetchall()

            if not rows:
                logger.info("  %s: 0 rows (skip)", table)
                continue

            converted = [_convert_row(r) for r in rows]

            if dry_run:
                logger.info("  %s: %d rows [DRY RUN]", table, len(converted))
                total_rows += len(converted)
                continue

            # Batch POST to PostgREST
            headers = {
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json",
                "Prefer": "resolution=ignore-duplicates",
            }

            # Post in batches of 100
            batch_size = 100
            for i in range(0, len(converted), batch_size):
                batch = converted[i:i + batch_size]
                resp = await client.post(
                    f"/{table}", json=batch, headers=headers,
                )
                if resp.status_code not in (200, 201):
                    logger.error("  %s batch %d: HTTP %d — %s",
                                 table, i // batch_size,
                                 resp.status_code, resp.text[:200])
                    # Try individual inserts for the failed batch
                    for row in batch:
                        r = await client.post(f"/{table}", json=row, headers=headers)
                        if r.status_code not in (200, 201):
                            logger.warning("  %s row %s: HTTP %d",
                                           table, row.get("id", "?"), r.status_code)

            total_rows += len(converted)
            logger.info("  %s: %d rows migrated", table, len(converted))

    pool.close()
    await pool.wait_closed()

    logger.info("Migration complete: %d total rows across %d tables",
                total_rows, len(TABLES))


def main():
    parser = argparse.ArgumentParser(description="Migrate Dolt data to PostgreSQL via PostgREST")
    parser.add_argument("--dolt-host", default=os.getenv("DOLT_HOST", "localhost"))
    parser.add_argument("--dolt-port", type=int, default=int(os.getenv("DOLT_PORT", "3306")))
    parser.add_argument("--dolt-db", default=os.getenv("DOLT_DATABASE", "taxlens"))
    parser.add_argument("--dolt-user", default=os.getenv("DOLT_USER", "root"))
    parser.add_argument("--dolt-password", default=os.getenv("DOLT_PASSWORD", ""))
    parser.add_argument("--postgrest-url", default=os.getenv("POSTGREST_URL", "http://localhost:3000"))
    parser.add_argument("--jwt-secret", default=os.getenv("DB_JWT_SECRET", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.jwt_secret:
        logger.error("--jwt-secret or DB_JWT_SECRET required")
        sys.exit(1)

    asyncio.run(migrate(
        args.dolt_host, args.dolt_port, args.dolt_db,
        args.dolt_user, args.dolt_password,
        args.postgrest_url, args.jwt_secret,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
