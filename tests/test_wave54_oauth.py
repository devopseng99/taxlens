"""Wave 54 tests — OAuth 2.0 Token Endpoint (RFC 6749 + PKCE)."""

import sys, os, hashlib, json, time, secrets
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


# =========================================================================
# Module-level imports & helpers
# =========================================================================
def _hash(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()


def _make_client(client_id="cid123", tenant_id="t1", scopes=None,
                 secret_hash=None, status="active"):
    return {
        "client_id": client_id,
        "tenant_id": tenant_id,
        "client_secret_hash": secret_hash or _hash("secret123"),
        "client_name": "Test Client",
        "redirect_uris": ["https://example.com/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "scopes": scopes or ["compute", "drafts", "documents"],
        "status": status,
        "created_at": "2025-01-01T00:00:00+00:00",
    }


def _make_token_row(token_hash, client_id="cid123", tenant_id="t1",
                    token_type="access", scopes=None, expires_at=None,
                    code_challenge=None, redirect_uri=None, user_id=None):
    return {
        "token_hash": token_hash,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "token_type": token_type,
        "scopes": scopes or ["compute", "drafts"],
        "expires_at": expires_at or int(time.time()) + 3600,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256" if code_challenge else None,
        "redirect_uri": redirect_uri,
        "created_at": "2025-01-01T00:00:00+00:00",
    }


# =========================================================================
# Token generation & hashing
# =========================================================================
class TestTokenUtilities:
    def test_hash_deterministic(self):
        from oauth import _hash
        assert _hash("test") == _hash("test")
        assert _hash("a") != _hash("b")

    def test_generate_token_prefix(self):
        from oauth import _generate_token
        t = _generate_token("tla")
        assert t.startswith("tla_")
        assert len(t) > 20

    def test_generate_token_unique(self):
        from oauth import _generate_token
        t1 = _generate_token("tla")
        t2 = _generate_token("tla")
        assert t1 != t2

    def test_valid_scopes_constant(self):
        from oauth import VALID_SCOPES
        assert "compute" in VALID_SCOPES
        assert "drafts" in VALID_SCOPES
        assert "documents" in VALID_SCOPES
        assert "mcp" in VALID_SCOPES
        assert "plaid" in VALID_SCOPES

    def test_ttl_defaults(self):
        from oauth import ACCESS_TOKEN_TTL, REFRESH_TOKEN_TTL, AUTH_CODE_TTL
        assert ACCESS_TOKEN_TTL == 3600
        assert REFRESH_TOKEN_TTL == 2592000
        assert AUTH_CODE_TTL == 600


# =========================================================================
# Client validation
# =========================================================================
class TestClientValidation:
    @pytest.mark.asyncio
    async def test_valid_client(self):
        from oauth import _validate_client
        client = _make_client(secret_hash=_hash("mysecret"))
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[client])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await _validate_client("cid123", "mysecret")
            assert result["client_id"] == "cid123"

    @pytest.mark.asyncio
    async def test_unknown_client_raises(self):
        from oauth import _validate_client
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _validate_client("bad", "secret")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_bad_secret_raises(self):
        from oauth import _validate_client
        client = _make_client(secret_hash=_hash("correct_secret"))
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[client])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _validate_client("cid123", "wrong_secret")
            assert exc_info.value.status_code == 401


# =========================================================================
# Client Credentials Grant
# =========================================================================
class TestClientCredentials:
    @pytest.mark.asyncio
    async def test_basic_flow(self):
        from oauth import _handle_client_credentials
        client = _make_client(secret_hash=_hash("s1"))
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[client])
            mock_pg.create = AsyncMock(return_value={})
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await _handle_client_credentials("cid123", "s1", None)
            assert "access_token" in result
            assert result["token_type"] == "bearer"
            assert "refresh_token" in result
            assert result["expires_in"] == 3600
            assert "scope" in result
            # Two create calls: access + refresh
            assert mock_pg.create.call_count == 2

    @pytest.mark.asyncio
    async def test_scope_filtering(self):
        from oauth import _handle_client_credentials
        client = _make_client(secret_hash=_hash("s1"),
                              scopes=["compute", "drafts"])
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[client])
            mock_pg.create = AsyncMock(return_value={})
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await _handle_client_credentials("cid123", "s1", "compute mcp")
            # mcp not in client scopes → only compute granted
            assert "compute" in result["scope"]
            assert "mcp" not in result["scope"]

    @pytest.mark.asyncio
    async def test_no_valid_scopes_raises(self):
        from oauth import _handle_client_credentials
        client = _make_client(secret_hash=_hash("s1"),
                              scopes=["compute"])
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[client])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _handle_client_credentials("cid123", "s1", "invalid_scope")
            assert exc_info.value.status_code == 400


