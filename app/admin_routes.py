"""TaxLens Admin API — tenant provisioning, user management, version history.

Protected by TAXLENS_ADMIN_KEY via X-Admin-Key header.
"""

import os
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import require_admin
from db.connection import DOLT_ENABLED
from db import tenant_repo, user_repo, api_key_repo, oauth_repo

router = APIRouter(prefix="/admin", tags=["admin"])

STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))


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
async def create_tenant(req: CreateTenantRequest, _admin: str = Depends(require_admin)):
    """Create a new tenant with default admin user and API key."""
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled. Multi-tenant requires database.")

    # Check slug uniqueness
    existing = await tenant_repo.get_tenant_by_slug(req.slug)
    if existing:
        raise HTTPException(409, f"Tenant slug '{req.slug}' already exists.")

    # Create tenant
    tenant = await tenant_repo.create_tenant(req.name, req.slug, req.plan)

    # Create default admin user
    user = await user_repo.create_user(
        tenant["id"], req.admin_username, req.admin_email, role="admin"
    )

    # Generate initial API key
    api_key = await api_key_repo.create_key(
        tenant["id"], user["id"], name="Initial admin key"
    )

    # Create PVC directory for tenant
    tenant_dir = STORAGE_ROOT / tenant["id"]
    tenant_dir.mkdir(parents=True, exist_ok=True)

    # Dolt commit for tenant creation
    from db.versioning import dolt_commit
    await dolt_commit(f"tenant created: {req.name} ({req.slug})")

    return {
        "tenant": tenant,
        "admin_user": user,
        "api_key": {
            "id": api_key["id"],
            "key": api_key["key"],  # Shown once
            "key_prefix": api_key["key_prefix"],
        },
    }


@router.get("/tenants")
async def list_tenants(status: str | None = None, _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    return {"tenants": await tenant_repo.list_tenants(status)}


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    tenant = await tenant_repo.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    return tenant


@router.get("/tenants/{tenant_id}/stats")
async def get_tenant_stats(tenant_id: str, _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    tenant = await tenant_repo.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    stats = await tenant_repo.get_tenant_stats(tenant_id)
    return {"tenant_id": tenant_id, **stats}


@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    rows = await tenant_repo.update_tenant(tenant_id, status="suspended")
    if not rows:
        raise HTTPException(404, "Tenant not found.")
    from db.versioning import dolt_commit
    await dolt_commit(f"tenant suspended: {tenant_id}")
    return {"status": "suspended", "tenant_id": tenant_id}


@router.post("/tenants/{tenant_id}/activate")
async def activate_tenant(tenant_id: str, _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    rows = await tenant_repo.update_tenant(tenant_id, status="active")
    if not rows:
        raise HTTPException(404, "Tenant not found.")
    from db.versioning import dolt_commit
    await dolt_commit(f"tenant activated: {tenant_id}")
    return {"status": "active", "tenant_id": tenant_id}


# --- User Management ---

@router.get("/tenants/{tenant_id}/users")
async def list_users(tenant_id: str, _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    return {"users": await user_repo.list_users(tenant_id)}


@router.post("/tenants/{tenant_id}/users")
async def create_user(tenant_id: str, req: CreateUserRequest,
                      _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    tenant = await tenant_repo.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    user = await user_repo.create_user(tenant_id, req.username, req.email, req.role)
    return user


# --- API Key Management ---

@router.get("/tenants/{tenant_id}/api-keys")
async def list_api_keys(tenant_id: str, _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    return {"api_keys": await api_key_repo.list_keys(tenant_id)}


@router.post("/tenants/{tenant_id}/api-keys")
async def create_api_key(tenant_id: str, req: CreateApiKeyRequest,
                         _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    key = await api_key_repo.create_key(tenant_id, req.user_id, req.name, req.scopes)
    return key


@router.delete("/tenants/{tenant_id}/api-keys/{key_id}")
async def revoke_api_key(tenant_id: str, key_id: str,
                         _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    rows = await api_key_repo.revoke_key(key_id)
    if not rows:
        raise HTTPException(404, "API key not found.")
    return {"revoked": key_id}


# --- OAuth Client Management ---

@router.get("/tenants/{tenant_id}/oauth-clients")
async def list_oauth_clients(tenant_id: str, _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    return {"oauth_clients": await oauth_repo.list_clients(tenant_id)}


@router.post("/tenants/{tenant_id}/oauth-client")
async def create_oauth_client(tenant_id: str, req: CreateOAuthClientRequest,
                               _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    client = await oauth_repo.register_client(
        tenant_id, req.client_name, req.redirect_uris, scopes=req.scopes
    )
    return {
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],  # Shown once
        "client_name": client["client_name"],
        "redirect_uris": client["redirect_uris"],
        "scopes": client["scopes"],
        "mcp_config": {
            "info": "Add this to your Claude Desktop config:",
            "config": {
                "taxlens": {
                    "url": "https://dropit.istayintek.com/api/mcp",
                    "oauth": {
                        "client_id": client["client_id"],
                        "client_secret": client["client_secret"],
                        "token_endpoint": "https://dropit.istayintek.com/api/oauth/token",
                    }
                }
            }
        }
    }


@router.post("/tenants/{tenant_id}/oauth-client/{client_id}/rotate")
async def rotate_oauth_secret(tenant_id: str, client_id: str,
                               _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    result = await oauth_repo.rotate_client_secret(client_id)
    if not result:
        raise HTTPException(404, "OAuth client not found.")
    return result


@router.delete("/tenants/{tenant_id}/oauth-client/{client_id}")
async def revoke_oauth_client(tenant_id: str, client_id: str,
                               _admin: str = Depends(require_admin)):
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    await oauth_repo.revoke_all_tokens(client_id)
    rows = await oauth_repo.revoke_client(client_id)
    if not rows:
        raise HTTPException(404, "OAuth client not found.")
    return {"revoked": client_id}


# --- Version History ---

@router.get("/tenants/{tenant_id}/history")
async def get_tenant_history(tenant_id: str, limit: int = 20,
                              _admin: str = Depends(require_admin)):
    """Get Dolt commit history for a tenant."""
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    from db.versioning import dolt_log
    log = await dolt_log(limit)
    # Filter to commits mentioning this tenant
    filtered = [e for e in log if tenant_id in e.get("message", "")]
    return {"history": filtered}


@router.get("/history")
async def get_full_history(limit: int = 50, _admin: str = Depends(require_admin)):
    """Get full Dolt commit history (all tenants)."""
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    from db.versioning import dolt_log
    return {"history": await dolt_log(limit)}


@router.get("/tenants/{tenant_id}/history/diff/{from_commit}/{to_commit}")
async def get_history_diff(tenant_id: str, from_commit: str, to_commit: str,
                           table: str = "tax_drafts",
                           _admin: str = Depends(require_admin)):
    """Get row-level diff between two commits for a table."""
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled.")
    from db.versioning import dolt_diff
    return {"diff": await dolt_diff(from_commit, to_commit, table)}
