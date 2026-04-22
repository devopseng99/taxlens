"""Tests for Dolt repository layer — uses mock connections."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


# --- Tenant Repo ---

class TestTenantRepo:

    @pytest.mark.asyncio
    async def test_create_tenant(self):
        with patch("db.tenant_repo.execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 1
            from db.tenant_repo import create_tenant
            result = await create_tenant("Acme Tax", "acme-tax", "starter")
            assert result["name"] == "Acme Tax"
            assert result["slug"] == "acme-tax"
            assert result["plan"] == "starter"
            assert result["status"] == "active"
            assert len(result["id"]) == 32
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tenant(self):
        mock_row = {"id": "abc123", "name": "Test", "slug": "test", "status": "active"}
        with patch("db.tenant_repo.fetchone", new_callable=AsyncMock, return_value=mock_row):
            from db.tenant_repo import get_tenant
            result = await get_tenant("abc123")
            assert result["name"] == "Test"

    @pytest.mark.asyncio
    async def test_get_tenant_not_found(self):
        with patch("db.tenant_repo.fetchone", new_callable=AsyncMock, return_value=None):
            from db.tenant_repo import get_tenant
            result = await get_tenant("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_list_tenants(self):
        mock_rows = [
            {"id": "1", "name": "A", "slug": "a"},
            {"id": "2", "name": "B", "slug": "b"},
        ]
        with patch("db.tenant_repo.fetchall", new_callable=AsyncMock, return_value=mock_rows):
            from db.tenant_repo import list_tenants
            result = await list_tenants()
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_update_tenant(self):
        with patch("db.tenant_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.tenant_repo import update_tenant
            result = await update_tenant("abc", name="New Name")
            assert result == 1

    @pytest.mark.asyncio
    async def test_get_tenant_stats(self):
        async def mock_fetchone(sql, args):
            return {"cnt": 5}
        with patch("db.tenant_repo.fetchone", side_effect=mock_fetchone):
            from db.tenant_repo import get_tenant_stats
            stats = await get_tenant_stats("abc")
            assert stats["users"] == 5
            assert stats["drafts"] == 5


# --- API Key Repo ---

class TestApiKeyRepo:

    @pytest.mark.asyncio
    async def test_create_key(self):
        with patch("db.api_key_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.api_key_repo import create_key
            result = await create_key("tenant1", name="Test Key")
            assert result["key"].startswith("tlk_")
            assert result["tenant_id"] == "tenant1"
            assert result["name"] == "Test Key"
            assert len(result["key_prefix"]) == 12

    @pytest.mark.asyncio
    async def test_validate_key_valid(self):
        import hashlib
        test_key = "tlk_test123"
        key_hash = hashlib.sha256(test_key.encode()).hexdigest()
        mock_row = {
            "id": "key1", "tenant_id": "t1", "key_hash": key_hash,
            "tenant_slug": "test", "tenant_status": "active",
        }
        with patch("db.api_key_repo.fetchone", new_callable=AsyncMock, return_value=mock_row):
            with patch("db.api_key_repo.execute", new_callable=AsyncMock):
                from db.api_key_repo import validate_key
                result = await validate_key(test_key)
                assert result["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_validate_key_invalid(self):
        with patch("db.api_key_repo.fetchone", new_callable=AsyncMock, return_value=None):
            from db.api_key_repo import validate_key
            result = await validate_key("bad_key")
            assert result is None

    @pytest.mark.asyncio
    async def test_revoke_key(self):
        with patch("db.api_key_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.api_key_repo import revoke_key
            result = await revoke_key("key1")
            assert result == 1


# --- Draft Repo ---

class TestDraftRepo:

    @pytest.mark.asyncio
    async def test_save_draft(self):
        with patch("db.draft_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.draft_repo import save_draft
            result = await save_draft(
                "tenant1", "alice", "single",
                filer_name="Alice",
                result={"total_income": 95000, "agi": 82000, "federal_tax": 11000, "net_refund_or_owed": -500},
            )
            assert result["tenant_id"] == "tenant1"
            assert result["username"] == "alice"
            assert result["total_income"] == 95000

    @pytest.mark.asyncio
    async def test_get_draft(self):
        mock_row = {"id": "d1", "tenant_id": "t1", "filing_status": "single"}
        with patch("db.draft_repo.fetchone", new_callable=AsyncMock, return_value=mock_row):
            from db.draft_repo import get_draft
            result = await get_draft("t1", "d1")
            assert result["filing_status"] == "single"

    @pytest.mark.asyncio
    async def test_list_drafts_by_user(self):
        mock_rows = [{"id": "d1"}, {"id": "d2"}]
        with patch("db.draft_repo.fetchall", new_callable=AsyncMock, return_value=mock_rows):
            from db.draft_repo import list_drafts
            result = await list_drafts("t1", "alice")
            assert len(result) == 2


# --- Document Repo ---

class TestDocumentRepo:

    @pytest.mark.asyncio
    async def test_save_metadata(self):
        with patch("db.document_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.document_repo import save_metadata
            result = await save_metadata(
                "proc1", "t1", "bob", "w2.pdf", "application/pdf",
                1024, "sha256abc", "bob/proc1/w2.pdf",
            )
            assert result["proc_id"] == "proc1"
            assert result["has_ocr"] is False

    @pytest.mark.asyncio
    async def test_mark_ocr_done(self):
        with patch("db.document_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.document_repo import mark_ocr_done
            result = await mark_ocr_done("t1", "proc1", "W-2")
            assert result == 1


# --- OAuth Repo ---

class TestOAuthRepo:

    @pytest.mark.asyncio
    async def test_register_client(self):
        with patch("db.oauth_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.oauth_repo import register_client
            result = await register_client(
                "t1", "My App", ["http://localhost/callback"],
            )
            assert result["client_id"]
            assert result["client_secret"]
            assert result["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_validate_client_secret_valid(self):
        import hashlib
        secret = "test_secret_123"
        mock_row = {
            "client_id": "c1", "client_secret_hash": hashlib.sha256(secret.encode()).hexdigest(),
        }
        with patch("db.oauth_repo.fetchone", new_callable=AsyncMock, return_value=mock_row):
            from db.oauth_repo import validate_client_secret
            result = await validate_client_secret("c1", secret)
            assert result["client_id"] == "c1"

    @pytest.mark.asyncio
    async def test_validate_client_secret_invalid(self):
        mock_row = {"client_id": "c1", "client_secret_hash": "wrong_hash"}
        with patch("db.oauth_repo.fetchone", new_callable=AsyncMock, return_value=mock_row):
            from db.oauth_repo import validate_client_secret
            result = await validate_client_secret("c1", "bad_secret")
            assert result is None

    @pytest.mark.asyncio
    async def test_rotate_secret(self):
        with patch("db.oauth_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.oauth_repo import rotate_client_secret
            result = await rotate_client_secret("c1")
            assert result["client_id"] == "c1"
            assert result["client_secret"]


# --- Plaid Repo ---

class TestPlaidRepo:

    @pytest.mark.asyncio
    async def test_save_item(self):
        with patch("db.plaid_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.plaid_repo import save_item
            result = await save_item("item1", "t1", "alice", "Chase", "encrypted_token")
            assert result["item_id"] == "item1"
            assert result["has_sync"] is False

    @pytest.mark.asyncio
    async def test_update_sync_status(self):
        with patch("db.plaid_repo.execute", new_callable=AsyncMock, return_value=1):
            from db.plaid_repo import update_sync_status
            result = await update_sync_status("t1", "item1")
            assert result == 1
