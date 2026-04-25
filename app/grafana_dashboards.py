"""Grafana dashboard definitions and Prometheus custom metrics."""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Custom Prometheus Metrics
# ---------------------------------------------------------------------------
CUSTOM_METRICS = {
    "taxlens_drafts_total": {
        "type": "counter",
        "help": "Total tax drafts created",
        "labels": ["filing_status", "tax_year"],
    },
    "taxlens_ocr_pages_total": {
        "type": "counter",
        "help": "Total OCR pages processed",
        "labels": ["doc_type"],
    },
    "taxlens_active_tenants": {
        "type": "gauge",
        "help": "Number of active tenants",
        "labels": [],
    },
    "taxlens_computation_duration_seconds": {
        "type": "histogram",
        "help": "Tax computation duration in seconds",
        "labels": ["filing_status"],
        "buckets": [0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
    },
    "taxlens_api_requests_total": {
        "type": "counter",
        "help": "Total API requests by endpoint",
        "labels": ["method", "endpoint", "status"],
    },
    "taxlens_webhook_deliveries_total": {
        "type": "counter",
        "help": "Total webhook deliveries",
        "labels": ["event_type", "success"],
    },
    "taxlens_stripe_mrr": {
        "type": "gauge",
        "help": "Monthly recurring revenue in dollars",
        "labels": [],
    },
}


# ---------------------------------------------------------------------------
# Alert Rules
# ---------------------------------------------------------------------------
@dataclass
class AlertRule:
    name: str
    expr: str
    for_duration: str  # "5m", "1m", etc.
    severity: str  # "critical", "warning"
    summary: str
    description: str


ALERT_RULES = [
    AlertRule(
        name="TaxLensHighErrorRate",
        expr='rate(taxlens_api_requests_total{status=~"5.."}[5m]) / rate(taxlens_api_requests_total[5m]) > 0.05',
        for_duration="5m",
        severity="critical",
        summary="TaxLens API error rate > 5%",
        description="More than 5% of API requests are returning 5xx errors",
    ),
    AlertRule(
        name="TaxLensHighLatency",
        expr='histogram_quantile(0.95, rate(taxlens_computation_duration_seconds_bucket[5m])) > 2',
        for_duration="5m",
        severity="warning",
        summary="TaxLens P95 computation latency > 2s",
        description="95th percentile computation time exceeds 2 seconds",
    ),
    AlertRule(
        name="TaxLensDiskUsageHigh",
        expr='(node_filesystem_size_bytes{mountpoint="/var/lib/rancher"} - node_filesystem_free_bytes{mountpoint="/var/lib/rancher"}) / node_filesystem_size_bytes{mountpoint="/var/lib/rancher"} > 0.80',
        for_duration="10m",
        severity="warning",
        summary="TaxLens disk usage > 80%",
        description="Disk usage on /var/lib/rancher exceeds 80%",
    ),
    AlertRule(
        name="TaxLensWebhookFailures",
        expr='rate(taxlens_webhook_deliveries_total{success="false"}[15m]) > 0',
        for_duration="15m",
        severity="warning",
        summary="Webhook delivery failures detected",
        description="Some webhook deliveries are failing persistently",
    ),
]


# ---------------------------------------------------------------------------
# Dashboard JSON generators
# ---------------------------------------------------------------------------
def _panel(title: str, panel_type: str, targets: list, grid_pos: dict, **kwargs) -> dict:
    """Generate a Grafana panel definition."""
    panel = {
        "title": title,
        "type": panel_type,
        "gridPos": grid_pos,
        "targets": targets,
        "datasource": {"type": "prometheus", "uid": "prometheus"},
    }
    panel.update(kwargs)
    return panel


def _target(expr: str, legend: str = "") -> dict:
    return {"expr": expr, "legendFormat": legend, "refId": "A"}


def generate_api_dashboard() -> dict:
    """API Performance dashboard."""
    return {
        "dashboard": {
            "title": "TaxLens — API Performance",
            "tags": ["taxlens", "api"],
            "panels": [
                _panel("Request Rate", "timeseries",
                       [_target('rate(taxlens_api_requests_total[5m])', '{{method}} {{endpoint}}')],
                       {"x": 0, "y": 0, "w": 12, "h": 8}),
                _panel("Error Rate (%)", "timeseries",
                       [_target('rate(taxlens_api_requests_total{status=~"5.."}[5m]) / rate(taxlens_api_requests_total[5m]) * 100', 'Error %')],
                       {"x": 12, "y": 0, "w": 12, "h": 8}),
                _panel("Computation P95 Latency", "timeseries",
                       [_target('histogram_quantile(0.95, rate(taxlens_computation_duration_seconds_bucket[5m]))', 'P95')],
                       {"x": 0, "y": 8, "w": 12, "h": 8}),
                _panel("Active Tenants", "stat",
                       [_target('taxlens_active_tenants', 'Tenants')],
                       {"x": 12, "y": 8, "w": 6, "h": 8}),
                _panel("Total Drafts", "stat",
                       [_target('taxlens_drafts_total', 'Drafts')],
                       {"x": 18, "y": 8, "w": 6, "h": 8}),
            ],
        },
    }


def generate_business_dashboard() -> dict:
    """Business Metrics dashboard."""
    return {
        "dashboard": {
            "title": "TaxLens — Business Metrics",
            "tags": ["taxlens", "business"],
            "panels": [
                _panel("MRR", "stat",
                       [_target('taxlens_stripe_mrr', 'MRR')],
                       {"x": 0, "y": 0, "w": 6, "h": 6}),
                _panel("Drafts by Filing Status", "piechart",
                       [_target('taxlens_drafts_total', '{{filing_status}}')],
                       {"x": 6, "y": 0, "w": 6, "h": 6}),
                _panel("OCR Pages Processed", "timeseries",
                       [_target('rate(taxlens_ocr_pages_total[1h])', '{{doc_type}}')],
                       {"x": 12, "y": 0, "w": 12, "h": 6}),
                _panel("Webhook Delivery Success Rate", "gauge",
                       [_target('sum(taxlens_webhook_deliveries_total{success="true"}) / sum(taxlens_webhook_deliveries_total) * 100', 'Success %')],
                       {"x": 0, "y": 6, "w": 12, "h": 6}),
            ],
        },
    }


def generate_tenant_dashboard() -> dict:
    """Tenant Activity dashboard."""
    return {
        "dashboard": {
            "title": "TaxLens — Tenant Activity",
            "tags": ["taxlens", "tenants"],
            "panels": [
                _panel("Active Tenants Over Time", "timeseries",
                       [_target('taxlens_active_tenants', 'Tenants')],
                       {"x": 0, "y": 0, "w": 12, "h": 8}),
                _panel("Computations per Tenant", "table",
                       [_target('topk(10, sum by (tenant_id) (taxlens_drafts_total))', '')],
                       {"x": 12, "y": 0, "w": 12, "h": 8}),
            ],
        },
    }


def generate_infra_dashboard() -> dict:
    """Infrastructure dashboard."""
    return {
        "dashboard": {
            "title": "TaxLens — Infrastructure",
            "tags": ["taxlens", "infrastructure"],
            "panels": [
                _panel("CPU Usage", "timeseries",
                       [_target('rate(container_cpu_usage_seconds_total{namespace="taxlens"}[5m])', '{{pod}}')],
                       {"x": 0, "y": 0, "w": 12, "h": 8}),
                _panel("Memory Usage", "timeseries",
                       [_target('container_memory_working_set_bytes{namespace="taxlens"}', '{{pod}}')],
                       {"x": 12, "y": 0, "w": 12, "h": 8}),
                _panel("Disk Usage", "gauge",
                       [_target('(node_filesystem_size_bytes{mountpoint="/var/lib/rancher"} - node_filesystem_free_bytes{mountpoint="/var/lib/rancher"}) / node_filesystem_size_bytes{mountpoint="/var/lib/rancher"} * 100', 'Disk %')],
                       {"x": 0, "y": 8, "w": 6, "h": 6}),
                _panel("PostgreSQL Connections", "timeseries",
                       [_target('pg_stat_activity_count{datname="taxlens"}', 'Connections')],
                       {"x": 6, "y": 8, "w": 6, "h": 6}),
            ],
        },
    }


def get_all_dashboards() -> dict[str, dict]:
    """Return all dashboard definitions."""
    return {
        "api_performance": generate_api_dashboard(),
        "business_metrics": generate_business_dashboard(),
        "tenant_activity": generate_tenant_dashboard(),
        "infrastructure": generate_infra_dashboard(),
    }


def get_alert_rules_yaml() -> list[dict]:
    """Return alert rules in Prometheus alerting rule format."""
    return [
        {
            "alert": rule.name,
            "expr": rule.expr,
            "for": rule.for_duration,
            "labels": {"severity": rule.severity},
            "annotations": {"summary": rule.summary, "description": rule.description},
        }
        for rule in ALERT_RULES
    ]
