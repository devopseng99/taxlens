"""Unit tests for PostgREST HTTP client."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestJWTMinting:
    def test_mint_jwt_default_role(self):
        os.environ["DB_JWT_SECRET"] = "test-secret-key-at-least-32-chars-long-for-hs256"
        # Re-import to pick up env var
        import importlib
        from db import postgrest_client
        importlib.reload(postgrest_client)

        token = postgrest_client.postgrest.mint_jwt("tenant-123", "user-456")
        import jwt
        payload = jwt.decode(token, "test-secret-key-at-least-32-chars-long-for-hs256",
                              algorithms=["HS256"])
        assert payload["role"] == "app_tenant"
        assert payload["tenant_id"] == "tenant-123"
        assert payload["user_id"] == "user-456"
        assert payload["exp"] > int(time.time())

    def test_mint_jwt_admin_role(self):
        os.environ["DB_JWT_SECRET"] = "test-secret-key-at-least-32-chars-long-for-hs256"
        import importlib
        from db import postgrest_client
        importlib.reload(postgrest_client)

        token = postgrest_client.postgrest.mint_jwt("__admin__", role="app_admin")
        import jwt
        payload = jwt.decode(token, "test-secret-key-at-least-32-chars-long-for-hs256",
                              algorithms=["HS256"])
        assert payload["role"] == "app_admin"
        assert payload["tenant_id"] == "__admin__"
        assert "user_id" not in payload

    def test_mint_jwt_expiry(self):
        os.environ["DB_JWT_SECRET"] = "test-secret-key-at-least-32-chars-long-for-hs256"
        import importlib
        from db import postgrest_client
        importlib.reload(postgrest_client)

        token = postgrest_client.postgrest.mint_jwt("tenant-1")
        import jwt
        payload = jwt.decode(token, "test-secret-key-at-least-32-chars-long-for-hs256",
                              algorithms=["HS256"])
        # Should expire in ~5 minutes (300s)
        ttl = payload["exp"] - int(time.time())
        assert 290 <= ttl <= 310


class TestAuthHeaders:
    def test_auth_headers_with_token(self):
        from db.postgrest_client import PostgRESTClient
        client = PostgRESTClient()
        headers = client._auth_headers("my-token")
        assert headers == {"Authorization": "Bearer my-token"}

    def test_auth_headers_without_token(self):
        from db.postgrest_client import PostgRESTClient
        client = PostgRESTClient()
        headers = client._auth_headers(None)
        assert headers == {}


class TestDBEnabled:
    def test_db_enabled_when_url_set(self):
        os.environ["POSTGREST_URL"] = "http://localhost:3000"
        import importlib
        from db import postgrest_client
        importlib.reload(postgrest_client)
        assert postgrest_client.DB_ENABLED is True

    def test_db_disabled_when_url_empty(self):
        os.environ.pop("POSTGREST_URL", None)
        import importlib
        from db import postgrest_client
        importlib.reload(postgrest_client)
        assert postgrest_client.DB_ENABLED is False
