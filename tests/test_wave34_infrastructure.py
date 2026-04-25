"""Wave 34 tests — Infrastructure improvements (backup script, config)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Backup Script
# =========================================================================
class TestBackupScript:
    def _script_path(self):
        return os.path.join(os.path.dirname(__file__), "..", "scripts", "backup-pg.sh")

    def test_backup_script_exists(self):
        assert os.path.exists(self._script_path())

    def test_backup_script_executable(self):
        assert os.access(self._script_path(), os.X_OK)

    def test_backup_script_has_restore_instructions(self):
        content = open(self._script_path()).read()
        assert "restore" in content.lower()
        assert "pg_dump" in content

    def test_backup_script_retention_configurable(self):
        content = open(self._script_path()).read()
        assert "RETENTION_DAYS" in content

    def test_backup_script_uses_gzip(self):
        content = open(self._script_path()).read()
        assert "gzip" in content or "gz" in content

    def test_backup_script_uses_ssh_key(self):
        """Backup uses the standard devops SSH key for node access."""
        content = open(self._script_path()).read()
        assert "id_rsa_devops_ssh" in content


# =========================================================================
# Health Endpoint Structure (parsed from source, not runtime)
# =========================================================================
class TestHealthEndpointSource:
    def _read_main(self):
        main_path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        return open(main_path).read()

    def test_health_has_uptime(self):
        """Health endpoint includes uptime_seconds."""
        src = self._read_main()
        assert "uptime_seconds" in src
        assert "_STARTUP_TIME" in src

    def test_health_has_deep_mode(self):
        """Health endpoint supports deep=True parameter."""
        src = self._read_main()
        assert "deep: bool" in src
        assert "db_latency_ms" in src
        assert "storage_write_ok" in src

    def test_readiness_endpoint_exists(self):
        """Readiness probe endpoint is defined."""
        src = self._read_main()
        assert '"/ready"' in src
        assert '"ready"' in src

    def test_readiness_returns_503_on_failure(self):
        """Readiness returns 503 when dependencies are down."""
        src = self._read_main()
        assert "503" in src

    def test_graceful_shutdown_logging(self):
        """Lifespan logs shutdown for observability."""
        src = self._read_main()
        assert "shutting down" in src.lower() or "shutdown" in src.lower()

    def test_version_consistency(self):
        """Version string is consistent in both locations."""
        src = self._read_main()
        # Count occurrences of the version string
        version = "3.35.0"
        count = src.count(f'"{version}"')
        assert count >= 2, f"Expected version {version} in at least 2 places, found {count}"


# =========================================================================
# Tax Config Completeness (infrastructure: all constants loadable)
# =========================================================================
class TestTaxConfigInfra:
    def test_all_year_configs_loadable(self):
        from tax_config import get_year_config, SUPPORTED_TAX_YEARS
        for year in SUPPORTED_TAX_YEARS:
            c = get_year_config(year)
            assert hasattr(c, 'FEDERAL_BRACKETS')
            assert hasattr(c, 'STANDARD_DEDUCTION')
            assert hasattr(c, 'HSA_LIMIT_SELF')
            assert hasattr(c, 'HSA_LIMIT_FAMILY')
            assert hasattr(c, 'HSA_CATCHUP')
            assert hasattr(c, 'RENTAL_LOSS_LIMIT')

    def test_year_config_values_reasonable(self):
        from tax_config import get_year_config
        for year in [2024, 2025]:
            c = get_year_config(year)
            assert c.HSA_LIMIT_SELF > 3000
            assert c.HSA_LIMIT_FAMILY > c.HSA_LIMIT_SELF
            assert c.HSA_CATCHUP == 1000  # Statutory, not indexed
            assert c.RENTAL_LOSS_LIMIT == 25000  # Statutory
            assert c.RENTAL_LOSS_PHASEOUT_START == 100000
            assert c.RENTAL_LOSS_PHASEOUT_END == 150000

    def test_engine_imports_clean(self):
        """All engine imports succeed without Azure/external deps."""
        from tax_engine import (
            PersonInfo, W2Income, Deductions, AdditionalIncome, Payments,
            BusinessIncome, CapitalTransaction, Dependent,
            RentalProperty, HSAContribution,
            compute_tax,
        )
        assert callable(compute_tax)
