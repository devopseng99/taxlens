"""Tests for rate limiter — token bucket, daily counters, plan-based limits."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from rate_limiter import TokenBucket, DailyCounter, TenantLimits, RateLimiter, PLAN_DEFAULTS


class TestTokenBucket:
    """Test the token bucket algorithm."""

    def test_initial_capacity(self):
        bucket = TokenBucket(capacity=10, rate=1.0, tokens=10)
        assert bucket.consume(1)

    def test_consume_reduces_tokens(self):
        bucket = TokenBucket(capacity=10, rate=1.0, tokens=5)
        assert bucket.consume(3)
        assert bucket.tokens < 3  # consumed 3 from ~5

    def test_consume_fails_when_empty(self):
        bucket = TokenBucket(capacity=10, rate=1.0, tokens=0)
        bucket.last_refill = time.monotonic()  # Just now, no refill time
        assert not bucket.consume(1)

    def test_refill_over_time(self):
        bucket = TokenBucket(capacity=10, rate=10.0, tokens=0)
        bucket.last_refill = time.monotonic() - 1.0  # 1 second ago
        # After 1 second at rate=10/s, should have ~10 tokens
        assert bucket.consume(5)

    def test_capacity_cap(self):
        bucket = TokenBucket(capacity=10, rate=100.0, tokens=0)
        bucket.last_refill = time.monotonic() - 10.0  # 10 seconds ago
        # 10 * 100 = 1000 but capped at capacity=10
        assert bucket.consume(10)
        assert not bucket.consume(1)

    def test_retry_after(self):
        bucket = TokenBucket(capacity=10, rate=1.0, tokens=0)
        bucket.last_refill = time.monotonic()
        assert bucket.retry_after > 0
        assert bucket.retry_after <= 1.0


class TestDailyCounter:
    """Test the daily counter with midnight reset."""

    def test_initial_state(self):
        counter = DailyCounter(limit=50)
        assert counter.check()
        assert counter.remaining == 50

    def test_increment_and_check(self):
        counter = DailyCounter(limit=3)
        counter.increment()
        counter.increment()
        assert counter.check()  # 2 < 3
        counter.increment()
        assert not counter.check()  # 3 >= 3

    def test_remaining_decreases(self):
        counter = DailyCounter(limit=10)
        counter.increment()
        counter.increment()
        assert counter.remaining == 8

    def test_reset_on_new_day(self):
        counter = DailyCounter(limit=5)
        counter.increment()
        counter.increment()
        counter.reset_day = "2020-01-01"  # Force old day
        assert counter.check()  # New day resets
        assert counter.remaining == 5


class TestTenantLimits:
    """Test composite limits for a tenant."""

    def test_starter_plan(self):
        limits = TenantLimits(PLAN_DEFAULTS["starter"])
        assert limits.api_bucket.capacity == 30
        assert limits.compute_daily.limit == 50
        assert limits.ocr_monthly.limit == 100

    def test_enterprise_plan(self):
        limits = TenantLimits(PLAN_DEFAULTS["enterprise"])
        assert limits.api_bucket.capacity == 600
        assert limits.compute_daily.limit == 999999


class TestRateLimiter:
    """Test the per-tenant rate limiter."""

    @pytest.mark.asyncio
    async def test_check_api_rate_allowed(self):
        with patch("rate_limiter.DB_ENABLED", False):
            rl = RateLimiter()
            allowed, headers = await rl.check_api_rate("tenant1")
            assert allowed
            assert "X-RateLimit-Limit" in headers

    @pytest.mark.asyncio
    async def test_check_api_rate_denied_after_burst(self):
        with patch("rate_limiter.DB_ENABLED", False):
            rl = RateLimiter()
            # Exhaust all tokens (starter = 30 RPM)
            for _ in range(31):
                allowed, headers = await rl.check_api_rate("tenant1")
            # Should be denied now
            assert not allowed
            assert "Retry-After" in headers

    @pytest.mark.asyncio
    async def test_check_computation_limit(self):
        with patch("rate_limiter.DB_ENABLED", False):
            rl = RateLimiter()
            allowed, remaining = await rl.check_computation("tenant1")
            assert allowed
            assert remaining == 49  # 50 - 1

    @pytest.mark.asyncio
    async def test_computation_limit_exhausted(self):
        with patch("rate_limiter.DB_ENABLED", False):
            rl = RateLimiter()
            for _ in range(50):
                await rl.check_computation("tenant1")
            allowed, remaining = await rl.check_computation("tenant1")
            assert not allowed
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_get_tenant_usage(self):
        with patch("rate_limiter.DB_ENABLED", False):
            rl = RateLimiter()
            await rl.check_api_rate("tenant1")
            await rl.check_computation("tenant1")
            usage = rl.get_tenant_usage("tenant1")
            assert "computations_today" in usage
            assert usage["computations_today"] == 1

    @pytest.mark.asyncio
    async def test_separate_tenant_limits(self):
        with patch("rate_limiter.DB_ENABLED", False):
            rl = RateLimiter()
            # Exhaust tenant1 computation
            for _ in range(50):
                await rl.check_computation("tenant1")
            # tenant2 should still be allowed
            allowed, _ = await rl.check_computation("tenant2")
            assert allowed

    def test_plan_defaults_complete(self):
        for tier in ["starter", "professional", "enterprise"]:
            plan = PLAN_DEFAULTS[tier]
            assert "api_calls_per_minute" in plan
            assert "computations_per_day" in plan
            assert "ocr_pages_per_month" in plan
            assert "agent_messages_per_day" in plan
