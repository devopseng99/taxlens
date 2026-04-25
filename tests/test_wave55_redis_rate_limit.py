"""Wave 55 tests — Redis-backed rate limiting with in-memory fallback."""

import sys, os, time
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Redis client module
# =========================================================================
class TestRedisClient:
    def test_redis_client_importable(self):
        from redis_client import get_redis, is_available, health_check, close
        assert callable(get_redis)
        assert callable(is_available)
        assert callable(health_check)
        assert callable(close)

    def test_lua_scripts_defined(self):
        from redis_client import TOKEN_BUCKET_LUA, SLIDING_COUNTER_LUA, IP_SLIDING_WINDOW_LUA
        assert "KEYS[1]" in TOKEN_BUCKET_LUA
        assert "KEYS[1]" in SLIDING_COUNTER_LUA
        assert "KEYS[1]" in IP_SLIDING_WINDOW_LUA

    def test_redis_url_default_empty(self):
        from redis_client import REDIS_URL
        # In test env, no REDIS_URL set
        assert REDIS_URL == "" or isinstance(REDIS_URL, str)

    @pytest.mark.asyncio
    async def test_get_redis_returns_none_without_url(self):
        with patch("redis_client.REDIS_URL", ""):
            from redis_client import get_redis
            import redis_client
            redis_client._pool = None
            redis_client._available = None
            redis_client.REDIS_URL = ""
            r = await get_redis()
            assert r is None

    @pytest.mark.asyncio
    async def test_health_check_disabled(self):
        from redis_client import health_check
        with patch("redis_client.REDIS_URL", ""):
            import redis_client
            redis_client.REDIS_URL = ""
            result = await health_check()
            assert result["redis_enabled"] is False

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        from redis_client import close
        import redis_client
        redis_client._pool = None
        await close()  # Should not raise


# =========================================================================
# TokenBucket (in-memory — unchanged API)
# =========================================================================
class TestTokenBucket:
    def test_consume_allowed(self):
        from rate_limiter import TokenBucket
        b = TokenBucket(capacity=10, rate=1.0, tokens=10)
        assert b.consume() is True
        assert b.tokens < 10

    def test_consume_denied(self):
        from rate_limiter import TokenBucket
        b = TokenBucket(capacity=10, rate=1.0, tokens=0)
        b.last_refill = time.monotonic()
        assert b.consume() is False

    def test_retry_after(self):
        from rate_limiter import TokenBucket
        b = TokenBucket(capacity=10, rate=1.0, tokens=0)
        b.last_refill = time.monotonic()
        assert b.retry_after > 0


# =========================================================================
# DailyCounter (in-memory — unchanged API)
# =========================================================================
class TestDailyCounter:
    def test_check_allowed(self):
        from rate_limiter import DailyCounter
        c = DailyCounter(limit=5, count=0)
        assert c.check() is True

    def test_check_at_limit(self):
        from rate_limiter import DailyCounter
        c = DailyCounter(limit=5, count=5)
        from datetime import datetime, timezone
        c.reset_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert c.check() is False

    def test_increment(self):
        from rate_limiter import DailyCounter
        c = DailyCounter(limit=10, count=0)
        c.increment()
        assert c.count == 1


# =========================================================================
# RateLimiter — in-memory fallback (no Redis)
# =========================================================================
class TestRateLimiterFallback:
    @pytest.mark.asyncio
    async def test_check_api_rate_without_redis(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter()
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=None):
            allowed, headers = await rl.check_api_rate("tenant1")
            assert allowed is True
            assert "X-RateLimit-Limit" in headers

    @pytest.mark.asyncio
    async def test_check_computation_without_redis(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter()
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=None):
            allowed, remaining = await rl.check_computation("tenant1")
            assert allowed is True
            assert remaining >= 0

    @pytest.mark.asyncio
    async def test_check_ocr_without_redis(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter()
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=None):
            allowed, remaining = await rl.check_ocr("tenant1")
            assert allowed is True

    @pytest.mark.asyncio
    async def test_check_agent_without_redis(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter()
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=None):
            allowed, remaining = await rl.check_agent("tenant1")
            assert allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_denied_at_capacity(self):
        from rate_limiter import RateLimiter, PLAN_DEFAULTS
        rl = RateLimiter()
        rl._plans_cache["t1"] = PLAN_DEFAULTS["free"]  # 10 rpm
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=None):
            # Exhaust the bucket
            for _ in range(15):
                await rl.check_api_rate("t1")
            allowed, headers = await rl.check_api_rate("t1")
            assert allowed is False
            assert "Retry-After" in headers


