"""Wave 72 tests — Stripe Live Mode Activation."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


@pytest.fixture(autouse=True)
def clean_usage():
    from stripe_live import reset_usage
    reset_usage()
    yield
    reset_usage()


# =========================================================================
# Live Products
# =========================================================================
class TestLiveProducts:
    def test_three_tiers(self):
        from stripe_live import LIVE_PRODUCTS
        assert "starter" in LIVE_PRODUCTS
        assert "professional" in LIVE_PRODUCTS
        assert "enterprise" in LIVE_PRODUCTS

    def test_starter_price(self):
        from stripe_live import LIVE_PRODUCTS
        assert LIVE_PRODUCTS["starter"].price_monthly == 2900  # $29

    def test_professional_price(self):
        from stripe_live import LIVE_PRODUCTS
        assert LIVE_PRODUCTS["professional"].price_monthly == 9900  # $99

    def test_enterprise_price(self):
        from stripe_live import LIVE_PRODUCTS
        assert LIVE_PRODUCTS["enterprise"].price_monthly == 29900  # $299

    def test_products_have_features(self):
        from stripe_live import LIVE_PRODUCTS
        for tier, product in LIVE_PRODUCTS.items():
            assert len(product.features) >= 3


# =========================================================================
# Metered Usage
# =========================================================================
class TestMeteredUsage:
    def test_record_usage(self):
        from stripe_live import record_metered_usage, get_tenant_usage_summary
        record_metered_usage("t1", "computations", 3)
        summary = get_tenant_usage_summary("t1")
        assert summary["computations"] == 3

    def test_multiple_metrics(self):
        from stripe_live import record_metered_usage, get_tenant_usage_summary
        record_metered_usage("t1", "computations", 5)
        record_metered_usage("t1", "ocr_pages", 10)
        record_metered_usage("t1", "api_calls", 100)
        summary = get_tenant_usage_summary("t1")
        assert summary == {"computations": 5, "ocr_pages": 10, "api_calls": 100}

    def test_tenant_isolation(self):
        from stripe_live import record_metered_usage, get_tenant_usage_summary
        record_metered_usage("t1", "computations", 5)
        record_metered_usage("t2", "computations", 10)
        assert get_tenant_usage_summary("t1")["computations"] == 5
        assert get_tenant_usage_summary("t2")["computations"] == 10


# =========================================================================
# Revenue Metrics
# =========================================================================
class TestRevenueMetrics:
    def test_empty_subscribers(self):
        from stripe_live import compute_revenue_metrics
        metrics = compute_revenue_metrics([])
        assert metrics.total_subscribers == 0
        assert metrics.mrr == 0.0

    def test_single_subscriber(self):
        from stripe_live import compute_revenue_metrics
        metrics = compute_revenue_metrics([
            {"tenant_id": "t1", "tier": "starter", "status": "active"},
        ])
        assert metrics.total_subscribers == 1
        assert metrics.mrr == 29.0
        assert metrics.arr == 348.0

    def test_mixed_tiers(self):
        from stripe_live import compute_revenue_metrics
        metrics = compute_revenue_metrics([
            {"tenant_id": "t1", "tier": "starter", "status": "active"},
            {"tenant_id": "t2", "tier": "professional", "status": "active"},
            {"tenant_id": "t3", "tier": "enterprise", "status": "active"},
        ])
        assert metrics.total_subscribers == 3
        assert metrics.mrr == 29.0 + 99.0 + 299.0
        assert metrics.subscribers_by_tier == {"starter": 1, "professional": 1, "enterprise": 1}

    def test_inactive_excluded(self):
        from stripe_live import compute_revenue_metrics
        metrics = compute_revenue_metrics([
            {"tenant_id": "t1", "tier": "starter", "status": "active"},
            {"tenant_id": "t2", "tier": "professional", "status": "canceled"},
        ])
        assert metrics.total_subscribers == 1
        assert metrics.mrr == 29.0

    def test_churn_rate(self):
        from stripe_live import compute_revenue_metrics
        metrics = compute_revenue_metrics(
            [{"tenant_id": "t1", "tier": "starter", "status": "active"}] * 9,
            churned_count=1,
        )
        assert abs(metrics.churn_rate - 0.1) < 0.01


# =========================================================================
# Billing State Transitions
# =========================================================================
class TestBillingTransitions:
    def test_valid_transitions(self):
        from stripe_live import validate_billing_transition
        assert validate_billing_transition("free", "active") is True
        assert validate_billing_transition("active", "canceled") is True
        assert validate_billing_transition("canceled", "active") is True

    def test_invalid_transitions(self):
        from stripe_live import validate_billing_transition
        assert validate_billing_transition("free", "past_due") is False
        assert validate_billing_transition("trialing", "downgraded") is False

    def test_upgrade_downgrade(self):
        from stripe_live import validate_billing_transition
        assert validate_billing_transition("active", "downgraded") is True
        assert validate_billing_transition("downgraded", "active") is True


# =========================================================================
# API Endpoint
# =========================================================================
class TestEndpoint:
    def test_revenue_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(path).read()
        assert "/admin/revenue" in src
        assert "async def revenue_dashboard" in src
