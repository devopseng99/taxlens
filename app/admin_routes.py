"""TaxLens Admin API — tenant provisioning, user management, audit history.

Protected by TAXLENS_ADMIN_KEY via X-Admin-Key header.
All DB operations go through PostgREST HTTP client.
"""

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import require_admin
from db.postgrest_client import postgrest, DB_ENABLED

router = APIRouter(prefix="/admin", tags=["admin"])

STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))


def _admin_token(request: Request) -> str:
    """Get admin JWT from request state (set by middleware)."""
    return getattr(request.state, "db_token", None) or postgrest.mint_jwt("__admin__", role="app_admin")


# --- Request/Response Models ---

class CreateTenantRequest(BaseModel):
    name: str
    slug: str
    plan: str = "starter"
    admin_username: str = "admin"
    admin_email: str | None = None


class CreateUserRequest(BaseModel):
    username: str
    email: str | None = None
    role: str = "member"


class CreateApiKeyRequest(BaseModel):
    name: str | None = None
    user_id: str | None = None
    scopes: list[str] | None = None


class CreateOAuthClientRequest(BaseModel):
    client_name: str
    redirect_uris: list[str]
    scopes: list[str] | None = None


# --- Tenant Management ---

@router.post("/tenants")
async def create_tenant(req: CreateTenantRequest, request: Request,
                        _admin: str = Depends(require_admin)):
    """Create a new tenant with default admin user and API key."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled. Multi-tenant requires database.")
    token = _admin_token(request)
    now = datetime.now(timezone.utc).isoformat()

    # Check slug uniqueness
    existing = await postgrest.get("tenants", {"slug": f"eq.{req.slug}"}, token=token)
    if existing:
        raise HTTPException(409, f"Tenant slug '{req.slug}' already exists.")

    # Create tenant
    tenant_id = uuid.uuid4().hex
    tenant = await postgrest.create("tenants", {
        "id": tenant_id, "name": req.name, "slug": req.slug,
        "plan_tier": req.plan, "status": "active",
        "created_at": now, "updated_at": now,
    }, token=token)

    # Create default admin user
    user_id = uuid.uuid4().hex
    user = await postgrest.create("users", {
        "id": user_id, "tenant_id": tenant_id,
        "username": req.admin_username, "email": req.admin_email,
        "role": "admin", "created_at": now,
    }, token=token)

    # Generate initial API key
    raw_key = f"tlk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = uuid.uuid4().hex
    await postgrest.create("api_keys", {
        "id": key_id, "tenant_id": tenant_id, "user_id": user_id,
        "key_hash": key_hash, "key_prefix": raw_key[:12],
        "name": "Initial admin key", "scopes": json.dumps([]),
        "status": "active", "created_at": now,
    }, token=token)

    # Create PVC directory for tenant
    tenant_dir = STORAGE_ROOT / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)

    return {
        "tenant": tenant,
        "admin_user": user,
        "api_key": {"id": key_id, "key": raw_key, "key_prefix": raw_key[:12]},
    }


@router.get("/tenants")
async def list_tenants(request: Request, status: str | None = None,
                       _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    filters = {}
    if status:
        filters["status"] = f"eq.{status}"
    tenants = await postgrest.get("tenants", filters, token=token,
                                   order="created_at.desc")
    return {"tenants": tenants}


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, request: Request,
                     _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    tenant = await postgrest.get_one("tenants", {"id": f"eq.{tenant_id}"}, token=token)
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    return tenant


@router.get("/tenants/{tenant_id}/stats")
async def get_tenant_stats(tenant_id: str, request: Request,
                           _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    tenant = await postgrest.get_one("tenants", {"id": f"eq.{tenant_id}"}, token=token)
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    stats = await postgrest.rpc("get_tenant_stats", {"p_tenant_id": tenant_id}, token=token)
    result = stats[0] if stats else {"users": 0, "drafts": 0, "documents": 0, "plaid_items": 0}
    return {"tenant_id": tenant_id, **(result if isinstance(result, dict) else json.loads(result))}


@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, request: Request,
                         _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    now = datetime.now(timezone.utc).isoformat()
    updated = await postgrest.update("tenants", {"id": f"eq.{tenant_id}"},
                                      {"status": "suspended", "updated_at": now}, token=token)
    if not updated:
        raise HTTPException(404, "Tenant not found.")
    return {"status": "suspended", "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/activate")
async def activate_tenant(tenant_id: str, request: Request,
                          _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    now = datetime.now(timezone.utc).isoformat()
    updated = await postgrest.update("tenants", {"id": f"eq.{tenant_id}"},
                                      {"status": "active", "updated_at": now}, token=token)
    if not updated:
        raise HTTPException(404, "Tenant not found.")
    return {"status": "active", "tenant_id": tenant_id}


# --- User Management ---

@router.get("/tenants/{tenant_id}/users")
async def list_users(tenant_id: str, request: Request,
                     _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    users = await postgrest.get("users", {"tenant_id": f"eq.{tenant_id}"},
                                 token=token, order="created_at")
    return {"users": users}


@router.post("/tenants/{tenant_id}/users")
async def create_user(tenant_id: str, req: CreateUserRequest, request: Request,
                      _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    tenant = await postgrest.get_one("tenants", {"id": f"eq.{tenant_id}"}, token=token)
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    now = datetime.now(timezone.utc).isoformat()
    user = await postgrest.create("users", {
        "id": uuid.uuid4().hex, "tenant_id": tenant_id,
        "username": req.username, "email": req.email,
        "role": req.role, "created_at": now,
    }, token=token)
    return user


# --- API Key Management ---

@router.get("/tenants/{tenant_id}/api-keys")
async def list_api_keys(tenant_id: str, request: Request,
                        _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    keys = await postgrest.get(
        "api_keys", {"tenant_id": f"eq.{tenant_id}"},
        token=token, order="created_at.desc",
        select="id,tenant_id,user_id,key_prefix,name,scopes,status,created_at,last_used_at,expires_at",
    )
    return {"api_keys": keys}


@router.post("/tenants/{tenant_id}/api-keys")
async def create_api_key(tenant_id: str, req: CreateApiKeyRequest, request: Request,
                         _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    raw_key = f"tlk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    await postgrest.create("api_keys", {
        "id": key_id, "tenant_id": tenant_id, "user_id": req.user_id,
        "key_hash": key_hash, "key_prefix": raw_key[:12],
        "name": req.name, "scopes": json.dumps(req.scopes or []),
        "status": "active", "created_at": now,
    }, token=token)
    return {
        "id": key_id, "key": raw_key, "key_prefix": raw_key[:12],
        "tenant_id": tenant_id, "name": req.name,
        "scopes": req.scopes or [], "created_at": now,
    }


@router.delete("/tenants/{tenant_id}/api-keys/{key_id}")
async def revoke_api_key(tenant_id: str, key_id: str, request: Request,
                         _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    updated = await postgrest.update("api_keys", {"id": f"eq.{key_id}"},
                                      {"status": "revoked"}, token=token)
    if not updated:
        raise HTTPException(404, "API key not found.")
    return {"revoked": key_id}


# --- OAuth Client Management ---

@router.get("/tenants/{tenant_id}/oauth-clients")
async def list_oauth_clients(tenant_id: str, request: Request,
                             _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    clients = await postgrest.get(
        "oauth_clients", {"tenant_id": f"eq.{tenant_id}"},
        token=token, order="created_at.desc",
        select="client_id,tenant_id,client_name,redirect_uris,grant_types,scopes,status,created_at",
    )
    return {"oauth_clients": clients}


@router.post("/tenants/{tenant_id}/oauth-client")
async def create_oauth_client(tenant_id: str, req: CreateOAuthClientRequest,
                               request: Request, _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    client_id = uuid.uuid4().hex
    client_secret = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc).isoformat()
    scopes = req.scopes or ["compute", "drafts", "documents"]

    await postgrest.create("oauth_clients", {
        "client_id": client_id, "tenant_id": tenant_id,
        "client_secret_hash": hashlib.sha256(client_secret.encode()).hexdigest(),
        "client_name": req.client_name,
        "redirect_uris": json.dumps(req.redirect_uris),
        "grant_types": json.dumps(["authorization_code", "refresh_token"]),
        "scopes": json.dumps(scopes),
        "status": "active", "created_at": now,
    }, token=token)

    return {
        "client_id": client_id, "client_secret": client_secret,
        "client_name": req.client_name, "redirect_uris": req.redirect_uris,
        "scopes": scopes,
        "mcp_config": {
            "info": "Add this to your Claude Desktop config:",
            "config": {
                "taxlens": {
                    "url": "https://dropit.istayintek.com/api/mcp",
                    "oauth": {
                        "client_id": client_id, "client_secret": client_secret,
                        "token_endpoint": "https://dropit.istayintek.com/api/oauth/token",
                    },
                }
            },
        },
    }


@router.post("/tenants/{tenant_id}/oauth-client/{client_id}/rotate")
async def rotate_oauth_secret(tenant_id: str, client_id: str, request: Request,
                               _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    new_secret = secrets.token_urlsafe(48)
    updated = await postgrest.update(
        "oauth_clients",
        {"client_id": f"eq.{client_id}", "status": "eq.active"},
        {"client_secret_hash": hashlib.sha256(new_secret.encode()).hexdigest()},
        token=token,
    )
    if not updated:
        raise HTTPException(404, "OAuth client not found.")
    return {"client_id": client_id, "client_secret": new_secret}


@router.delete("/tenants/{tenant_id}/oauth-client/{client_id}")
async def revoke_oauth_client(tenant_id: str, client_id: str, request: Request,
                               _admin: str = Depends(require_admin)):
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    # Revoke all tokens first
    await postgrest.delete("oauth_tokens", {"client_id": f"eq.{client_id}"}, token=token)
    # Revoke client
    updated = await postgrest.update("oauth_clients", {"client_id": f"eq.{client_id}"},
                                      {"status": "revoked"}, token=token)
    if not updated:
        raise HTTPException(404, "OAuth client not found.")
    return {"revoked": client_id}


# --- Audit History (replaces Dolt version history) ---

@router.get("/tenants/{tenant_id}/history")
async def get_tenant_history(tenant_id: str, request: Request, limit: int = 20,
                              _admin: str = Depends(require_admin)):
    """Get audit log entries for a tenant."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    # Query audit_log for entries related to this tenant
    rows = await postgrest.get(
        "audit_log", {"order": "committed_at.desc", "limit": str(limit)},
        token=token,
    )
    # Filter to entries mentioning this tenant_id
    filtered = []
    for r in rows:
        data = r.get("new_data") or r.get("old_data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = {}
        if data.get("tenant_id") == tenant_id or r.get("row_id") == tenant_id:
            filtered.append({
                "table": r["table_name"], "operation": r["operation"],
                "row_id": r["row_id"], "committed_at": r["committed_at"],
                "committed_by": r.get("committed_by", "system"),
            })
    return {"history": filtered}


@router.get("/history")
async def get_full_history(request: Request, limit: int = 50,
                           _admin: str = Depends(require_admin)):
    """Get full audit log (all tenants)."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    rows = await postgrest.get(
        "audit_log", {"order": "committed_at.desc", "limit": str(limit)},
        token=token,
    )
    return {"history": [{
        "table": r["table_name"], "operation": r["operation"],
        "row_id": r["row_id"], "committed_at": r["committed_at"],
        "committed_by": r.get("committed_by", "system"),
    } for r in rows]}


# --- Feature Flag Management ---

_VALID_FEATURE_FLAGS = {
    "can_compute_tax", "can_upload_documents", "can_itemized_deductions",
    "can_schedule_c", "can_schedule_d", "can_1099_forms", "can_multi_state",
    "can_use_mcp", "can_use_plaid", "can_use_agent",
    "max_filings_per_year", "max_w2_uploads", "max_documents", "max_users",
    "allowed_form_types", "early_access_enabled", "early_access_features",
}


@router.get("/tenants/{tenant_id}/features")
async def get_tenant_features(tenant_id: str, request: Request,
                              _admin: str = Depends(require_admin)):
    """Get current feature flags for a tenant."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")
    token = _admin_token(request)
    rows = await postgrest.get(
        "tenant_features", {"tenant_id": f"eq.{tenant_id}"}, token=token,
    )
    if not rows:
        raise HTTPException(404, f"No features found for tenant {tenant_id}")
    return rows[0]