# =========================================================================
# RateLimiter — Redis path (mocked)
# =========================================================================
class TestRateLimiterRedis:
    @pytest.mark.asyncio
    async def test_check_api_rate_with_redis(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter()
        mock_redis = MagicMock()
        mock_script = AsyncMock(return_value=[1, "29.5"])  # allowed, tokens
        mock_redis.register_script = MagicMock(return_value=mock_script)
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=mock_redis):
            allowed, headers = await rl.check_api_rate("tenant1")
            assert allowed is True
            assert headers["X-RateLimit-Remaining"] == "29"

    @pytest.mark.asyncio
    async def test_check_api_rate_redis_denied(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter()
        mock_redis = MagicMock()
        mock_script = AsyncMock(return_value=[0, "0.0"])  # denied
        mock_redis.register_script = MagicMock(return_value=mock_script)
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=mock_redis):
            allowed, headers = await rl.check_api_rate("tenant1")
            assert allowed is False
            assert "Retry-After" in headers

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter()
        mock_redis = MagicMock()
        mock_script = AsyncMock(side_effect=Exception("Redis down"))
        mock_redis.register_script = MagicMock(return_value=mock_script)
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=mock_redis):
            # Should not raise — falls back to in-memory
            allowed, headers = await rl.check_api_rate("tenant1")
            assert isinstance(allowed, bool)
            assert "X-RateLimit-Limit" in headers

    @pytest.mark.asyncio
    async def test_counter_with_redis(self):
        from rate_limiter import RateLimiter
        rl = RateLimiter()
        mock_redis = MagicMock()
        mock_script = AsyncMock(return_value=[1, 49])  # allowed, remaining
        mock_redis.register_script = MagicMock(return_value=mock_script)
        with patch.object(rl, "_get_redis", new_callable=AsyncMock, return_value=mock_redis):
            allowed, remaining = await rl.check_computation("tenant1")
            assert allowed is True
            assert remaining == 49


# =========================================================================
# IPRateLimiter
# =========================================================================
class TestIPRateLimiter:
    def test_sync_check_allowed(self):
        from rate_limiter import IPRateLimiter
        ipr = IPRateLimiter()
        allowed, headers = ipr.check("10.0.0.1", 60)
        assert allowed is True

    def test_sync_check_at_limit(self):
        from rate_limiter import IPRateLimiter
        ipr = IPRateLimiter()
        for _ in range(65):
            ipr.check("10.0.0.2", 60)
        allowed, headers = ipr.check("10.0.0.2", 60)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_async_check_no_redis(self):
        from rate_limiter import IPRateLimiter
        ipr = IPRateLimiter()
        with patch.object(ipr, "_get_redis", new_callable=AsyncMock, return_value=None):
            allowed, headers = await ipr.check_async("10.0.0.3", 60)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_async_check_with_redis(self):
        from rate_limiter import IPRateLimiter
        ipr = IPRateLimiter()
        mock_redis = MagicMock()
        mock_script = AsyncMock(return_value=[1, 59])  # allowed, remaining
        mock_redis.register_script = MagicMock(return_value=mock_script)
        with patch.object(ipr, "_get_redis", new_callable=AsyncMock, return_value=mock_redis):
            allowed, headers = await ipr.check_async("10.0.0.4", 60)
            assert allowed is True
            assert headers["X-RateLimit-Remaining"] == "59"


# =========================================================================
# Plan defaults & tier features (unchanged)
# =========================================================================
class TestPlanDefaults:
    def test_all_plans_present(self):
        from rate_limiter import PLAN_DEFAULTS
        assert set(PLAN_DEFAULTS.keys()) == {"free", "starter", "professional", "enterprise"}

    def test_tier_features_present(self):
        from rate_limiter import TIER_FEATURES
        assert set(TIER_FEATURES.keys()) == {"free", "starter", "professional", "enterprise"}

    def test_free_plan_limits(self):
        from rate_limiter import PLAN_DEFAULTS
        free = PLAN_DEFAULTS["free"]
        assert free["api_calls_per_minute"] == 10
        assert free["computations_per_day"] == 5


# =========================================================================
# K8s manifests
# =========================================================================
class TestK8sManifests:
    def test_redis_statefulset_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "charts",
                            "taxlens-db", "templates", "redis-statefulset.yaml")
        assert os.path.exists(path)
        content = open(path).read()
        assert "taxlens-redis" in content
        assert "redis:7-alpine" in content
        assert "maxmemory" in content

    def test_redis_service_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "charts",
                            "taxlens-db", "templates", "redis-service.yaml")
        assert os.path.exists(path)
        content = open(path).read()
        assert "6379" in content

    def test_version_updated(self):
        main_path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(main_path).read()
        version = "3.34.0"
        count = src.count(f'"{version}"')
        assert count >= 2, f"Expected {version} in 2+ places, found {count}"
