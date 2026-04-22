"""Self-service tenant onboarding — provision from Stripe checkout or admin API."""

import logging
import re
import uuid
from datetime import datetime, timezone

from db.connection import DOLT_ENABLED, execute, fetchone
from db.tenant_repo import create_tenant
from db.user_repo import create_user
from db.api_key_repo import create_key
from db.versioning import dolt_commit
from billing import save_billing_customer
from rate_limiter import PLAN_DEFAULTS

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert tenant name to URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:64]


async def provision_tenant(tenant_name: str, plan_tier: str = "starter",
                           email: str = "", admin_username: str = "admin",
                           stripe_customer_id: str = "",
                           stripe_subscription_id: str = "") -> dict:
    """Full tenant provisioning:
    1. Create tenant record
    2. Create default admin user
    3. Generate API key
    4. Set plan limits
    5. Link Stripe billing (if provided)
    6. Commit to Dolt

    Returns dict with tenant_id, api_key, and connection instructions.
    """
    if not DOLT_ENABLED:
        raise RuntimeError("Dolt required for tenant provisioning")

    slug = _slugify(tenant_name)
    now = datetime.now(timezone.utc)

    # Check slug uniqueness
    existing = await fetchone("SELECT id FROM tenants WHERE slug = %s", (slug,))
    if existing:
        # Append random suffix
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    # 1. Create tenant
    tenant_id = await create_tenant(tenant_name, slug, plan_tier)

    # 2. Create admin user
    user_id = await create_user(tenant_id, admin_username, email, "admin")

    # 3. Generate API key
    key_result = await create_key(tenant_id, user_id, f"Default key for {tenant_name}")
    raw_key = key_result["raw_key"]

    # 4. Set plan limits
    limits = PLAN_DEFAULTS.get(plan_tier, PLAN_DEFAULTS["starter"])
    await execute(
        "REPLACE INTO tenant_plans "
        "(tenant_id, plan_tier, api_calls_per_minute, computations_per_day, "
        "ocr_pages_per_month, agent_messages_per_day, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (tenant_id, plan_tier, limits["api_calls_per_minute"],
         limits["computations_per_day"], limits["ocr_pages_per_month"],
         limits["agent_messages_per_day"], now),
    )

    # 5. Link Stripe billing
    if stripe_customer_id:
        await save_billing_customer(
            tenant_id, stripe_customer_id, stripe_subscription_id, plan_tier
        )

    # 6. Commit
    await dolt_commit(f"onboarding: provisioned tenant {slug} ({plan_tier}) [{tenant_id}]")

    logger.info("Provisioned tenant: %s (%s) id=%s", tenant_name, plan_tier, tenant_id)

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
                    "url": "https://dropit.istayintek.com/api/mcp",
                    "headers": {"X-API-Key": raw_key},
                }
            },
        },
    }


async def deactivate_tenant(tenant_id: str) -> dict:
    """Deactivate tenant — revoke tokens, mark inactive, retain data."""
    if not DOLT_ENABLED:
        raise RuntimeError("Dolt required")

    now = datetime.now(timezone.utc)

    # Mark tenant inactive
    await execute(
        "UPDATE tenants SET status = 'inactive', updated_at = %s WHERE id = %s",
        (now, tenant_id),
    )

    # Revoke all API keys
    await execute(
        "UPDATE api_keys SET status = 'revoked' WHERE tenant_id = %s AND status = 'active'",
        (tenant_id,),
    )

    # Revoke all OAuth clients
    await execute(
        "UPDATE oauth_clients SET status = 'revoked' WHERE tenant_id = %s AND status = 'active'",
        (tenant_id,),
    )

    # Update billing status
    await execute(
        "UPDATE billing_customers SET subscription_status = 'cancelled', updated_at = %s "
        "WHERE tenant_id = %s",
        (now, tenant_id),
    )

    await dolt_commit(f"onboarding: deactivated tenant [{tenant_id}]")

    logger.info("Deactivated tenant: %s", tenant_id)
    return {"deactivated": True, "tenant_id": tenant_id}
