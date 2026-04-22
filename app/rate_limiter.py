"""In-memory token bucket rate limiter per tenant with plan-based limits."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from db.postgrest_client import postgrest, DB_ENABLED

logger = logging.getLogger(__name__)

# Default plan limits
PLAN_DEFAULTS = {
    "starter": {"api_calls_per_minute": 30, "computations_per_day": 50,
                "ocr_pages_per_month": 100, "agent_messages_per_day": 100},
    "professional": {"api_calls_per_minute": 120, "computations_per_day": 500,
                     "ocr_pages_per_month": 1000, "agent_messages_per_day": 500},
    "enterprise": {"api_calls_per_minute": 600, "computations_per_day": 999999,
                   "ocr_pages_per_month": 10000, "agent_messages_per_day": 999999},
}


@dataclass
class TokenBucket:
    """Token bucket for rate limiting. Refills `rate` tokens per second."""
    capacity: float
    rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)

    def consume(self, count: float = 1.0) -> bool:
        """Try to consume `count` tokens. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= count:
            self.tokens -= count
            return True
        return False

    @property
    def retry_after(self) -> float:
        """Seconds until 1 token is available."""
        if self.tokens >= 1:
            return 0.0
        return max(0.0, (1.0 - self.tokens) / self.rate)


@dataclass
class DailyCounter:
    """Simple daily counter that resets at midnight UTC."""
    limit: int
    count: int = 0
    reset_day: str = ""

    def _today(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def check(self) -> bool:
        """Check if under limit. Returns True if allowed."""
        today = self._today()
        if self.reset_day != today:
            self.count = 0
            self.reset_day = today
        return self.count < self.limit

    def increment(self):
        today = self._today()
        if self.reset_day != today:
            self.count = 0
            self.reset_day = today
        self.count += 1

    @property
    def remaining(self) -> int:
        today = self._today()
        if self.reset_day != today:
            return self.limit
        return max(0, self.limit - self.count)


class TenantLimits:
    """All rate limits for a single tenant."""

    def __init__(self, plan: dict):
        rpm = plan.get("api_calls_per_minute", 30)
        self.api_bucket = TokenBucket(capacity=rpm, rate=rpm / 60.0, tokens=rpm)
        self.compute_daily = DailyCounter(limit=plan.get("computations_per_day", 50))
        self.ocr_monthly = DailyCounter(limit=plan.get("ocr_pages_per_month", 100))
        self.agent_daily = DailyCounter(limit=plan.get("agent_messages_per_day", 100))


class RateLimiter:
    """Per-tenant rate limiter with plan-based limits loaded from PostgreSQL."""

    def __init__(self):
        self._tenants: dict[str, TenantLimits] = {}
        self._plans_cache: dict[str, dict] = {}
        self._cache_refresh: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes
        self._lock = asyncio.Lock()

    async def _refresh_plans(self):
        """Load tenant plan limits from PostgreSQL via PostgREST (cached for 5 min)."""
        now = time.monotonic()
        if now - self._cache_refresh < self._cache_ttl:
            return

        if not DB_ENABLED:
            self._cache_refresh = now
            return

        try:
            admin_token = postgrest.mint_jwt("__admin__", role="app_admin")
            rows = await postgrest.get("tenant_plans", token=admin_token)
            for row in rows:
                self._plans_cache[row["tenant_id"]] = {
                    "plan_tier": row["plan_tier"],
                    "api_calls_per_minute": row["api_calls_per_minute"],
                    "computations_per_day": row["computations_per_day"],
                    "ocr_pages_per_month": row["ocr_pages_per_month"],
                    "agent_messages_per_day": row["agent_messages_per_day"],
                }
            self._cache_refresh = now
        except Exception as e:
            logger.warning("Failed to refresh plan limits: %s", e)

    def _get_tenant(self, tenant_id: str) -> TenantLimits:
        """Get or create tenant limits."""
        if tenant_id not in self._tenants:
            plan = self._plans_cache.get(tenant_id, PLAN_DEFAULTS["starter"])
            self._tenants[tenant_id] = TenantLimits(plan)
        return self._tenants[tenant_id]

    async def check_api_rate(self, tenant_id: str) -> tuple[bool, dict]:
        """Check API call rate limit. Returns (allowed, headers)."""
        await self._refresh_plans()
        limits = self._get_tenant(tenant_id)

        allowed = limits.api_bucket.consume()
        plan = self._plans_cache.get(tenant_id, PLAN_DEFAULTS["starter"])
        rpm = plan.get("api_calls_per_minute", 30)

        headers = {
            "X-RateLimit-Limit": str(rpm),
            "X-RateLimit-Remaining": str(max(0, int(limits.api_bucket.tokens))),
            "X-RateLimit-Reset": str(int(time.time() + 60)),
        }
        if not allowed:
            headers["Retry-After"] = str(int(limits.api_bucket.retry_after) + 1)
        return allowed, headers

    async def check_computation(self, tenant_id: str) -> tuple[bool, int]:
        """Check daily computation limit. Returns (allowed, remaining)."""
        await self._refresh_plans()
        limits = self._get_tenant(tenant_id)
        allowed = limits.compute_daily.check()
        if allowed:
            limits.compute_daily.increment()
        return allowed, limits.compute_daily.remaining

    async def check_ocr(self, tenant_id: str) -> tuple[bool, int]:
        """Check monthly OCR page limit. Returns (allowed, remaining)."""
        await self._refresh_plans()
        limits = self._get_tenant(tenant_id)
        allowed = limits.ocr_monthly.check()
        if allowed:
            limits.ocr_monthly.increment()
        return allowed, limits.ocr_monthly.remaining

    async def check_agent(self, tenant_id: str) -> tuple[bool, int]:
        """Check daily agent message limit. Returns (allowed, remaining)."""
        await self._refresh_plans()
        limits = self._get_tenant(tenant_id)
        allowed = limits.agent_daily.check()
        if allowed:
            limits.agent_daily.increment()
        return allowed, limits.agent_daily.remaining

    def get_tenant_usage(self, tenant_id: str) -> dict:
        """Get current usage counters for a tenant."""
        limits = self._tenants.get(tenant_id)
        if not limits:
            return {"api_tokens": 0, "computations_today": 0,
                    "ocr_this_period": 0, "agent_today": 0}
        return {
            "api_tokens_remaining": max(0, int(limits.api_bucket.tokens)),
            "computations_today": limits.compute_daily.count,
            "computations_remaining": limits.compute_daily.remaining,
            "ocr_this_period": limits.ocr_monthly.count,
            "ocr_remaining": limits.ocr_monthly.remaining,
            "agent_today": limits.agent_daily.count,
            "agent_remaining": limits.agent_daily.remaining,
        }


# Singleton
rate_limiter = RateLimiter()
