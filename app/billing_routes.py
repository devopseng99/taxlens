"""Billing routes — Stripe checkout, webhooks, portal, usage, onboarding."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel

from auth import require_auth, require_admin, get_tenant_id
from billing import (
    STRIPE_ENABLED, PLAN_TIERS, STRIPE_PRICES,
    create_checkout_session, create_billing_portal_session,
    verify_webhook_signature, save_billing_customer,
    get_billing_customer, update_subscription_status,
)
from db.postgrest_client import postgrest, DB_ENABLED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# --- Models ---

class CheckoutRequest(BaseModel):
    tenant_name: str
    email: str
    plan_tier: str = "starter"
    success_url: str = "https://taxlens-portal.istayintek.com/dashboard?billing=success"
    cancel_url: str = "https://taxlens-portal.istayintek.com/settings/billing?billing=cancelled"


class PortalRequest(BaseModel):
    return_url: str = "https://taxlens-portal.istayintek.com/settings/billing"


# --- Checkout & Portal ---

@router.post("/checkout")
async def checkout(req: CheckoutRequest, _admin: str = Depends(require_admin)):
    """Create a Stripe Checkout session for a new or upgrading tenant."""
    if not STRIPE_ENABLED:
        raise HTTPException(503, "Stripe billing not configured")
    if req.plan_tier not in PLAN_TIERS:
        raise HTTPException(400, f"Invalid plan tier: {req.plan_tier}")
    result = await create_checkout_session(
        req.tenant_name, req.email, req.plan_tier,
        req.success_url, req.cancel_url,
    )
    return result


@router.post("/portal")
async def billing_portal(req: PortalRequest, request: Request,
                         _auth: str = Depends(require_auth)):
    """Create a Stripe Customer Portal session for the current tenant."""
    if not STRIPE_ENABLED:
        raise HTTPException(503, "Stripe billing not configured")
    tenant_id = get_tenant_id(request)
    customer = await get_billing_customer(tenant_id)
    if not customer:
        raise HTTPException(404, "No billing account found for this tenant")
    result = await create_billing_portal_session(
        customer["stripe_customer_id"], req.return_url,
    )
    return result


# --- Webhook ---

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events. Verifies signature."""
    if not STRIPE_ENABLED:
        raise HTTPException(503, "Stripe billing not configured")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = verify_webhook_signature(payload, sig)
    except Exception as e:
        logger.warning("Stripe webhook signature verification failed: %s", e)
        raise HTTPException(400, "Invalid signature")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})
    logger.info("Stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data)
    elif event_type == "invoice.paid":
        logger.info("Invoice paid: %s", data.get("id"))
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data)

    return {"received": True}


async def _handle_checkout_completed(session: dict):
    """Provision tenant after successful checkout."""
    from onboarding import provision_tenant

    customer_id = session.get("customer", "")
    subscription_id = session.get("subscription", "")
    metadata = session.get("metadata", {})
    tenant_name = metadata.get("tenant_name", "New Tenant")
    plan_tier = metadata.get("plan_tier", "starter")
    email = session.get("customer_email", "")

    try:
        result = await provision_tenant(
            tenant_name=tenant_name,
            plan_tier=plan_tier,
            email=email,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
        )
        logger.info("Tenant provisioned via Stripe: %s (%s)", tenant_name, plan_tier)
    except Exception as e:
        logger.error("Failed to provision tenant from checkout: %s", e)


async def _handle_subscription_updated(subscription: dict):
    """Update plan tier when subscription changes."""
    customer_id = subscription.get("customer", "")
    status = subscription.get("status", "")
    items = subscription.get("items", {}).get("data", [])
    plan_tier = None
    for item in items:
        price_id = item.get("price", {}).get("id", "")
        for tier, pid in STRIPE_PRICES.items():
            if pid == price_id:
                plan_tier = tier
                break

    period_end = None
    if subscription.get("current_period_end"):
        period_end = datetime.fromtimestamp(
            subscription["current_period_end"], tz=timezone.utc
        )

    await update_subscription_status(customer_id, status, plan_tier, period_end)
    if plan_tier:
        await _sync_plan_limits(customer_id, plan_tier)


async def _handle_subscription_deleted(subscription: dict):
    """Downgrade tenant when subscription is cancelled."""
    customer_id = subscription.get("customer", "")
    await update_subscription_status(customer_id, "cancelled")


async def _handle_payment_failed(invoice: dict):
    """Log payment failure. Don't suspend immediately — Stripe retries."""
    customer_id = invoice.get("customer", "")
    logger.warning("Payment failed for customer %s", customer_id)


