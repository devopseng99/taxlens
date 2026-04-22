"""db-flyway-admin — reusable PostgreSQL migration engine.

Usage:
    from db.flyway import MigrationEngine

    engine = MigrationEngine(db_url="postgres://user:pass@host:5432/dbname")
    await engine.migrate()
"""

from .engine import MigrationEngine
from .exceptions import FlywayError, ChecksumMismatchError, MigrationFailedError

__all__ = ["MigrationEngine", "FlywayError", "ChecksumMismatchError", "MigrationFailedError"]
