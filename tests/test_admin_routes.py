"""Tests for admin provisioning API."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestCreateTenant:

    @pytest.mark.asyncio
    async def test_create_tenant_success(self):
        """Tenant creation returns tenant, user, and API key."""
        from admin_routes import create_tenant, CreateTenantRequest

        with patch("admin_routes.DOLT_ENABLED", True), \
             patch("admin_routes.tenant_repo") as mock_tr, \
             patch("admin_routes.user_repo") as mock_ur, \
             patch("admin_routes.api_key_repo") as mock_kr, \
             patch("admin_routes.STORAGE_ROOT", MagicMock()):

            mock_tr.get_tenant_by_slug = AsyncMock(return_value=None)
            mock_tr.create_tenant = AsyncMock(return_value={
                "id": "t1", "name": "Test Co", "slug": "test-co",
                "plan": "starter", "status": "active", "created_at": "2026-01-01",
            })
            mock_ur.create_user = AsyncMock(return_value={
                "id": "u1", "tenant_id": "t1", "username": "admin",
                "role": "admin", "created_at": "2026-01-01",
            })
            mock_kr.create_key = AsyncMock(return_value={
                "id": "k1", "key": "tlk_test123", "key_prefix": "tlk_test1",
                "tenant_id": "t1", "created_at": "2026-01-01",
            })

            req = CreateTenantRequest(name="Test Co", slug="test-co")

            with patch("db.versioning.dolt_commit", new_callable=AsyncMock):
                result = await create_tenant(req, "admin")

            assert result["tenant"]["name"] == "Test Co"
            assert result["api_key"]["key"] == "tlk_test123"

    @pytest.mark.asyncio
    async def test_create_tenant_duplicate_slug(self):
        from admin_routes import create_tenant, CreateTenantRequest

        with patch("admin_routes.DOLT_ENABLED", True), \
             patch("admin_routes.tenant_repo") as mock_tr:

            mock_tr.get_tenant_by_slug = AsyncMock(return_value={"id": "existing"})
            req = CreateTenantRequest(name="Dupe", slug="existing-slug")

            with pytest.raises(Exception) as exc_info:
                await create_tenant(req, "admin")
            assert "409" in str(exc_info.value.status_code)

    @pytest.mark.asyncio
    async def test_create_tenant_dolt_disabled(self):
        from admin_routes import create_tenant, CreateTenantRequest

        with patch("admin_routes.DOLT_ENABLED", False):
            req = CreateTenantRequest(name="Test", slug="test")
            with pytest.raises(Exception) as exc_info:
                await create_tenant(req, "admin")
            assert "503" in str(exc_info.value.status_code)


class TestTenantStats:

    @pytest.mark.asyncio
    async def test_get_stats(self):
        from admin_routes import get_tenant_stats

        with patch("admin_routes.DOLT_ENABLED", True), \
             patch("admin_routes.tenant_repo") as mock_tr:
            mock_tr.get_tenant = AsyncMock(return_value={"id": "t1"})
            mock_tr.get_tenant_stats = AsyncMock(return_value={
                "users": 3, "drafts": 10, "documents": 5, "plaid_items": 1,
            })
            result = await get_tenant_stats("t1", "admin")
            assert result["users"] == 3
            assert result["drafts"] == 10


class TestOAuthClientManagement:

    @pytest.mark.asyncio
    async def test_create_oauth_client(self):
        from admin_routes import create_oauth_client, CreateOAuthClientRequest

        with patch("admin_routes.DOLT_ENABLED", True), \
             patch("admin_routes.oauth_repo") as mock_or:
            mock_or.register_client = AsyncMock(return_value={
                "client_id": "c1", "client_secret": "secret123",
                "tenant_id": "t1", "client_name": "My App",
                "redirect_uris": ["http://localhost/cb"],
                "scopes": ["compute", "drafts"],
                "created_at": "2026-01-01",
            })

            req = CreateOAuthClientRequest(
                client_name="My App",
                redirect_uris=["http://localhost/cb"],
            )
            result = await create_oauth_client("t1", req, "admin")
            assert result["client_id"] == "c1"
            assert "mcp_config" in result

    @pytest.mark.asyncio
    async def test_rotate_oauth_secret(self):
        from admin_routes import rotate_oauth_secret

        with patch("admin_routes.DOLT_ENABLED", True), \
             patch("admin_routes.oauth_repo") as mock_or:
            mock_or.rotate_client_secret = AsyncMock(return_value={
                "client_id": "c1", "client_secret": "new_secret",
            })
            result = await rotate_oauth_secret("t1", "c1", "admin")
            assert result["client_secret"] == "new_secret"
