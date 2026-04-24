"""Self-service tenant onboarding — provision from Stripe checkout or admin API."""

import hashlib
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone

from db.postgrest_client import postgrest, DB_ENABLED
from billing import save_billing_customer
from rate_limiter import PLAN_DEFAULTS, TIER_FEATURES

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert tenant name to URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:64]


async def provision_tenant(tenant_name: str, plan_tier: str = "starter",
                           email: str = "", admin_username: str = "admin",
                           stripe_customer_id: str = "",
                           stripe_subscription_id: str = "") -> dict:
    """Full tenant provisioning via PostgREST:
    1. Create tenant record
    2. Create default admin user
    3. Generate API key
    4. Set plan limits
    5. Link Stripe billing (if provided)

    Returns dict with tenant_id, api_key, and connection instructions.
    """
    if not DB_ENABLED:
        raise RuntimeError("Database required for tenant provisioning")

    admin_token = postgrest.mint_jwt("__admin__", role="app_admin")
    slug = _slugify(tenant_name)
    now = datetime.now(timezone.utc).isoformat()

    # Check slug uniqueness
    existing = await postgrest.get("tenants", {"slug": f"eq.{slug}"}, token=admin_token)
    if existing:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    # 1. Create tenant
    tenant_id = uuid.uuid4().hex
    await postgrest.create("tenants", {
        "id": tenant_id, "name": tenant_name, "slug": slug,
        "plan_tier": plan_tier, "status": "active",
        "created_at": now, "updated_at": now,
    }, token=admin_token)

    # 2. Create admin user
    user_id = uuid.uuid4().hex
    await postgrest.create("users", {
        "id": user_id, "tenant_id": tenant_id,
        "username": admin_username, "email": email,
        "role": "admin", "created_at": now,
    }, token=admin_token)

    # 3. Generate API key
    raw_key = f"tlk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = uuid.uuid4().hex
    await postgrest.create("api_keys", {
        "id": key_id, "tenant_id": tenant_id, "user_id": user_id,
        "key_hash": key_hash, "key_prefix": raw_key[:12],
        "name": f"Default key for {tenant_name}",
        "scopes": json.dumps([]), "status": "active", "created_at": now,
    }, token=admin_token)

    # 4. Set plan limits via RPC
    limits = PLAN_DEFAULTS.get(plan_tier, PLAN_DEFAULTS["starter"])
    await postgrest.rpc("upsert_tenant_plans", {
        "p_tenant_id": tenant_id,
        "p_plan_tier": plan_tier,
        "p_api_calls_per_minute": limits["api_calls_per_minute"],
        "p_computations_per_day": limits["computations_per_day"],
        "p_ocr_pages_per_month": limits["ocr_pages_per_month"],
        "p_agent_messages_per_day": limits["agent_messages_per_day"],
    }, token=admin_token)

    # 5. Set feature flags based on plan tier
    tier_features = TIER_FEATURES.get(plan_tier, TIER_FEATURES["free"])
    feat_params = {"p_tenant_id": tenant_id}
    for key, value in tier_features.items():
        param_key = f"p_{key}"
        if key == "allowed_form_types":
            feat_params[param_key] = json.dumps(value) if value is not None else None
        elif key == "early_access_features":
            feat_params[param_key] = json.dumps(value) if value else "[]"
        else:
            feat_params[param_key] = value
    await postgrest.rpc("upsert_tenant_features", feat_params, token=admin_token)

    # 6. Link Stripe billing
    if stripe_customer_id:
        await save_billing_customer(
            tenant_id, stripe_customer_id, stripe_subscription_id, plan_tier
        )

    logger.info("Provisioned tenant: %s (%s) id=%s", tenant_name, plan_tier, tenant_id)

    # 7. Send welcome email (fire-and-forget, don't block provisioning)
    if email:
        try:
            from email_service import send_welcome_email, EMAIL_ENABLED
            if EMAIL_ENABLED:
                await send_welcome_email(email, tenant_name, raw_key)
        except Exception as e:
            logger.warning("Welcome email failed (non-blocking): %s", e)

    return {
        "tenant_id": tenant_id,
        "slug": slug,
        "user_id": user_id,
        "api_key": raw_key,
        "plan_tier": plan_tier,
        "mcp_config": {
            "description": "Add this to your Claude Desktop config (claude_desktop_config.json):",
            "mcpServers": {
                "taxlens": {
                    "url": f"{os.getenv('TAXLENS_API_URL', 'https://dropit.istayintek.com/api')}/mcp",
                    "headers": {"X-API-Key": raw_key},
                }
            },
        },
    }


async def deactivate_tenant(tenant_id: str) -> dict:
    """Deactivate tenant — revoke tokens, mark inactive, retain data."""
    if not DB_ENABLED:
        raise RuntimeError("Database required")

    admin_token = postgrest.mint_jwt("__admin__", role="app_admin")
    now = datetime.now(timezone.utc).isoformat()

    # Mark tenant inactive
    await postgrest.update("tenants", {"id": f"eq.{tenant_id}"},
                            {"status": "inactive", "updated_at": now}, token=admin_token)

    # Revoke all API keys
    await postgrest.update("api_keys",
                            {"tenant_id": f"eq.{tenant_id}", "status": "eq.active"},
                            {"status": "revoked"}, token=admin_token)

    # Revoke all OAuth clients
    await postgrest.update("oauth_clients",
                            {"tenant_id": f"eq.{tenant_id}", "status": "eq.active"},
                            {"status": "revoked"}, token=admin_token)

    # Update billing status
    await postgrest.update("billing_customers",
                            {"tenant_id": f"eq.{tenant_id}"},
                            {"subscription_status": "cancelled", "updated_at": now},
                            token=admin_token)

    logger.info("Deactivated tenant: %s", tenant_id)
    return {"deactivated": True, "tenant_id": tenant_id}
