"""Unit tests for db-flyway-admin migration engine."""

import os
import sys
import tempfile

import pytest

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from db.flyway.models import MigrationFile, MigrationRecord, MigrationState
from db.flyway.checksum import file_checksum
from db.flyway.exceptions import FlywayError, ChecksumMismatchError, MigrationFailedError
from db.flyway.engine import MigrationEngine, _PATTERN


class TestMigrationModels:
    def test_migration_file_fields(self):
        mf = MigrationFile(version=1, description="create schema",
                           filename="V001__create_schema.sql",
                           filepath="/tmp/V001__create_schema.sql",
                           checksum="abc123")
        assert mf.version == 1
        assert mf.description == "create schema"

    def test_migration_state_up_to_date(self):
        state = MigrationState(applied=[], pending=[], failed=[])
        assert state.is_up_to_date

    def test_migration_state_not_up_to_date(self):
        mf = MigrationFile(1, "test", "V001.sql", "/tmp/V001.sql", "abc")
        state = MigrationState(applied=[], pending=[mf], failed=[])
        assert not state.is_up_to_date

    def test_migration_state_failed(self):
        state = MigrationState(applied=[], pending=[], failed=["error"])
        assert not state.is_up_to_date


class TestChecksum:
    def test_file_checksum(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("CREATE TABLE test (id INT);")
            f.flush()
            path = f.name
        try:
            cs = file_checksum(path)
            assert len(cs) == 64  # SHA-256 hex
            # Same content = same checksum
            assert cs == file_checksum(path)
        finally:
            os.unlink(path)

    def test_different_content_different_checksum(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f1:
            f1.write("CREATE TABLE a (id INT);")
            f1.flush()
            p1 = f1.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f2:
            f2.write("CREATE TABLE b (id INT);")
            f2.flush()
            p2 = f2.name
        try:
            assert file_checksum(p1) != file_checksum(p2)
        finally:
            os.unlink(p1)
            os.unlink(p2)


class TestExceptions:
    def test_checksum_mismatch(self):
        err = ChecksumMismatchError(1, "expected", "actual")
        assert err.version == 1
        assert "V001" in str(err)

    def test_migration_failed(self):
        err = MigrationFailedError(3, "syntax error")
        assert err.version == 3
        assert "syntax error" in str(err)

    def test_flyway_error_hierarchy(self):
        assert issubclass(ChecksumMismatchError, FlywayError)
        assert issubclass(MigrationFailedError, FlywayError)


class TestFilenamePattern:
    def test_valid_patterns(self):
        assert _PATTERN.match("V001__create_schema.sql")
        assert _PATTERN.match("V002__roles_and_rls.sql")
        assert _PATTERN.match("V100__big_migration.sql")

    def test_invalid_patterns(self):
        assert not _PATTERN.match("V1__missing_zeros.sql")
        assert not _PATTERN.match("create_schema.sql")
        assert not _PATTERN.match("V001_single_underscore.sql")
        assert not _PATTERN.match("V001__no_extension")


class TestMigrationDiscovery:
    def test_discover_migrations(self):
        """Test that the engine discovers the actual V001-V004 migrations."""
        migrations_dir = os.path.join(
            os.path.dirname(__file__), "..", "app", "db", "flyway", "migrations"
        )
        engine = MigrationEngine("postgres://fake:fake@localhost/fake",
                                  migrations_dir=migrations_dir)
        files = engine.discover()
        assert len(files) == 7
        assert files[0].version == 1
        assert files[1].version == 2
        assert files[2].version == 3
        assert files[3].version == 4
        assert files[4].version == 5
        assert files[5].version == 6
        assert files[6].version == 7
        assert "create schema" in files[0].description
        assert "feature" in files[4].description
        assert "roles and rls" in files[1].description
        assert "functions" in files[2].description
        assert "audit log triggers" in files[3].description
        assert "oauth" in files[6].description

    def test_discover_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MigrationEngine("postgres://fake@localhost/fake",
                                      migrations_dir=tmpdir)
            assert engine.discover() == []

    def test_discover_nonexistent_dir(self):
        engine = MigrationEngine("postgres://fake@localhost/fake",
                                  migrations_dir="/nonexistent")
        assert engine.discover() == []
