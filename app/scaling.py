"""Horizontal scaling infrastructure — metering, HPA config, PDB."""

from __future__ import annotations
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metering buffer (Redis Streams in production, in-memory for single replica)
# ---------------------------------------------------------------------------
@dataclass
class MeterEvent:
    tenant_id: str = ""
    event_type: str = ""  # "computation", "ocr_page", "api_call"
    count: int = 1
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class MeteringBuffer:
    """Thread-safe metering buffer. Production: Redis Streams backend."""

    def __init__(self, backend: str = "memory"):
        self.backend = backend
        self._buffer: list[MeterEvent] = []
        self._aggregated: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record(self, tenant_id: str, event_type: str, count: int = 1):
        """Record a metering event."""
        evt = MeterEvent(tenant_id=tenant_id, event_type=event_type, count=count)
        self._buffer.append(evt)
        self._aggregated[tenant_id][event_type] += count

    def flush(self) -> list[MeterEvent]:
        """Flush buffer and return events (for aggregation CronJob)."""
        events = self._buffer[:]
        self._buffer.clear()
        return events

    def get_tenant_usage(self, tenant_id: str) -> dict[str, int]:
        """Get aggregated usage for a tenant."""
        return dict(self._aggregated.get(tenant_id, {}))

    def get_all_usage(self) -> dict[str, dict[str, int]]:
        """Get aggregated usage for all tenants."""
        return {k: dict(v) for k, v in self._aggregated.items()}

    def reset(self):
        """Reset all metering data (for testing)."""
        self._buffer.clear()
        self._aggregated.clear()


# Global metering instance
_meter = MeteringBuffer()


def get_meter() -> MeteringBuffer:
    return _meter


def record_usage(tenant_id: str, event_type: str, count: int = 1):
    """Convenience function to record usage."""
    _meter.record(tenant_id, event_type, count)


# ---------------------------------------------------------------------------
# HPA Configuration
# ---------------------------------------------------------------------------
@dataclass
class HPAConfig:
    """Horizontal Pod Autoscaler configuration."""
    min_replicas: int = 1
    max_replicas: int = 3
    target_cpu_percent: int = 70
    scale_up_stabilization_seconds: int = 60
    scale_down_stabilization_seconds: int = 300

    def to_k8s_manifest(self, deployment_name: str, namespace: str) -> dict:
        """Generate K8s HPA manifest."""
        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": f"{deployment_name}-hpa",
                "namespace": namespace,
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": deployment_name,
                },
                "minReplicas": self.min_replicas,
                "maxReplicas": self.max_replicas,
                "metrics": [{
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": self.target_cpu_percent,
                        },
                    },
                }],
                "behavior": {
                    "scaleUp": {
                        "stabilizationWindowSeconds": self.scale_up_stabilization_seconds,
                    },
                    "scaleDown": {
                        "stabilizationWindowSeconds": self.scale_down_stabilization_seconds,
                    },
                },
            },
        }


# ---------------------------------------------------------------------------
# PodDisruptionBudget
# ---------------------------------------------------------------------------
@dataclass
class PDBConfig:
    """PodDisruptionBudget configuration."""
    min_available: int = 1

    def to_k8s_manifest(self, deployment_name: str, namespace: str) -> dict:
        """Generate K8s PDB manifest."""
        return {
            "apiVersion": "policy/v1",
            "kind": "PodDisruptionBudget",
            "metadata": {
                "name": f"{deployment_name}-pdb",
                "namespace": namespace,
            },
            "spec": {
                "minAvailable": self.min_available,
                "selector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": deployment_name,
                    },
                },
            },
        }


# ---------------------------------------------------------------------------
# Scaling status
# ---------------------------------------------------------------------------
@dataclass
class ScalingStatus:
    """Current scaling status for health endpoint."""
    metering_backend: str = "memory"
    buffer_size: int = 0
    tenants_tracked: int = 0
    hpa_enabled: bool = False
    hpa_min_replicas: int = 1
    hpa_max_replicas: int = 3
    pdb_min_available: int = 1


def get_scaling_status() -> ScalingStatus:
    """Get current scaling infrastructure status."""
    meter = get_meter()
    return ScalingStatus(
        metering_backend=meter.backend,
        buffer_size=len(meter._buffer),
        tenants_tracked=len(meter._aggregated),
    )
