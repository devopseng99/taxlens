"""Tests for multi-tenant context middleware and auth."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestAuth:

    @pytest.mark.asyncio
    async def test_require_auth_anonymous_when_disabled(self):
        """Auth returns 'anonymous' when neither Dolt nor env keys are configured."""
        with patch("auth.DOLT_ENABLED", False), \
             patch("auth.AUTH_ENABLED", False):
            from auth import require_auth
            mock_request = MagicMock()
            result = await require_auth(mock_request, None)
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_require_auth_dolt_with_tenant(self):
        """Auth succeeds when Dolt is enabled and tenant_id is set."""
        with patch("auth.DOLT_ENABLED", True):
            from auth import require_auth
            mock_request = MagicMock()
            mock_request.state.tenant_id = "tenant123"
            result = await require_auth(mock_request, "tlk_test")
            assert result == "tlk_test"

    @pytest.mark.asyncio
    async def test_require_auth_dolt_no_tenant_401(self):
        """Auth raises 401 when Dolt is enabled but no key provided."""
        with patch("auth.DOLT_ENABLED", True):
            from auth import require_auth
            mock_request = MagicMock()
            mock_request.state.tenant_id = None
            with pytest.raises(Exception) as exc_info:
                await require_auth(mock_request, None)
            assert "401" in str(exc_info.value.status_code)

    @pytest.mark.asyncio
    async def test_require_admin_success(self):
        with patch("auth.ADMIN_KEY", "secret_admin_key"):
            from auth import require_admin
            mock_request = MagicMock()
            mock_request.headers = {"X-Admin-Key": "secret_admin_key"}
            result = await require_admin(mock_request)
            assert result == "admin"

    @pytest.mark.asyncio
    async def test_require_admin_wrong_key(self):
        with patch("auth.ADMIN_KEY", "secret_admin_key"):
            from auth import require_admin
            mock_request = MagicMock()
            mock_request.headers = {"X-Admin-Key": "wrong"}
            with pytest.raises(Exception) as exc_info:
                await require_admin(mock_request)
            assert "403" in str(exc_info.value.status_code)

    def test_get_tenant_id_default_mode(self):
        with patch("auth.DOLT_ENABLED", False):
            from auth import get_tenant_id
            mock_request = MagicMock()
            mock_request.state.tenant_id = None
            result = get_tenant_id(mock_request)
            assert result == "default"

    def test_get_tenant_id_from_state(self):
        with patch("auth.DOLT_ENABLED", True):
            from auth import get_tenant_id
            mock_request = MagicMock()
            mock_request.state.tenant_id = "t123"
            result = get_tenant_id(mock_request)
            assert result == "t123"


class TestApiKeyGeneration:

    def test_key_format(self):
        from auth import generate_api_key
        key = generate_api_key()
        assert key.startswith("tlk_")
        assert len(key) > 20