# =========================================================================
# Authorization Code Grant + PKCE
# =========================================================================
class TestAuthorizationCode:
    @pytest.mark.asyncio
    async def test_basic_code_exchange(self):
        from oauth import _handle_authorization_code
        client = _make_client(secret_hash=_hash("s1"))
        code_row = _make_token_row(
            _hash("mycode"), token_type="code",
            scopes=["compute", "drafts"],
        )
        with patch("oauth.postgrest") as mock_pg:
            # First get: client lookup; second get: code lookup
            mock_pg.get = AsyncMock(side_effect=[[client], [code_row]])
            mock_pg.delete = AsyncMock(return_value=1)
            mock_pg.create = AsyncMock(return_value={})
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await _handle_authorization_code(
                "cid123", "s1", "mycode", None, None)
            assert "access_token" in result
            assert result["token_type"] == "bearer"
            # Code should be deleted
            assert mock_pg.delete.call_count >= 1

    @pytest.mark.asyncio
    async def test_pkce_s256_verification(self):
        from oauth import _handle_authorization_code
        # Generate PKCE pair
        verifier = secrets.token_urlsafe(48)
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()

        client = _make_client(secret_hash=_hash("s1"))
        code_row = _make_token_row(
            _hash("mycode"), token_type="code",
            code_challenge=challenge,
        )
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], [code_row]])
            mock_pg.delete = AsyncMock(return_value=1)
            mock_pg.create = AsyncMock(return_value={})
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await _handle_authorization_code(
                "cid123", "s1", "mycode", None, verifier)
            assert "access_token" in result

    @pytest.mark.asyncio
    async def test_pkce_wrong_verifier_raises(self):
        from oauth import _handle_authorization_code
        challenge = urlsafe_b64encode(
            hashlib.sha256(b"correct_verifier").digest()
        ).rstrip(b"=").decode()

        client = _make_client(secret_hash=_hash("s1"))
        code_row = _make_token_row(
            _hash("mycode"), token_type="code",
            code_challenge=challenge,
        )
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], [code_row]])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _handle_authorization_code(
                    "cid123", "s1", "mycode", None, "wrong_verifier")
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_pkce_missing_verifier_raises(self):
        from oauth import _handle_authorization_code
        challenge = "somechallenge"
        client = _make_client(secret_hash=_hash("s1"))
        code_row = _make_token_row(
            _hash("mycode"), token_type="code",
            code_challenge=challenge,
        )
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], [code_row]])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _handle_authorization_code(
                    "cid123", "s1", "mycode", None, None)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_expired_code_raises(self):
        from oauth import _handle_authorization_code
        client = _make_client(secret_hash=_hash("s1"))
        code_row = _make_token_row(
            _hash("mycode"), token_type="code",
            expires_at=int(time.time()) - 100,  # expired
        )
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], [code_row]])
            mock_pg.delete = AsyncMock(return_value=1)
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _handle_authorization_code(
                    "cid123", "s1", "mycode", None, None)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_redirect_uri_mismatch_raises(self):
        from oauth import _handle_authorization_code
        client = _make_client(secret_hash=_hash("s1"))
        code_row = _make_token_row(
            _hash("mycode"), token_type="code",
            redirect_uri="https://example.com/cb",
        )
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], [code_row]])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _handle_authorization_code(
                    "cid123", "s1", "mycode", "https://wrong.com/cb", None)
            assert exc_info.value.status_code == 400


# =========================================================================
# Refresh Token Grant
# =========================================================================
class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_basic_refresh(self):
        from oauth import _handle_refresh_token
        client = _make_client(secret_hash=_hash("s1"))
        refresh_row = _make_token_row(
            _hash("old_refresh"), token_type="refresh",
            scopes=["compute", "drafts"],
        )
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], [refresh_row]])
            mock_pg.delete = AsyncMock(return_value=1)
            mock_pg.create = AsyncMock(return_value={})
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await _handle_refresh_token("cid123", "s1", "old_refresh", None)
            assert "access_token" in result
            assert "refresh_token" in result
            # Old refresh token deleted (rotation)
            assert mock_pg.delete.call_count >= 1

    @pytest.mark.asyncio
    async def test_scope_narrowing(self):
        from oauth import _handle_refresh_token
        client = _make_client(secret_hash=_hash("s1"))
        refresh_row = _make_token_row(
            _hash("old_refresh"), token_type="refresh",
            scopes=["compute", "drafts", "documents"],
        )
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], [refresh_row]])
            mock_pg.delete = AsyncMock(return_value=1)
            mock_pg.create = AsyncMock(return_value={})
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            result = await _handle_refresh_token("cid123", "s1", "old_refresh", "compute")
            assert "compute" in result["scope"]
            assert "documents" not in result["scope"]

    @pytest.mark.asyncio
    async def test_expired_refresh_raises(self):
        from oauth import _handle_refresh_token
        client = _make_client(secret_hash=_hash("s1"))
        refresh_row = _make_token_row(
            _hash("old_refresh"), token_type="refresh",
            expires_at=int(time.time()) - 100,
        )
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], [refresh_row]])
            mock_pg.delete = AsyncMock(return_value=1)
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _handle_refresh_token("cid123", "s1", "old_refresh", None)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_refresh_raises(self):
        from oauth import _handle_refresh_token
        client = _make_client(secret_hash=_hash("s1"))
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(side_effect=[[client], []])  # no refresh token found
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            with pytest.raises(Exception) as exc_info:
                await _handle_refresh_token("cid123", "s1", "bad_token", None)
            assert exc_info.value.status_code == 400


