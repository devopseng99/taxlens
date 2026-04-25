"""Wave 70 tests — Horizontal Scaling infrastructure."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


@pytest.fixture(autouse=True)
def clean_meter():
    from scaling import get_meter
    get_meter().reset()
    yield
    get_meter().reset()


# =========================================================================
# Metering Buffer
# =========================================================================
class TestMetering:
    def test_record_event(self):
        from scaling import record_usage, get_meter
        record_usage("t1", "computation")
        assert get_meter().get_tenant_usage("t1") == {"computation": 1}

    def test_record_multiple_events(self):
        from scaling import record_usage, get_meter
        record_usage("t1", "computation", 3)
        record_usage("t1", "ocr_page", 5)
        usage = get_meter().get_tenant_usage("t1")
        assert usage["computation"] == 3
        assert usage["ocr_page"] == 5

    def test_multiple_tenants(self):
        from scaling import record_usage, get_meter
        record_usage("t1", "computation", 2)
        record_usage("t2", "computation", 7)
        all_usage = get_meter().get_all_usage()
        assert all_usage["t1"]["computation"] == 2
        assert all_usage["t2"]["computation"] == 7

    def test_flush_returns_and_clears_buffer(self):
        from scaling import record_usage, get_meter
        record_usage("t1", "api_call", 10)
        meter = get_meter()
        events = meter.flush()
        assert len(events) == 1
        assert events[0].count == 10
        assert len(meter.flush()) == 0  # buffer cleared

    def test_flush_does_not_clear_aggregated(self):
        from scaling import record_usage, get_meter
        record_usage("t1", "computation")
        get_meter().flush()
        assert get_meter().get_tenant_usage("t1") == {"computation": 1}

    def test_reset_clears_everything(self):
        from scaling import record_usage, get_meter
        record_usage("t1", "computation")
        get_meter().reset()
        assert get_meter().get_tenant_usage("t1") == {}
        assert len(get_meter().flush()) == 0


# =========================================================================
# HPA Configuration
# =========================================================================
class TestHPA:
    def test_default_config(self):
        from scaling import HPAConfig
        hpa = HPAConfig()
        assert hpa.min_replicas == 1
        assert hpa.max_replicas == 3
        assert hpa.target_cpu_percent == 70

    def test_manifest_generation(self):
        from scaling import HPAConfig
        hpa = HPAConfig(min_replicas=2, max_replicas=5, target_cpu_percent=60)
        manifest = hpa.to_k8s_manifest("taxlens-api", "taxlens")
        assert manifest["kind"] == "HorizontalPodAutoscaler"
        assert manifest["spec"]["minReplicas"] == 2
        assert manifest["spec"]["maxReplicas"] == 5
        assert manifest["metadata"]["namespace"] == "taxlens"

    def test_manifest_has_behavior(self):
        from scaling import HPAConfig
        manifest = HPAConfig().to_k8s_manifest("taxlens-api", "taxlens")
        behavior = manifest["spec"]["behavior"]
        assert "scaleUp" in behavior
        assert "scaleDown" in behavior
        assert behavior["scaleDown"]["stabilizationWindowSeconds"] == 300


# =========================================================================
# PDB Configuration
# =========================================================================
class TestPDB:
    def test_default_config(self):
        from scaling import PDBConfig
        pdb = PDBConfig()
        assert pdb.min_available == 1

    def test_manifest_generation(self):
        from scaling import PDBConfig
        pdb = PDBConfig(min_available=2)
        manifest = pdb.to_k8s_manifest("taxlens-api", "taxlens")
        assert manifest["kind"] == "PodDisruptionBudget"
        assert manifest["spec"]["minAvailable"] == 2
        assert manifest["spec"]["selector"]["matchLabels"]["app.kubernetes.io/name"] == "taxlens-api"


# =========================================================================
# Scaling Status
# =========================================================================
class TestScalingStatus:
    def test_status_reports_metrics(self):
        from scaling import get_scaling_status, record_usage
        record_usage("t1", "computation")
        record_usage("t2", "ocr_page")
        status = get_scaling_status()
        assert status.metering_backend == "memory"
        assert status.tenants_tracked == 2
        assert status.buffer_size == 2

    def test_health_endpoint_includes_scaling(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "scaling" in src
        assert "metering_backend" in src
