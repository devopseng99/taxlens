"""Wave 39 tests — Operational Maturity (CronJobs, smoke tests, backups)."""

import os
import yaml
import pytest


K8S_DIR = os.path.join(os.path.dirname(__file__), "..", "k8s")


# =========================================================================
# CronJob YAML Validation
# =========================================================================
class TestCronJobYAML:
    def _load(self, filename):
        path = os.path.join(K8S_DIR, filename)
        with open(path) as f:
            return yaml.safe_load(f)

    # --- PG Backup CronJob ---
    def test_pg_backup_exists(self):
        assert os.path.exists(os.path.join(K8S_DIR, "cronjob-pg-backup.yaml"))

    def test_pg_backup_schedule(self):
        doc = self._load("cronjob-pg-backup.yaml")
        assert doc["spec"]["schedule"] == "0 2 * * *"

    def test_pg_backup_concurrency_forbid(self):
        doc = self._load("cronjob-pg-backup.yaml")
        assert doc["spec"]["concurrencyPolicy"] == "Forbid"

    def test_pg_backup_uses_pg_dump(self):
        doc = self._load("cronjob-pg-backup.yaml")
        cmd = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert "pg_dump" in cmd

    def test_pg_backup_uses_gzip(self):
        doc = self._load("cronjob-pg-backup.yaml")
        cmd = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert "gzip" in cmd

    def test_pg_backup_7day_retention(self):
        doc = self._load("cronjob-pg-backup.yaml")
        cmd = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert "-mtime +7 -delete" in cmd

    def test_pg_backup_secret_ref(self):
        doc = self._load("cronjob-pg-backup.yaml")
        envs = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["env"]
        pgpass = [e for e in envs if e["name"] == "PGPASSWORD"]
        assert len(pgpass) == 1
        assert pgpass[0]["valueFrom"]["secretKeyRef"]["name"] == "taxlens-pg-secret"

    def test_pg_backup_node_selector(self):
        doc = self._load("cronjob-pg-backup.yaml")
        ns = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["nodeSelector"]
        assert ns["kubernetes.io/hostname"] == "mgplcb05"

    def test_pg_backup_hostpath_volume(self):
        doc = self._load("cronjob-pg-backup.yaml")
        vols = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
        assert any(v.get("hostPath", {}).get("path", "").startswith("/opt/k8s-pers/") for v in vols)

    # --- Smoke Test CronJob ---
    def test_smoke_test_exists(self):
        assert os.path.exists(os.path.join(K8S_DIR, "cronjob-smoke-test.yaml"))

    def test_smoke_test_schedule(self):
        doc = self._load("cronjob-smoke-test.yaml")
        assert doc["spec"]["schedule"] == "*/30 * * * *"

    def test_smoke_test_concurrency_forbid(self):
        doc = self._load("cronjob-smoke-test.yaml")
        assert doc["spec"]["concurrencyPolicy"] == "Forbid"

    def test_smoke_test_checks_health(self):
        doc = self._load("cronjob-smoke-test.yaml")
        cmd = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert "/health" in cmd

    def test_smoke_test_checks_ready(self):
        doc = self._load("cronjob-smoke-test.yaml")
        cmd = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert "/ready" in cmd

    def test_smoke_test_checks_metrics(self):
        doc = self._load("cronjob-smoke-test.yaml")
        cmd = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert "/metrics" in cmd

    def test_smoke_test_checks_docs(self):
        doc = self._load("cronjob-smoke-test.yaml")
        cmd = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert "/docs" in cmd

    def test_smoke_test_uses_short_dns(self):
        """Smoke test uses short service names (not FQDN) for Alpine DNS compat."""
        doc = self._load("cronjob-smoke-test.yaml")
        cmd = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert "taxlens-api:8000" in cmd
        assert ".svc.cluster.local" not in cmd

    def test_smoke_test_ndots_config(self):
        """dnsConfig ndots:2 set for short DNS resolution."""
        doc = self._load("cronjob-smoke-test.yaml")
        dns = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"].get("dnsConfig", {})
        opts = dns.get("options", [])
        ndots = [o for o in opts if o.get("name") == "ndots"]
        assert len(ndots) == 1
        assert ndots[0]["value"] == "2"

    def test_smoke_test_timeout(self):
        doc = self._load("cronjob-smoke-test.yaml")
        deadline = doc["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"]
        assert deadline <= 120  # Should complete well within 2 min

    def test_smoke_test_no_restart(self):
        doc = self._load("cronjob-smoke-test.yaml")
        policy = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["restartPolicy"]
        assert policy == "Never"
