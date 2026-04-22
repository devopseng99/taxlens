"""Unit tests for TaxLens API key authentication.

Run: PYTHONPATH=app pytest tests/test_auth.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest


from unittest.mock import MagicMock


def _mock_request(tenant_id=None):
    """Create a mock Request with state attributes."""
    req = MagicMock()
    req.state.tenant_id = tenant_id
    req.state.tenant_slug = None
    req.state.user_id = None
    return req


class TestAuthDisabled:
    """When TAXLENS_API_KEYS is not set, auth is disabled."""

    def test_require_auth_returns_anonymous(self):
        # Clear keys and reimport
        os.environ.pop("TAXLENS_API_KEYS", None)
        # Force reimport to pick up env change
        import importlib
        import auth
        importlib.reload(auth)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            auth.require_auth(_mock_request(), None))
        assert result == "anonymous"

    def test_auth_enabled_flag(self):
        os.environ.pop("TAXLENS_API_KEYS", None)
        import importlib
        import auth
        importlib.reload(auth)
        assert auth.AUTH_ENABLED is False


class TestAuthEnabled:
    """When TAXLENS_API_KEYS is set, auth validates keys."""

    def setup_method(self):
        os.environ["TAXLENS_API_KEYS"] = "test-key-1,test-key-2"
        import importlib
        import auth
        importlib.reload(auth)
        self.auth = auth

    def teardown_method(self):
        os.environ.pop("TAXLENS_API_KEYS", None)

    def test_auth_enabled(self):
        assert self.auth.AUTH_ENABLED is True

    def test_valid_key(self):
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            self.auth.require_auth(_mock_request(), "test-key-1"))
        assert result == "test-key-1"

    def test_valid_key_2(self):
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            self.auth.require_auth(_mock_request(), "test-key-2"))
        assert result == "test-key-2"

    def test_invalid_key(self):
        import asyncio
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(
                self.auth.require_auth(_mock_request(), "bad-key"))
        assert exc.value.status_code == 403

    def test_missing_key(self):
        import asyncio
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(
                self.auth.require_auth(_mock_request(), None))
        assert exc.value.status_code == 401


class TestKeyGeneration:
    def test_generate_key_format(self):
        import auth
        key = auth.generate_api_key()
        assert key.startswith("tlk_")
        assert len(key) > 40  # urlsafe(32) = 43 chars + prefix

    def test_generate_key_unique(self):
        import auth
        keys = {auth.generate_api_key() for _ in range(100)}
        assert len(keys) == 100  # All unique
