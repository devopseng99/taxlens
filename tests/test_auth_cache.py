"""Unit tests for middleware auth cache."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from middleware.tenant_context import _cache_get, _cache_put, _auth_cache, _AUTH_CACHE_MAX


class TestAuthCache:
    def setup_method(self):
        _auth_cache.clear()

    def test_cache_put_and_get(self):
        data = {"tenant_id": "t1", "tenant_slug": "slug1", "user_id": "u1"}
        _cache_put("hash1", data)
        result = _cache_get("hash1")
        assert result is not None
        assert result["tenant_id"] == "t1"

    def test_cache_miss(self):
        result = _cache_get("nonexistent")
        assert result is None

    def test_cache_expiry(self):
        data = {"tenant_id": "t1"}
        _cache_put("hash2", data)
        # Manually expire the entry
        _auth_cache["hash2"] = (data, time.monotonic() - 120)  # 2 min ago
        result = _cache_get("hash2")
        assert result is None

    def test_cache_lru_eviction(self):
        # Fill cache beyond max
        for i in range(_AUTH_CACHE_MAX + 10):
            _cache_put(f"key_{i}", {"tenant_id": f"t{i}"})
        assert len(_auth_cache) <= _AUTH_CACHE_MAX
        # Oldest entries should be evicted
        assert _cache_get("key_0") is None
        # Newest should still be there
        assert _cache_get(f"key_{_AUTH_CACHE_MAX + 9}") is not None

    def test_cache_refresh_on_access(self):
        data = {"tenant_id": "t1"}
        _cache_put("hash3", data)
        # Access moves to end
        _cache_get("hash3")
        # Verify it's still there
        assert _cache_get("hash3") is not None

    def test_cache_overwrites(self):
        _cache_put("hash4", {"tenant_id": "old"})
        _cache_put("hash4", {"tenant_id": "new"})
        result = _cache_get("hash4")
        assert result["tenant_id"] == "new"
