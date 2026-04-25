"""Wave 73 tests — Grafana Dashboard Integration."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Custom Metrics
# =========================================================================
class TestCustomMetrics:
    def test_metrics_defined(self):
        from grafana_dashboards import CUSTOM_METRICS
        assert "taxlens_drafts_total" in CUSTOM_METRICS
        assert "taxlens_ocr_pages_total" in CUSTOM_METRICS
        assert "taxlens_active_tenants" in CUSTOM_METRICS
        assert "taxlens_computation_duration_seconds" in CUSTOM_METRICS
        assert "taxlens_api_requests_total" in CUSTOM_METRICS
        assert "taxlens_webhook_deliveries_total" in CUSTOM_METRICS
        assert "taxlens_stripe_mrr" in CUSTOM_METRICS

    def test_metric_types(self):
        from grafana_dashboards import CUSTOM_METRICS
        assert CUSTOM_METRICS["taxlens_drafts_total"]["type"] == "counter"
        assert CUSTOM_METRICS["taxlens_active_tenants"]["type"] == "gauge"
        assert CUSTOM_METRICS["taxlens_computation_duration_seconds"]["type"] == "histogram"

    def test_histogram_has_buckets(self):
        from grafana_dashboards import CUSTOM_METRICS
        buckets = CUSTOM_METRICS["taxlens_computation_duration_seconds"]["buckets"]
        assert len(buckets) >= 4
        assert buckets == sorted(buckets)


# =========================================================================
# Alert Rules
# =========================================================================
class TestAlertRules:
    def test_four_alerts_defined(self):
        from grafana_dashboards import ALERT_RULES
        assert len(ALERT_RULES) == 4

    def test_high_error_rate_alert(self):
        from grafana_dashboards import ALERT_RULES
        error_alert = next(r for r in ALERT_RULES if r.name == "TaxLensHighErrorRate")
        assert error_alert.severity == "critical"
        assert "0.05" in error_alert.expr  # 5% threshold

    def test_high_latency_alert(self):
        from grafana_dashboards import ALERT_RULES
        latency_alert = next(r for r in ALERT_RULES if r.name == "TaxLensHighLatency")
        assert latency_alert.severity == "warning"
        assert "2" in latency_alert.expr  # 2s threshold

    def test_disk_usage_alert(self):
        from grafana_dashboards import ALERT_RULES
        disk_alert = next(r for r in ALERT_RULES if r.name == "TaxLensDiskUsageHigh")
        assert "0.80" in disk_alert.expr  # 80% threshold

    def test_alert_rules_yaml_format(self):
        from grafana_dashboards import get_alert_rules_yaml
        rules = get_alert_rules_yaml()
        assert len(rules) == 4
        for rule in rules:
            assert "alert" in rule
            assert "expr" in rule
            assert "for" in rule
            assert "labels" in rule
            assert "annotations" in rule


# =========================================================================
# Dashboard Definitions
# =========================================================================
class TestDashboards:
    def test_four_dashboards(self):
        from grafana_dashboards import get_all_dashboards
        dashboards = get_all_dashboards()
        assert "api_performance" in dashboards
        assert "business_metrics" in dashboards
        assert "tenant_activity" in dashboards
        assert "infrastructure" in dashboards

    def test_api_dashboard_panels(self):
        from grafana_dashboards import generate_api_dashboard
        d = generate_api_dashboard()
        panels = d["dashboard"]["panels"]
        assert len(panels) >= 4
        titles = [p["title"] for p in panels]
        assert "Request Rate" in titles
        assert "Error Rate (%)" in titles

    def test_business_dashboard_panels(self):
        from grafana_dashboards import generate_business_dashboard
        d = generate_business_dashboard()
        panels = d["dashboard"]["panels"]
        titles = [p["title"] for p in panels]
        assert "MRR" in titles
        assert "OCR Pages Processed" in titles

    def test_infra_dashboard_panels(self):
        from grafana_dashboards import generate_infra_dashboard
        d = generate_infra_dashboard()
        panels = d["dashboard"]["panels"]
        titles = [p["title"] for p in panels]
        assert "CPU Usage" in titles
        assert "Memory Usage" in titles
        assert "Disk Usage" in titles

    def test_panels_have_targets(self):
        from grafana_dashboards import get_all_dashboards
        for name, d in get_all_dashboards().items():
            for panel in d["dashboard"]["panels"]:
                assert len(panel["targets"]) > 0, f"Panel '{panel['title']}' in {name} has no targets"
                assert "expr" in panel["targets"][0]


# =========================================================================
# API Endpoint
# =========================================================================
class TestEndpoint:
    def test_dashboards_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/admin/dashboards" in src
        assert "async def grafana_dashboards" in src
