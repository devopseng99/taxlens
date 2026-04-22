"""Data models for db-flyway-admin migration system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MigrationFile:
    """A versioned SQL migration file discovered on disk."""
    version: int
    description: str
    filename: str
    filepath: str
    checksum: str


@dataclass
class MigrationRecord:
    """A migration record from flyway_schema_history."""
    version: int
    description: str
    checksum: str
    installed_on: datetime
    execution_time_ms: int
    success: bool


@dataclass
class MigrationState:
    """Current state of migrations: applied vs pending."""
    applied: list[MigrationRecord] = field(default_factory=list)
    pending: list[MigrationFile] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def is_up_to_date(self) -> bool:
        return len(self.pending) == 0 and len(self.failed) == 0
