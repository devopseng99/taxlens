"""Tests for admin provisioning API (PostgREST backend)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestCreateTenant:

    @pytest.mark.asyncio
    async def test_create_tenant_success(self):
        """Tenant creation returns tenant, user, and API key."""
        from admin_routes import create_tenant, CreateTenantRequest

        mock_postgrest = MagicMock()
        mock_postgrest.get = AsyncMock(return_value=[])  # slug check — no existing
        mock_postgrest.create = AsyncMock(side_effect=[
            {"id": "t1", "name": "Test Co", "slug": "test-co", "plan_tier": "starter", "status": "active"},
            {"id": "u1", "tenant_id": "t1", "username": "admin", "role": "admin"},
            {"id": "k1"},  # api_keys create
        ])
        mock_postgrest.mint_jwt = MagicMock(return_value="fake-token")

        with patch("admin_routes.DB_ENABLED", True), \
             patch("admin_routes.postgrest", mock_postgrest), \
             patch("admin_routes.STORAGE_ROOT", MagicMock()):

            req = CreateTenantRequest(name="Test Co", slug="test-co")
            mock_request = MagicMock()
            mock_request.state.db_token = "fake-token"

            result = await create_tenant(req, mock_request, "admin")

            assert result["tenant"]["name"] == "Test Co"
            assert result["api_key"]["key"].startswith("tlk_")

    @pytest.mark.asyncio
    async def test_create_tenant_duplicate_slug(self):
        from admin_routes import create_tenant, CreateTenantRequest

        mock_postgrest = MagicMock()
        mock_postgrest.get = AsyncMock(return_value=[{"id": "existing"}])
        mock_postgrest.mint_jwt = MagicMock(return_value="fake-token")

        with patch("admin_routes.DB_ENABLED", True), \
             patch("admin_routes.postgrest", mock_postgrest):

            req = CreateTenantRequest(name="Dupe", slug="existing-slug")
            mock_request = MagicMock()
            mock_request.state.db_token = "fake-token"

            with pytest.raises(Exception) as exc_info:
                await create_tenant(req, mock_request, "admin")
            assert "409" in str(exc_info.value.status_code)

    @pytest.mark.asyncio
    async def test_create_tenant_db_disabled(self):
        from admin_routes import create_tenant, CreateTenantRequest

        with patch("admin_routes.DB_ENABLED", False):
            req = CreateTenantRequest(name="Test", slug="test")
            mock_request = MagicMock()
            with pytest.raises(Exception) as exc_info:
                await create_tenant(req, mock_request, "admin")
            assert "503" in str(exc_info.value.status_code)


class TestTenantStats:

    @pytest.mark.asyncio
    async def test_get_stats(self):
        from admin_routes import get_tenant_stats

        mock_postgrest = MagicMock()
        mock_postgrest.get_one = AsyncMock(return_value={"id": "t1"})
        mock_postgrest.rpc = AsyncMock(return_value=[{
            "users": 3, "drafts": 10, "documents": 5, "plaid_items": 1,
        }])
        mock_postgrest.mint_jwt = MagicMock(return_value="fake-token")

        with patch("admin_routes.DB_ENABLED", True), \
             patch("admin_routes.postgrest", mock_postgrest):
            mock_request = MagicMock()
            mock_request.state.db_token = "fake-token"
            result = await get_tenant_stats("t1", mock_request, "admin")
            assert result["users"] == 3
            assert result["drafts"] == 10


class TestOAuthClientManagement:

    @pytest.mark.asyncio
    async def test_create_oauth_client(self):
        from admin_routes import create_oauth_client, CreateOAuthClientRequest

        mock_postgrest = MagicMock()
        mock_postgrest.create = AsyncMock(return_value={
            "client_id": "c1", "tenant_id": "t1",
            "client_name": "My App",
        })
        mock_postgrest.mint_jwt = MagicMock(return_value="fake-token")

        with patch("admin_routes.DB_ENABLED", True), \
             patch("admin_routes.postgrest", mock_postgrest):

            req = CreateOAuthClientRequest(
                client_name="My App",
                redirect_uris=["http://localhost/cb"],
            )
            mock_request = MagicMock()
            mock_request.state.db_token = "fake-token"
            result = await create_oauth_client("t1", req, mock_request, "admin")
            assert "client_id" in result
