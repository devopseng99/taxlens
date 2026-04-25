"""Wave 69 tests — Webhook Notifications + Event System."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


@pytest.fixture(autouse=True)
def clean_store():
    from webhooks import reset_store
    reset_store()
    yield
    reset_store()


# =========================================================================
# HMAC Signing
# =========================================================================
class TestSigning:
    def test_sign_payload(self):
        from webhooks import sign_payload
        sig = sign_payload("my-secret", '{"test": true}')
        assert len(sig) == 64  # SHA256 hex digest
        assert sig.isalnum()

    def test_verify_valid_signature(self):
        from webhooks import sign_payload, verify_signature
        payload = '{"event": "draft.created"}'
        secret = "test-secret-123"
        sig = sign_payload(secret, payload)
        assert verify_signature(secret, payload, sig) is True

    def test_verify_invalid_signature(self):
        from webhooks import verify_signature
        assert verify_signature("secret", "payload", "invalid-sig") is False

    def test_different_secrets_different_signatures(self):
        from webhooks import sign_payload
        payload = '{"same": "data"}'
        sig1 = sign_payload("secret-1", payload)
        sig2 = sign_payload("secret-2", payload)
        assert sig1 != sig2


# =========================================================================
# Endpoint CRUD
# =========================================================================
class TestEndpointCRUD:
    def test_create_endpoint(self):
        from webhooks import create_endpoint
        ep = create_endpoint("tenant-1", "https://example.com/hook", ["draft.created"])
        assert ep.id.startswith("whep_")
        assert ep.secret.startswith("whsec_")
        assert ep.url == "https://example.com/hook"
        assert ep.events == ["draft.created"]
        assert ep.active is True

    def test_list_endpoints_by_tenant(self):
        from webhooks import create_endpoint, list_endpoints
        create_endpoint("t1", "https://a.com", ["draft.created"])
        create_endpoint("t1", "https://b.com", ["draft.updated"])
        create_endpoint("t2", "https://c.com", ["draft.created"])
        assert len(list_endpoints("t1")) == 2
        assert len(list_endpoints("t2")) == 1

    def test_update_endpoint(self):
        from webhooks import create_endpoint, update_endpoint
        ep = create_endpoint("t1", "https://old.com", ["draft.created"])
        updated = update_endpoint(ep.id, url="https://new.com", active=False)
        assert updated.url == "https://new.com"
        assert updated.active is False

    def test_delete_endpoint(self):
        from webhooks import create_endpoint, delete_endpoint, get_endpoint
        ep = create_endpoint("t1", "https://del.com", ["draft.created"])
        assert delete_endpoint(ep.id) is True
        assert get_endpoint(ep.id) is None
        assert delete_endpoint("nonexistent") is False

    def test_invalid_event_type_rejected(self):
        from webhooks import create_endpoint
        with pytest.raises(ValueError, match="Unknown event type"):
            create_endpoint("t1", "https://x.com", ["invalid.event"])


# =========================================================================
# Event Dispatch
# =========================================================================
class TestDispatch:
    def test_dispatch_to_matching_endpoint(self):
        from webhooks import create_endpoint, dispatch_event
        create_endpoint("t1", "https://a.com", ["draft.created"])
        deliveries = dispatch_event("draft.created", "t1", {"draft_id": "d-001"})
        assert len(deliveries) == 1
        assert deliveries[0].success is True
        assert deliveries[0].event_type == "draft.created"

    def test_dispatch_skips_non_matching_events(self):
        from webhooks import create_endpoint, dispatch_event
        create_endpoint("t1", "https://a.com", ["draft.updated"])
        deliveries = dispatch_event("draft.created", "t1", {"draft_id": "d-001"})
        assert len(deliveries) == 0

    def test_dispatch_skips_other_tenants(self):
        from webhooks import create_endpoint, dispatch_event
        create_endpoint("t2", "https://a.com", ["draft.created"])
        deliveries = dispatch_event("draft.created", "t1", {"draft_id": "d-001"})
        assert len(deliveries) == 0

    def test_dispatch_skips_inactive_endpoints(self):
        from webhooks import create_endpoint, update_endpoint, dispatch_event
        ep = create_endpoint("t1", "https://a.com", ["draft.created"])
        update_endpoint(ep.id, active=False)
        deliveries = dispatch_event("draft.created", "t1", {"draft_id": "d-001"})
        assert len(deliveries) == 0

    def test_dispatch_to_multiple_endpoints(self):
        from webhooks import create_endpoint, dispatch_event
        create_endpoint("t1", "https://a.com", ["draft.created"])
        create_endpoint("t1", "https://b.com", ["draft.created", "draft.updated"])
        deliveries = dispatch_event("draft.created", "t1", {"draft_id": "d-001"})
        assert len(deliveries) == 2


# =========================================================================
# Delivery Log
# =========================================================================
class TestDeliveryLog:
    def test_deliveries_recorded(self):
        from webhooks import create_endpoint, dispatch_event, get_deliveries
        ep = create_endpoint("t1", "https://a.com", ["draft.created"])
        dispatch_event("draft.created", "t1", {"draft_id": "d-001"})
        deliveries = get_deliveries(endpoint_id=ep.id)
        assert len(deliveries) == 1
        assert deliveries[0].payload["type"] == "draft.created"

    def test_delivery_limit(self):
        from webhooks import create_endpoint, dispatch_event, get_deliveries
        ep = create_endpoint("t1", "https://a.com", ["draft.created"])
        for i in range(10):
            dispatch_event("draft.created", "t1", {"i": i})
        assert len(get_deliveries(endpoint_id=ep.id, limit=5)) == 5


# =========================================================================
# Test Endpoint
# =========================================================================
class TestTestEndpoint:
    def test_sends_test_delivery(self):
        from webhooks import create_endpoint, test_endpoint
        ep = create_endpoint("t1", "https://a.com", ["draft.created"])
        delivery = test_endpoint(ep.id)
        assert delivery.success is True
        assert delivery.event_type == "test"

    def test_nonexistent_endpoint_raises(self):
        from webhooks import test_endpoint
        with pytest.raises(ValueError, match="not found"):
            test_endpoint("nonexistent")


# =========================================================================
# Event Log
# =========================================================================
class TestEventLog:
    def test_events_recorded(self):
        from webhooks import create_endpoint, dispatch_event, get_events
        create_endpoint("t1", "https://a.com", ["draft.created"])
        dispatch_event("draft.created", "t1", {"draft_id": "d-001"})
        events = get_events(tenant_id="t1")
        assert len(events) == 1
        assert events[0].event_type == "draft.created"


# =========================================================================
# API Endpoints
# =========================================================================
class TestAPIEndpoints:
    def test_webhook_endpoints_exist(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert '"/webhooks"' in src
        assert "async def create_webhook" in src
        assert "async def list_webhooks" in src
        assert "async def delete_webhook" in src
        assert "async def test_webhook" in src
        assert "async def list_deliveries" in src

    def test_event_types_defined(self):
        from webhooks import EVENT_TYPES
        assert "draft.created" in EVENT_TYPES
        assert "draft.updated" in EVENT_TYPES
        assert "document.uploaded" in EVENT_TYPES
        assert "document.ocr_complete" in EVENT_TYPES
        assert "plan.upgraded" in EVENT_TYPES
