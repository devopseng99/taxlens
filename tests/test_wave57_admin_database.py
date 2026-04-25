"""Wave 57 tests — Admin Database Explorer + PostgREST OpenAPI Integration."""

import sys, os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Database Explorer — Module Structure
# =========================================================================
class TestDatabaseExplorerConfig:
    def test_db_tables_list_defined(self):
        from admin_routes import DB_TABLES
        assert isinstance(DB_TABLES, list)
        assert "tenants" in DB_TABLES
        assert "oauth_clients" in DB_TABLES
        assert "oauth_tokens" in DB_TABLES
        assert "audit_log" in DB_TABLES

    def test_db_tables_count(self):
        from admin_routes import DB_TABLES
        assert len(DB_TABLES) >= 10

    def test_database_overview_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "admin_routes.py")
        src = open(path).read()
        assert "async def database_overview" in src
        assert '"/database"' in src

    def test_table_detail_endpoint_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "admin_routes.py")
        src = open(path).read()
        assert "async def table_detail" in src
        assert '"/database/{table_name}"' in src


# =========================================================================
# Database Overview — Mocked
# =========================================================================
class TestDatabaseOverview:
    @pytest.mark.asyncio
    async def test_database_overview_returns_tables(self):
        from admin_routes import database_overview, DB_TABLES
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.db_token = "jwt"

        with patch("admin_routes.DB_ENABLED", True), \
             patch("admin_routes.postgrest") as mock_pg:
            mock_pg.count = AsyncMock(return_value=42)
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await database_overview(mock_request, _admin="admin")
            assert result["total_tables"] == len(DB_TABLES)
            assert len(result["tables"]) == len(DB_TABLES)
            assert result["tables"][0]["row_count"] == 42

    @pytest.mark.asyncio
    async def test_database_overview_handles_errors(self):
        from admin_routes import database_overview
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.db_token = "jwt"

        with patch("admin_routes.DB_ENABLED", True), \
             patch("admin_routes.postgrest") as mock_pg:
            mock_pg.count = AsyncMock(side_effect=Exception("table missing"))
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await database_overview(mock_request, _admin="admin")
            # Should still return all tables, with error status
            assert result["tables"][0]["status"].startswith("error")


# =========================================================================
# Table Detail — Mocked
# =========================================================================
class TestTableDetail:
    @pytest.mark.asyncio
    async def test_table_detail_returns_rows(self):
        from admin_routes import table_detail
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.db_token = "jwt"

        sample_rows = [
            {"id": "t1", "name": "Acme", "created_at": "2025-01-01"},
            {"id": "t2", "name": "Beta", "created_at": "2025-01-02"},
        ]
        with patch("admin_routes.DB_ENABLED", True), \
             patch("admin_routes.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=sample_rows)
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await table_detail("tenants", mock_request, limit=10, _admin="admin")
            assert result["table"] == "tenants"
            assert result["columns"] == ["id", "name", "created_at"]
            assert len(result["sample_rows"]) == 2

    @pytest.mark.asyncio
    async def test_table_detail_rejects_unknown_table(self):
        from admin_routes import table_detail
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.db_token = "jwt"

        with patch("admin_routes.DB_ENABLED", True), \
             pytest.raises(Exception) as exc_info:
            await table_detail("secret_table", mock_request, _admin="admin")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_table_detail_empty_table(self):
        from admin_routes import table_detail
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.db_token = "jwt"

        with patch("admin_routes.DB_ENABLED", True), \
             patch("admin_routes.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await table_detail("tenants", mock_request, limit=10, _admin="admin")
            assert result["columns"] == []
            assert result["sample_rows"] == []


# =========================================================================
# Admin Routes Enrichment
# =========================================================================
class TestAdminRoutesEnrichment:
    def test_database_endpoints_have_summaries(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "admin_routes.py")
        src = open(path).read()
        assert 'summary="Database overview"' in src
        assert 'summary="Table detail"' in src

    def test_admin_database_endpoint_has_description(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "admin_routes.py")
        src = open(path).read()
        assert 'description="List all database tables' in src
