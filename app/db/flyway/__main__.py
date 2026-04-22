"""CLI for db-flyway-admin: python -m db.flyway migrate|info|validate"""

import argparse
import asyncio
import logging
import os
import sys

from .engine import MigrationEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _get_db_url() -> str:
    """Build PostgreSQL URL from environment variables."""
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db = os.getenv("PG_DATABASE", "taxlens")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    return f"postgres://{user}:{password}@{host}:{port}/{db}"


async def cmd_migrate(engine: MigrationEngine, dry_run: bool = False):
    applied = await engine.migrate(dry_run=dry_run)
    if applied:
        for m in applied:
            prefix = "[DRY RUN] " if dry_run else ""
            print(f"  {prefix}V{m.version:03d}: {m.description}")
    else:
        print("  Database is up to date.")


async def cmd_info(engine: MigrationEngine):
    state = await engine.info()
    print(f"\nApplied ({len(state.applied)}):")
    for r in state.applied:
        status = "OK" if r.success else "FAILED"
        print(f"  V{r.version:03d}: {r.description} [{status}] ({r.execution_time_ms}ms)")
    print(f"\nPending ({len(state.pending)}):")
    for m in state.pending:
        print(f"  V{m.version:03d}: {m.description}")
    if state.failed:
        print(f"\nIssues ({len(state.failed)}):")
        for msg in state.failed:
            print(f"  {msg}")


async def cmd_validate(engine: MigrationEngine):
    errors = await engine.validate()
    if errors:
        print("Validation FAILED:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("All migrations valid.")


def main():
    parser = argparse.ArgumentParser(prog="db.flyway", description="Database migration tool")
    parser.add_argument("command", choices=["migrate", "info", "validate"])
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied")
    parser.add_argument("--db-url", help="PostgreSQL connection URL (overrides env vars)")
    parser.add_argument("--migrations-dir", help="Path to migrations directory")
    args = parser.parse_args()

    db_url = args.db_url or _get_db_url()
    engine = MigrationEngine(db_url, migrations_dir=args.migrations_dir)

    if args.command == "migrate":
        asyncio.run(cmd_migrate(engine, dry_run=args.dry_run))
    elif args.command == "info":
        asyncio.run(cmd_info(engine))
    elif args.command == "validate":
        asyncio.run(cmd_validate(engine))


if __name__ == "__main__":
    main()
