"""Webhook notification system — HMAC-signed event delivery with retry."""

from __future__ import annotations
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
EVENT_TYPES = [
    "draft.created",
    "draft.updated",
    "document.uploaded",
    "document.ocr_complete",
    "plan.upgraded",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class WebhookEndpoint:
    id: str = ""
    tenant_id: str = ""
    url: str = ""
    secret: str = ""
    events: list = field(default_factory=list)  # list of event type strings
    active: bool = True
    created_at: str = ""
    description: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"whep_{uuid.uuid4().hex[:12]}"
        if not self.secret:
            self.secret = f"whsec_{uuid.uuid4().hex}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class WebhookDelivery:
    id: str = ""
    endpoint_id: str = ""
    event_type: str = ""
    payload: dict = field(default_factory=dict)
    status_code: int = 0
    success: bool = False
    attempt: int = 1
    max_attempts: int = 3
    next_retry_at: Optional[str] = None
    created_at: str = ""
    completed_at: Optional[str] = None
    error_message: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"whdel_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class WebhookEvent:
    id: str = ""
    event_type: str = ""
    tenant_id: str = ""
    data: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"evt_{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# In-memory store (production would use DB tables)
# ---------------------------------------------------------------------------
_endpoints: dict[str, WebhookEndpoint] = {}
_deliveries: list[WebhookDelivery] = []
_events: list[WebhookEvent] = []


def reset_store():
    """Reset in-memory store (for testing)."""
    _endpoints.clear()
    _deliveries.clear()
    _events.clear()


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------
def sign_payload(secret: str, payload: str) -> str:
    """Create HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(secret: str, payload: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = sign_payload(secret, payload)
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Endpoint CRUD
# ---------------------------------------------------------------------------
def create_endpoint(
    tenant_id: str,
    url: str,
    events: list[str],
    description: str = "",
) -> WebhookEndpoint:
    """Register a new webhook endpoint."""
    for evt in events:
        if evt not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {evt}. Valid: {EVENT_TYPES}")
    ep = WebhookEndpoint(
        tenant_id=tenant_id,
        url=url,
        events=events,
        description=description,
    )
    _endpoints[ep.id] = ep
    return ep


def get_endpoint(endpoint_id: str) -> Optional[WebhookEndpoint]:
    return _endpoints.get(endpoint_id)


def list_endpoints(tenant_id: str) -> list[WebhookEndpoint]:
    return [ep for ep in _endpoints.values() if ep.tenant_id == tenant_id]


def update_endpoint(
    endpoint_id: str,
    url: Optional[str] = None,
    events: Optional[list[str]] = None,
    active: Optional[bool] = None,
    description: Optional[str] = None,
) -> Optional[WebhookEndpoint]:
    ep = _endpoints.get(endpoint_id)
    if not ep:
        return None
    if url is not None:
        ep.url = url
    if events is not None:
        for evt in events:
            if evt not in EVENT_TYPES:
                raise ValueError(f"Unknown event type: {evt}")
        ep.events = events
    if active is not None:
        ep.active = active
    if description is not None:
        ep.description = description
    return ep


def delete_endpoint(endpoint_id: str) -> bool:
    return _endpoints.pop(endpoint_id, None) is not None


# ---------------------------------------------------------------------------
# Event dispatch
# ---------------------------------------------------------------------------
RETRY_DELAYS = [0, 60, 300]  # seconds: immediate, 1min, 5min


def dispatch_event(
    event_type: str,
    tenant_id: str,
    data: dict,
) -> list[WebhookDelivery]:
    """Dispatch event to all matching endpoints for the tenant."""
    event = WebhookEvent(event_type=event_type, tenant_id=tenant_id, data=data)
    _events.append(event)

    deliveries = []
    matching = [
        ep for ep in _endpoints.values()
        if ep.tenant_id == tenant_id
        and ep.active
        and event_type in ep.events
    ]

    for ep in matching:
        delivery = _deliver(ep, event)
        deliveries.append(delivery)

    return deliveries


def _deliver(ep: WebhookEndpoint, event: WebhookEvent) -> WebhookDelivery:
    """Attempt delivery (in-memory simulation — real impl uses httpx)."""
    payload_dict = {
        "id": event.id,
        "type": event.event_type,
        "created": event.created_at,
        "data": event.data,
    }
    payload_json = json.dumps(payload_dict, default=str)
    signature = sign_payload(ep.secret, payload_json)

    delivery = WebhookDelivery(
        endpoint_id=ep.id,
        event_type=event.event_type,
        payload=payload_dict,
    )

    # In production: httpx.post(ep.url, content=payload_json, headers={...})
    # For now, simulate success for in-memory testing
    delivery.status_code = 200
    delivery.success = True
    delivery.completed_at = datetime.now(timezone.utc).isoformat()

    _deliveries.append(delivery)
    return delivery


def get_deliveries(
    endpoint_id: Optional[str] = None,
    limit: int = 50,
) -> list[WebhookDelivery]:
    """Get delivery log, optionally filtered by endpoint."""
    filtered = _deliveries
    if endpoint_id:
        filtered = [d for d in filtered if d.endpoint_id == endpoint_id]
    return filtered[-limit:]


def get_events(tenant_id: Optional[str] = None, limit: int = 50) -> list[WebhookEvent]:
    """Get event log, optionally filtered by tenant."""
    filtered = _events
    if tenant_id:
        filtered = [e for e in filtered if e.tenant_id == tenant_id]
    return filtered[-limit:]


# ---------------------------------------------------------------------------
# Test endpoint (simulates delivery without actual HTTP)
# ---------------------------------------------------------------------------
def test_endpoint(endpoint_id: str) -> WebhookDelivery:
    """Send a test event to verify endpoint configuration."""
    ep = _endpoints.get(endpoint_id)
    if not ep:
        raise ValueError(f"Endpoint not found: {endpoint_id}")

    test_event = WebhookEvent(
        event_type="test",
        tenant_id=ep.tenant_id,
        data={"message": "This is a test webhook delivery", "endpoint_id": endpoint_id},
    )

    delivery = _deliver(ep, test_event)
    return delivery