class UpdateFeaturesRequest(BaseModel):
    features: dict


@router.put("/tenants/{tenant_id}/features")
async def update_tenant_features(tenant_id: str, req: UpdateFeaturesRequest,
                                 request: Request,
                                 _admin: str = Depends(require_admin)):
    """Update feature flags for a tenant. Only known flags are accepted."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")

    invalid = set(req.features.keys()) - _VALID_FEATURE_FLAGS
    if invalid:
        raise HTTPException(400, f"Unknown feature flags: {', '.join(invalid)}")

    token = _admin_token(request)

    # Build update data
    update_data = {}
    for key, value in req.features.items():
        if key in ("allowed_form_types", "early_access_features"):
            update_data[key] = json.dumps(value) if value is not None else None
        else:
            update_data[key] = value
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await postgrest.update(
        "tenant_features", {"tenant_id": f"eq.{tenant_id}"},
        update_data, token=token,
    )

    # Invalidate feature cache
    from middleware.feature_gate import invalidate_cache
    invalidate_cache(tenant_id)

    return {"updated": True, "tenant_id": tenant_id, "features": req.features}


class EarlyAccessRequest(BaseModel):
    enabled: bool
    features: list[str] = []


@router.post("/tenants/{tenant_id}/features/early-access")
async def toggle_early_access(tenant_id: str, req: EarlyAccessRequest,
                              request: Request,
                              _admin: str = Depends(require_admin)):
    """Toggle early access and select beta features for a tenant."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled.")

    token = _admin_token(request)
    await postgrest.update(
        "tenant_features", {"tenant_id": f"eq.{tenant_id}"},
        {
            "early_access_enabled": req.enabled,
            "early_access_features": json.dumps(req.features),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        token=token,
    )

    from middleware.feature_gate import invalidate_cache
    invalidate_cache(tenant_id)

    return {
        "tenant_id": tenant_id,
        "early_access_enabled": req.enabled,
        "early_access_features": req.features,
    }
