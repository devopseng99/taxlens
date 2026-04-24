"""Unit tests for Wave 31 — Stripe Live Mode Safety.

Tests the live mode safety guard, mode detection, and billing status endpoint.

Run: PYTHONPATH=app pytest tests/test_wave31_stripe_live.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest


def _detect_stripe_mode(secret_key: str, confirmed: str) -> tuple[bool, str]:
    """Reproduce the billing.py detection logic for testing."""
    is_live = secret_key.startswith(("sk_live_", "rk_live_"))
    confirmed_bool = confirmed.lower() == "true"
    enabled = bool(secret_key) and (not is_live or confirmed_bool)
    if not enabled:
        mode = "disabled"
    elif is_live:
        mode = "live"
    else:
        mode = "test"
    return enabled, mode


class TestStripeModeDetection:
    """Test STRIPE_MODE detection logic."""

    def test_test_key_detected(self):
        enabled, mode = _detect_stripe_mode("sk_test_abc123", "")
        assert mode == "test"
        assert enabled is True

    def test_restricted_test_key(self):
        enabled, mode = _detect_stripe_mode("rk_test_abc123", "")
        assert mode == "test"
        assert enabled is True

    def test_no_key_disabled(self):
        enabled, mode = _detect_stripe_mode("", "")
        assert mode == "disabled"
        assert enabled is False

    def test_live_key_without_confirmation_disabled(self):
        """Live key present but STRIPE_LIVE_MODE_CONFIRMED not set → disabled."""
        enabled, mode = _detect_stripe_mode("sk_live_abc123", "")
        assert mode == "disabled"
        assert enabled is False

    def test_live_key_with_confirmation_enabled(self):
        """Live key + STRIPE_LIVE_MODE_CONFIRMED=true → live mode active."""
        enabled, mode = _detect_stripe_mode("sk_live_abc123", "true")
        assert mode == "live"
        assert enabled is True

    def test_restricted_live_key_with_confirmation(self):
        enabled, mode = _detect_stripe_mode("rk_live_abc123", "true")
        assert mode == "live"
        assert enabled is True

    def test_live_confirmation_case_insensitive(self):
        enabled, mode = _detect_stripe_mode("sk_live_abc123", "True")
        assert mode == "live"
        assert enabled is True

    def test_live_key_false_confirmation(self):
        enabled, mode = _detect_stripe_mode("sk_live_abc123", "false")
        assert mode == "disabled"
        assert enabled is False

    def test_live_key_random_confirmation(self):
        enabled, mode = _detect_stripe_mode("sk_live_abc123", "yes")
        assert mode == "disabled"
        assert enabled is False


class TestPlanTiers:
    """Verify plan tier configuration."""

    def test_all_tiers_present(self):
        from billing import PLAN_TIERS
        assert "free" in PLAN_TIERS
        assert "starter" in PLAN_TIERS
        assert "professional" in PLAN_TIERS
        assert "enterprise" in PLAN_TIERS

    def test_free_tier_zero_price(self):
        from billing import PLAN_TIERS
        assert PLAN_TIERS["free"]["price"] == 0

    def test_paid_tier_prices(self):
        from billing import PLAN_TIERS
        assert PLAN_TIERS["starter"]["price"] == 2900
        assert PLAN_TIERS["professional"]["price"] == 9900
        assert PLAN_TIERS["enterprise"]["price"] == 29900


class TestBillingStatusResponse:
    """Test the /billing/status response structure."""

    def test_status_response_structure(self):
        from billing import STRIPE_MODE, STRIPE_ENABLED, STRIPE_PRICES, PLAN_TIERS
        configured_prices = {k: bool(v) for k, v in STRIPE_PRICES.items()}
        status = {
            "stripe_enabled": STRIPE_ENABLED,
            "stripe_mode": STRIPE_MODE,
            "prices_configured": configured_prices,
            "all_prices_set": all(configured_prices.values()),
            "plans": list(PLAN_TIERS.keys()),
        }
        assert "stripe_mode" in status
        assert status["stripe_mode"] in ("test", "live", "disabled")
        assert len(status["plans"]) == 4
        assert "free" in status["plans"]
        assert isinstance(status["prices_configured"], dict)
        assert "starter" in status["prices_configured"]
        assert "professional" in status["prices_configured"]
        assert "enterprise" in status["prices_configured"]