# =========================================================================
# Authorization Code Creation
# =========================================================================
class TestAuthCodeCreation:
    @pytest.mark.asyncio
    async def test_create_auth_code(self):
        from oauth import create_authorization_code
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.create = AsyncMock(return_value={})
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            code = await create_authorization_code(
                "cid123", "t1", ["compute"],
                redirect_uri="https://example.com/cb",
                code_challenge="abc123", code_challenge_method="S256",
            )
            assert code.startswith("tlc_")
            assert mock_pg.create.call_count == 1
            call_data = mock_pg.create.call_args[0][1]
            assert call_data["token_type"] == "code"
            assert call_data["code_challenge"] == "abc123"

    @pytest.mark.asyncio
    async def test_create_auth_code_rejects_non_s256(self):
        from oauth import create_authorization_code
        with pytest.raises(ValueError, match="S256"):
            await create_authorization_code(
                "cid123", "t1", ["compute"],
                code_challenge_method="plain",
            )


# =========================================================================
# Token Cleanup
# =========================================================================
class TestTokenCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_deletes_expired(self):
        from oauth import cleanup_expired_tokens
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.delete = AsyncMock(return_value=5)
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            count = await cleanup_expired_tokens()
            assert count == 5
            mock_pg.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_expired(self):
        from oauth import cleanup_expired_tokens
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.delete = AsyncMock(return_value=0)
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            count = await cleanup_expired_tokens()
            assert count == 0


# =========================================================================
# Token Scope Validation
# =========================================================================
class TestTokenScopeValidation:
    @pytest.mark.asyncio
    async def test_valid_scope(self):
        from oauth import validate_token_scopes
        row = _make_token_row(_hash("tok"), scopes=["compute", "drafts"])
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[row])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            assert await validate_token_scopes("tok", "compute") is True

    @pytest.mark.asyncio
    async def test_missing_scope(self):
        from oauth import validate_token_scopes
        row = _make_token_row(_hash("tok"), scopes=["compute"])
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[row])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            assert await validate_token_scopes("tok", "plaid") is False

    @pytest.mark.asyncio
    async def test_expired_token_invalid(self):
        from oauth import validate_token_scopes
        row = _make_token_row(_hash("tok"), scopes=["compute"],
                              expires_at=int(time.time()) - 100)
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[row])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            assert await validate_token_scopes("tok", "compute") is False

    @pytest.mark.asyncio
    async def test_unknown_token_invalid(self):
        from oauth import validate_token_scopes
        with patch("oauth.postgrest") as mock_pg:
            mock_pg.get = AsyncMock(return_value=[])
            mock_pg.mint_jwt = MagicMock(return_value="jwt")
            assert await validate_token_scopes("bad", "compute") is False


# =========================================================================
# Middleware Integration
# =========================================================================
class TestMiddlewareIntegration:
    def test_oauth_token_in_tenant_skip_paths(self):
        from middleware.tenant_context import _SKIP_PATHS
        assert "/oauth/token" in _SKIP_PATHS

    def test_main_version_updated(self):
        main_path = os.path.join(os.path.dirname(__file__), "..", "app", "main.py")
        src = open(main_path).read()
        version = "3.33.0"
        count = src.count(f'"{version}"')
        assert count >= 2, f"Expected version {version} in at least 2+ places, found {count}"

    def test_oauth_module_importable(self):
        from oauth import router, create_authorization_code, cleanup_expired_tokens
        from oauth import validate_token_scopes, VALID_SCOPES
        assert router is not None
        assert callable(create_authorization_code)
        assert callable(cleanup_expired_tokens)

    def test_migration_v007_exists(self):
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "app", "db", "flyway", "migrations",
            "V007__oauth_token_indexes.sql")
        assert os.path.exists(migration_path)
        content = open(migration_path).read()
        assert "idx_oauth_tokens_client_expires" in content
        assert "idx_oauth_tokens_type_client" in content
