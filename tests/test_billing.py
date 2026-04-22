"""Tests for billing module — plan tiers, webhook handling, onboarding."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from billing import PLAN_TIERS, STRIPE_METERED_PRICES


class TestPlanTiers:
    """Verify plan tier configuration."""

    def test_all_tiers_defined(self):
        assert "starter" in PLAN_TIERS
        assert "professional" in PLAN_TIERS
        assert "enterprise" in PLAN_TIERS

    def test_tier_has_required_fields(self):
        for tier, info in PLAN_TIERS.items():
            assert "name" in info
            assert "price" in info
            assert "description" in info

    def test_pricing_order(self):
        assert PLAN_TIERS["starter"]["price"] < PLAN_TIERS["professional"]["price"]
        assert PLAN_TIERS["professional"]["price"] < PLAN_TIERS["enterprise"]["price"]


class TestOnboarding:
    """Test the onboarding module."""

    def test_slugify(self):
        from onboarding import _slugify
        assert _slugify("Metro CPA Group") == "metro-cpa-group"
        assert _slugify("test@firm!") == "test-firm"
        assert _slugify("  spaces  ") == "spaces"

    def test_slugify_length_limit(self):
        from onboarding import _slugify
        long_name = "A" * 200
        slug = _slugify(long_name)
        assert len(slug) <= 64

    @pytest.mark.asyncio
    async def test_provision_requires_dolt(self):
        with patch("onboarding.DOLT_ENABLED", False):
            from onboarding import provision_tenant
            with pytest.raises(RuntimeError, match="Dolt required"):
                await provision_tenant("Test Firm")

    @pytest.mark.asyncio
    async def test_deactivate_requires_dolt(self):
        with patch("onboarding.DOLT_ENABLED", False):
            from onboarding import deactivate_tenant
            with pytest.raises(RuntimeError, match="Dolt required"):
                await deactivate_tenant("abc123")


class TestBillingModule:
    """Test billing module helpers."""

    def test_stripe_disabled_by_default(self):
        from billing import STRIPE_ENABLED
        # In test env, STRIPE_SECRET_KEY is empty
        assert not STRIPE_ENABLED

    def test_get_stripe_raises_when_disabled(self):
        from billing import _get_stripe, STRIPE_ENABLED
        if not STRIPE_ENABLED:
            with pytest.raises(RuntimeError, match="Stripe not configured"):
                _get_stripe()


class TestBillingRoutes:
    """Test billing route behavior without Stripe."""

    @pytest.mark.asyncio
    async def test_plans_endpoint(self):
        """Plans endpoint should work without auth."""
        from billing_routes import list_plans
        result = await list_plans()
        assert "plans" in result
        assert "starter" in result["plans"]

    @pytest.mark.asyncio
    async def test_checkout_requires_stripe(self):
        """Checkout should return 503 when Stripe is not configured."""
        from billing_routes import CheckoutRequest
        from fastapi import HTTPException
        with patch("billing_routes.STRIPE_ENABLED", False):
            from billing_routes import checkout
            req = CheckoutRequest(tenant_name="Test", email="test@test.com")
            with pytest.raises(HTTPException) as exc:
                await checkout(req, _admin="admin")
            assert exc.value.status_code == 503


class TestWebhookVerification:
    """Test webhook signature verification."""

    def test_verify_missing_secret_raises(self):
        from billing import verify_webhook_signature
        with patch("billing.STRIPE_ENABLED", True), \
             patch("billing.STRIPE_SECRET_KEY", "sk_test_fake"), \
             patch("billing.STRIPE_WEBHOOK_SECRET", ""):
            with pytest.raises(ValueError, match="STRIPE_WEBHOOK_SECRET"):
                verify_webhook_signature(b"payload", "sig")

    def test_verify_no_stripe_raises(self):
        from billing import verify_webhook_signature
        with patch("billing.STRIPE_ENABLED", False):
            with pytest.raises(RuntimeError):
                verify_webhook_signature(b"payload", "sig")
