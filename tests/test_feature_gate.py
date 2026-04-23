"""Tests for feature gate middleware and tier feature definitions."""

import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from rate_limiter import PLAN_DEFAULTS, TIER_FEATURES
from billing import PLAN_TIERS


class TestTierFeatureDefinitions:
    """Test that TIER_FEATURES and PLAN_DEFAULTS are consistent."""

    def test_free_tier_exists_in_plan_defaults(self):
        assert "free" in PLAN_DEFAULTS

    def test_free_tier_exists_in_plan_tiers(self):
        assert "free" in PLAN_TIERS
        assert PLAN_TIERS["free"]["price"] == 0

    def test_all_plan_tiers_have_features(self):
        for tier in PLAN_TIERS:
            assert tier in TIER_FEATURES, f"Missing TIER_FEATURES for {tier}"

    def test_all_plan_tiers_have_defaults(self):
        for tier in PLAN_TIERS:
            assert tier in PLAN_DEFAULTS, f"Missing PLAN_DEFAULTS for {tier}"

    def test_free_tier_standard_deduction_only(self):
        f = TIER_FEATURES["free"]
        assert f["can_compute_tax"] is True
        assert f["can_upload_documents"] is True
        assert f["can_itemized_deductions"] is False
        assert f["can_schedule_c"] is False
        assert f["can_schedule_d"] is False
        assert f["can_1099_forms"] is False
        assert f["can_multi_state"] is False
        assert f["can_use_mcp"] is False
        assert f["can_use_plaid"] is False
        assert f["can_use_agent"] is False

    def test_free_tier_unlimited_w2(self):
        f = TIER_FEATURES["free"]
        assert f["max_w2_uploads"] is None  # NULL = unlimited
        assert f["allowed_form_types"] == ["W-2"]

    def test_free_tier_single_filing(self):
        f = TIER_FEATURES["free"]
        assert f["max_filings_per_year"] == 1
        assert f["max_users"] == 1

    def test_free_tier_rate_limits(self):
        d = PLAN_DEFAULTS["free"]
        assert d["api_calls_per_minute"] == 10
        assert d["computations_per_day"] == 5
        assert d["ocr_pages_per_month"] == 20
        assert d["agent_messages_per_day"] == 0

    def test_starter_has_1099_but_no_schedule_d(self):
        f = TIER_FEATURES["starter"]
        assert f["can_1099_forms"] is True
        assert f["can_schedule_d"] is False
        assert f["can_multi_state"] is False

    def test_professional_has_all_schedules(self):
        f = TIER_FEATURES["professional"]
        assert f["can_itemized_deductions"] is True
        assert f["can_schedule_c"] is True
        assert f["can_schedule_d"] is True
        assert f["can_1099_forms"] is True
        assert f["can_multi_state"] is True

    def test_enterprise_has_early_access(self):
        f = TIER_FEATURES["enterprise"]
        assert f["early_access_enabled"] is True
        assert f["max_users"] is None  # unlimited

    def test_all_tiers_have_upload(self):
        """NIST/IRS compliance: all tiers must allow document upload."""
        for tier, f in TIER_FEATURES.items():
            assert f["can_upload_documents"] is True, f"{tier} must allow uploads"

    def test_all_tiers_have_tax_compute(self):
        for tier, f in TIER_FEATURES.items():
            assert f["can_compute_tax"] is True, f"{tier} must allow tax compute"


class TestFeatureGateMiddleware:
    """Test the feature gate middleware logic."""

    def test_import(self):
        from middleware.feature_gate import FeatureGateMiddleware, FEATURE_GATES
        assert "can_use_mcp" in FEATURE_GATES.values()

    def test_cache_operations(self):
        from middleware.feature_gate import _cache_put, _cache_get, invalidate_cache
        invalidate_cache()
        _cache_put("test-tenant", {"can_use_mcp": True})
        result = _cache_get("test-tenant")
        assert result is not None
        assert result["can_use_mcp"] is True

        invalidate_cache("test-tenant")
        assert _cache_get("test-tenant") is None

    def test_cache_full_invalidate(self):
        from middleware.feature_gate import _cache_put, _cache_get, invalidate_cache
        _cache_put("t1", {"a": 1})
        _cache_put("t2", {"b": 2})
        invalidate_cache()
        assert _cache_get("t1") is None
        assert _cache_get("t2") is None
