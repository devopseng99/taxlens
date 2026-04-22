"""PostgREST HTTP client — replaces all Dolt repository modules.

All database access goes through PostgREST REST API. JWT tokens encode
the tenant_id for RLS enforcement at the database level.

Usage:
    from db.postgrest_client import postgrest

    # Anonymous RPC (auth flow)
    result = await postgrest.rpc("validate_api_key", {"p_key_hash": hash})

    # Tenant-scoped CRUD (JWT encodes tenant_id)
    token = postgrest.mint_jwt(tenant_id, user_id)
    rows = await postgrest.get("tax_drafts", {"username": "eq.admin"}, token)
    row = await postgrest.create("tenants", {...}, token)
"""

import json
import logging
import os
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

POSTGREST_URL = os.getenv("POSTGREST_URL", "http://taxlens-postgrest.taxlens-db.svc:3000")
JWT_SECRET = os.getenv("DB_JWT_SECRET", "")

# DB provider: "postgrest" or "disabled" (graceful degradation)
DB_ENABLED = bool(os.getenv("POSTGREST_URL", ""))


def _lazy_jwt():
    """Lazy import PyJWT."""
    import jwt as pyjwt
    return pyjwt


class PostgRESTClient:
    """Async HTTP client for PostgREST with JWT minting."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=POSTGREST_URL,
                timeout=10.0,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def mint_jwt(self, tenant_id: str, user_id: str = None,
                 role: str = "app_tenant") -> str:
        """Mint a short-lived JWT for PostgREST. Encodes role + tenant_id for RLS."""
        pyjwt = _lazy_jwt()
        payload = {
            "role": role,
            "tenant_id": tenant_id,
            "exp": int(time.time()) + 300,  # 5 min TTL
        }
        if user_id:
            payload["user_id"] = user_id
        return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")

    def _auth_headers(self, token: str = None) -> dict:
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def rpc(self, fn: str, params: dict, token: str = None) -> list[dict]:
        """Call a PostgreSQL function via POST /rpc/{fn}."""
        client = await self._get_client()
        headers = self._auth_headers(token)
        resp = await client.post(f"/rpc/{fn}", json=params, headers=headers)
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    async def get(self, table: str, filters: dict = None, token: str = None,
                  select: str = "*", order: str = None, limit: int = None) -> list[dict]:
        """GET /{table}?{filters}&select={select}."""
        client = await self._get_client()
        headers = self._auth_headers(token)
        params = {"select": select}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        resp = await client.get(f"/{table}", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def get_one(self, table: str, filters: dict, token: str = None,
                      select: str = "*") -> Optional[dict]:
        """GET single row. Returns None if not found."""
        client = await self._get_client()
        headers = {
            **self._auth_headers(token),
            "Accept": "application/vnd.pgrst.object+json",
        }
        params = {"select": select, **filters}
        resp = await client.get(f"/{table}", params=params, headers=headers)
        if resp.status_code == 406:  # Not Acceptable = 0 or >1 rows
            return None
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def create(self, table: str, data: dict, token: str = None) -> dict:
        """POST /{table} with Prefer: return=representation."""
        client = await self._get_client()
        headers = {
            **self._auth_headers(token),
            "Prefer": "return=representation",
        }
        resp = await client.post(f"/{table}", json=data, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        return result[0] if isinstance(result, list) and result else result

    async def create_many(self, table: str, rows: list[dict], token: str = None) -> list[dict]:
        """POST multiple rows."""
        client = await self._get_client()
        headers = {
            **self._auth_headers(token),
            "Prefer": "return=representation",
        }
        resp = await client.post(f"/{table}", json=rows, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def update(self, table: str, filters: dict, data: dict,
                     token: str = None) -> list[dict]:
        """PATCH /{table}?{filters} with data."""
        client = await self._get_client()
        headers = {
            **self._auth_headers(token),
            "Prefer": "return=representation",
        }
        resp = await client.patch(f"/{table}", params=filters, json=data, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def delete(self, table: str, filters: dict, token: str = None) -> int:
        """DELETE /{table}?{filters}. Returns count of deleted rows."""
        client = await self._get_client()
        headers = {
            **self._auth_headers(token),
            "Prefer": "return=representation",
        }
        resp = await client.delete(f"/{table}", params=filters, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        return len(result) if isinstance(result, list) else 0

    async def count(self, table: str, filters: dict = None,
                    token: str = None) -> int:
        """Get row count for a table with optional filters."""
        client = await self._get_client()
        headers = {
            **self._auth_headers(token),
            "Prefer": "count=exact",
            "Range-Unit": "items",
            "Range": "0-0",
        }
        params = filters or {}
        resp = await client.head(f"/{table}", params=params, headers=headers)
        resp.raise_for_status()
        content_range = resp.headers.get("Content-Range", "")
        if "/" in content_range:
            total = content_range.split("/")[1]
            return int(total) if total != "*" else 0
        return 0


# Singleton
postgrest = PostgRESTClient()
