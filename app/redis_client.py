"""Redis async client with connection pool and graceful fallback.

When REDIS_URL is set, provides a shared aioredis connection pool.
When unset or Redis is unavailable, all operations gracefully degrade
to in-memory equivalents (callers handle fallback logic).
"""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")

# Lazy-loaded connection pool
_pool = None
_available: Optional[bool] = None


async def _get_pool():
    """Lazy-init the Redis connection pool."""
    global _pool, _available
    if not REDIS_URL:
        _available = False
        return None
    if _pool is not None:
        return _pool
    try:
        import redis.asyncio as aioredis
        _pool = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        # Test connectivity
        await _pool.ping()
        _available = True
        logger.info("Redis connected: %s", REDIS_URL.split("@")[-1] if "@" in REDIS_URL else REDIS_URL)
        return _pool
    except Exception as e:
        logger.warning("Redis unavailable, falling back to in-memory: %s", e)
        _pool = None
        _available = False
        return None


async def get_redis():
    """Get Redis client or None if unavailable."""
    return await _get_pool()


def is_available() -> bool:
    """Check if Redis is configured and was reachable at startup."""
    return _available is True


async def health_check() -> dict:
    """Return Redis health status for /health endpoint."""
    if not REDIS_URL:
        return {"redis_enabled": False}

    r = await get_redis()
    if r is None:
        return {"redis_enabled": True, "redis_ok": False}

    try:
        start = time.monotonic()
        await r.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"redis_enabled": True, "redis_ok": True, "redis_latency_ms": latency_ms}
    except Exception as e:
        return {"redis_enabled": True, "redis_ok": False, "redis_error": str(e)}


async def close():
    """Close Redis connection pool."""
    global _pool, _available
    if _pool:
        try:
            await _pool.aclose()
        except Exception:
            pass
        _pool = None
        _available = None


# --- Lua Scripts for Atomic Rate Limiting ---

# Token bucket: atomic consume + refill
# KEYS[1] = bucket key
# ARGV[1] = capacity, ARGV[2] = rate (tokens/sec), ARGV[3] = now (epoch float), ARGV[4] = count
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local count = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1]) or capacity
local last_refill = tonumber(data[2]) or now

-- Refill
local elapsed = now - last_refill
tokens = math.min(capacity, tokens + elapsed * rate)
local last = now

-- Consume
local allowed = 0
if tokens >= count then
    tokens = tokens - count
    allowed = 1
end

redis.call('HMSET', key, 'tokens', tostring(tokens), 'last_refill', tostring(last))
redis.call('EXPIRE', key, 120)  -- 2 min TTL (auto-cleanup idle buckets)

return {allowed, tostring(tokens)}
"""

# Sliding window counter (daily/monthly)
# KEYS[1] = counter key
# ARGV[1] = limit, ARGV[2] = window_key (e.g. "2026-04-24"), ARGV[3] = increment (0=check, 1=incr)
SLIDING_COUNTER_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_key = ARGV[2]
local do_incr = tonumber(ARGV[3])

local stored_window = redis.call('HGET', key, 'window')
local count = tonumber(redis.call('HGET', key, 'count')) or 0

if stored_window ~= window_key then
    count = 0
    redis.call('HMSET', key, 'window', window_key, 'count', '0')
end

local allowed = 0
if count < limit then
    allowed = 1
    if do_incr == 1 then
        count = count + 1
        redis.call('HSET', key, 'count', tostring(count))
    end
end

redis.call('EXPIRE', key, 90000)  -- 25 hours TTL

local remaining = math.max(0, limit - count)
return {allowed, remaining}
"""

# IP sliding window (sorted set approach)
# KEYS[1] = ip key
# ARGV[1] = window_seconds, ARGV[2] = limit, ARGV[3] = now (epoch)
IP_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Remove expired entries
redis.call('ZREMRANGEBYSCORE', key, '-inf', tostring(now - window))

-- Count current
local count = redis.call('ZCARD', key)

local allowed = 0
if count < limit then
    redis.call('ZADD', key, tostring(now), tostring(now) .. ':' .. tostring(math.random(100000)))
    allowed = 1
end

redis.call('EXPIRE', key, window + 10)

local remaining = math.max(0, limit - count - (1 - allowed))
return {allowed, remaining}
"""