async def _sync_plan_limits(stripe_customer_id: str, plan_tier: str):
    """Sync tenant_plans + tenant_features tables after plan change."""
    if not DB_ENABLED:
        return
    from rate_limiter import PLAN_DEFAULTS, TIER_FEATURES
    import json as _json
    admin_token = postgrest.mint_jwt("__admin__", role="app_admin")
    customers = await postgrest.get(
        "billing_customers",
        {"stripe_customer_id": f"eq.{stripe_customer_id}"},
        token=admin_token,
    )
    if not customers:
        return
    tenant_id = customers[0]["tenant_id"]

    # Sync rate limits
    limits = PLAN_DEFAULTS.get(plan_tier, PLAN_DEFAULTS["starter"])
    await postgrest.rpc("upsert_tenant_plans", {
        "p_tenant_id": tenant_id,
        "p_plan_tier": plan_tier,
        "p_api_calls_per_minute": limits["api_calls_per_minute"],
        "p_computations_per_day": limits["computations_per_day"],
        "p_ocr_pages_per_month": limits["ocr_pages_per_month"],
        "p_agent_messages_per_day": limits["agent_messages_per_day"],
    }, token=admin_token)

    # Sync feature flags
    tier_features = TIER_FEATURES.get(plan_tier, TIER_FEATURES["free"])
    feat_params = {"p_tenant_id": tenant_id}
    for key, value in tier_features.items():
        param_key = f"p_{key}"
        if key in ("allowed_form_types", "early_access_features"):
            feat_params[param_key] = _json.dumps(value) if value is not None else None
        else:
            feat_params[param_key] = value
    await postgrest.rpc("upsert_tenant_features", feat_params, token=admin_token)

    # Invalidate feature cache
    from middleware.feature_gate import invalidate_cache
    invalidate_cache(tenant_id)


# --- Usage endpoints ---

@router.get("/usage")
async def get_usage(request: Request, _auth: str = Depends(require_auth)):
    """Get current billing period usage for the authenticated tenant."""
    tenant_id = get_tenant_id(request)
    from rate_limiter import rate_limiter
    usage = rate_limiter.get_tenant_usage(tenant_id)

    customer = await get_billing_customer(tenant_id) if DB_ENABLED else None
    plan = customer["plan_tier"] if customer else "starter"

    daily = []
    if DB_ENABLED:
        token = getattr(request.state, "db_token", None) or postgrest.mint_jwt(tenant_id)
        daily = await postgrest.get(
            "usage_daily",
            {"tenant_id": f"eq.{tenant_id}", "order": "event_date.desc", "limit": "30"},
            token=token,
        )

    return {
        "tenant_id": tenant_id,
        "plan_tier": plan,
        "current_usage": usage,
        "daily_history": [
            {"type": r["event_type"], "date": str(r["event_date"]),
             "count": r["event_count"]} for r in daily
        ],
    }


@router.get("/plans")
async def list_plans():
    """List available billing plans (public endpoint)."""
    return {"plans": PLAN_TIERS}


# --- Free tier self-service signup ---

class FreeSignupRequest(BaseModel):
    name: str
    email: str

# IP-based rate limiting for free signup (10/hr)
_signup_attempts: dict[str, list[float]] = {}
_SIGNUP_LIMIT = 10
_SIGNUP_WINDOW = 3600  # 1 hour


def _check_signup_rate(ip: str) -> bool:
    """Returns True if allowed."""
    import time
    now = time.time()
    attempts = _signup_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _SIGNUP_WINDOW]
    _signup_attempts[ip] = attempts
    return len(attempts) < _SIGNUP_LIMIT


@router.post("/onboarding/free")
async def free_signup(req: FreeSignupRequest, request: Request):
    """Self-service free tier signup. No Stripe, no admin key.
    Creates tenant with standard deduction + W-2 only features.
    Login required for all API/portal access (NIST/IRS compliance)."""
    import time

    if not DB_ENABLED:
        raise HTTPException(503, "Database required for signup")

    client_ip = request.client.host if request.client else "unknown"
    if not _check_signup_rate(client_ip):
        raise HTTPException(429, "Too many signup attempts. Please try again later.")
    _signup_attempts.setdefault(client_ip, []).append(time.time())

    if not req.name or not req.email:
        raise HTTPException(400, "Name and email are required")

    from onboarding import provision_tenant
    try:
        result = await provision_tenant(
            tenant_name=req.name,
            plan_tier="free",
            email=req.email,
            admin_username=req.email.split("@")[0],
        )
    except Exception as e:
        logger.error("Free signup failed: %s", e)
        raise HTTPException(500, "Signup failed. Please try again.")

    return {
        "tenant_id": result["tenant_id"],
        "api_key": result["api_key"],
        "plan_tier": "free",
        "portal_url": f"https://taxlens-portal.istayintek.com/login?key={result['api_key']}",
        "features": {
            "standard_deduction": True,
            "unlimited_w2": True,
            "itemized_deductions": False,
            "schedules_c_d": False,
            "1099_forms": False,
            "multi_state": False,
        },
    }
