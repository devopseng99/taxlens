"""Migration engine — discover, validate, and apply versioned SQL migrations."""

import logging
import os
import re
import time
from pathlib import Path

from .models import MigrationFile, MigrationRecord, MigrationState
from .checksum import file_checksum
from .exceptions import ChecksumMismatchError, MigrationFailedError
from .history import ensure_history_table, get_applied, record_migration

logger = logging.getLogger(__name__)

# Migration filename pattern: V001__description.sql
_PATTERN = re.compile(r"^V(\d{3})__(.+)\.sql$")


class MigrationEngine:
    """Flyway-inspired migration engine for PostgreSQL.

    Usage:
        engine = MigrationEngine(db_url)
        await engine.migrate()        # Apply pending migrations
        state = await engine.info()   # Show current state
        errors = await engine.validate()  # Verify checksums
    """

    def __init__(self, db_url: str, migrations_dir: str = None):
        self.db_url = db_url
        self.migrations_dir = migrations_dir or str(
            Path(__file__).parent / "migrations"
        )

    def discover(self) -> list[MigrationFile]:
        """Scan migrations directory for V*__.sql files."""
        migrations = []
        if not os.path.isdir(self.migrations_dir):
            logger.warning("Migrations directory not found: %s", self.migrations_dir)
            return migrations

        for filename in sorted(os.listdir(self.migrations_dir)):
            match = _PATTERN.match(filename)
            if match:
                version = int(match.group(1))
                description = match.group(2).replace("_", " ")
                filepath = os.path.join(self.migrations_dir, filename)
                migrations.append(MigrationFile(
                    version=version,
                    description=description,
                    filename=filename,
                    filepath=filepath,
                    checksum=file_checksum(filepath),
                ))
        return migrations

    async def _get_conn(self):
        """Get an asyncpg connection."""
        import asyncpg
        return await asyncpg.connect(self.db_url)

    async def get_state(self) -> MigrationState:
        """Compare applied migrations with discovered files."""
        conn = await self._get_conn()
        try:
            await ensure_history_table(conn)
            applied_rows = await get_applied(conn)
            applied_map = {r["version"]: r for r in applied_rows}

            discovered = self.discover()
            state = MigrationState()

            for rec in applied_rows:
                state.applied.append(MigrationRecord(
                    version=rec["version"],
                    description=rec["description"],
                    checksum=rec["checksum"],
                    installed_on=rec["installed_on"],
                    execution_time_ms=rec["execution_time_ms"],
                    success=rec["success"],
                ))

            for mf in discovered:
                if mf.version not in applied_map:
                    state.pending.append(mf)
                else:
                    rec = applied_map[mf.version]
                    if rec["checksum"] != mf.checksum:
                        state.failed.append(
                            f"V{mf.version:03d}: checksum mismatch "
                            f"(applied={rec['checksum'][:12]}..., "
                            f"file={mf.checksum[:12]}...)"
                        )
            return state
        finally:
            await conn.close()

    async def migrate(self, dry_run: bool = False) -> list[MigrationFile]:
        """Apply all pending migrations in version order.

        Returns list of applied migrations.
        Raises MigrationFailedError if any migration fails.
        """
        conn = await self._get_conn()
        try:
            await ensure_history_table(conn)
            applied_rows = await get_applied(conn)
            applied_versions = {r["version"] for r in applied_rows}

            discovered = self.discover()
            pending = [m for m in discovered if m.version not in applied_versions]

            if not pending:
                logger.info("Database is up to date — no pending migrations")
                return []

            if dry_run:
                for m in pending:
                    logger.info("[DRY RUN] Would apply V%03d: %s", m.version, m.description)
                return pending

            applied = []
            for mf in pending:
                logger.info("Applying V%03d: %s ...", mf.version, mf.description)
                sql = Path(mf.filepath).read_text()
                start = time.monotonic()

                try:
                    # Run entire migration in a transaction
                    async with conn.transaction():
                        await conn.execute(sql)
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    await record_migration(
                        conn, mf.version, mf.description,
                        mf.checksum, elapsed_ms, success=True,
                    )
                    applied.append(mf)
                    logger.info("Applied V%03d in %dms", mf.version, elapsed_ms)
                except Exception as e:
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    await record_migration(
                        conn, mf.version, mf.description,
                        mf.checksum, elapsed_ms, success=False,
                    )
                    raise MigrationFailedError(mf.version, str(e)) from e

            logger.info("Applied %d migration(s)", len(applied))
            return applied
        finally:
            await conn.close()

    async def validate(self) -> list[str]:
        """Verify checksums of applied migrations against files on disk.

        Returns list of error messages (empty = valid).
        """
        state = await self.get_state()
        errors = list(state.failed)

        discovered_map = {m.version: m for m in self.discover()}
        for rec in state.applied:
            if rec.version in discovered_map:
                mf = discovered_map[rec.version]
                if rec.checksum != mf.checksum:
                    errors.append(
                        f"V{rec.version:03d}: checksum mismatch"
                    )
            else:
                errors.append(
                    f"V{rec.version:03d}: applied but file missing from disk"
                )

        if errors:
            logger.warning("Validation found %d issue(s)", len(errors))
        else:
            logger.info("All migrations validated successfully")
        return errors

    async def info(self) -> MigrationState:
        """Display current migration state."""
        state = await self.get_state()
        logger.info("Applied: %d, Pending: %d, Failed: %d",
                     len(state.applied), len(state.pending), len(state.failed))
        return state
