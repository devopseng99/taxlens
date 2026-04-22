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
from db.connection import DOLT_ENABLED, fetchone, fetchall, execute
from db.versioning import dolt_commit

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

    await dolt_commit(f"billing: subscription updated for customer {customer_id[:8]}")


async def _handle_subscription_deleted(subscription: dict):
    """Downgrade tenant when subscription is cancelled."""
    customer_id = subscription.get("customer", "")
    await update_subscription_status(customer_id, "cancelled")
    await dolt_commit(f"billing: subscription cancelled for customer {customer_id[:8]}")


async def _handle_payment_failed(invoice: dict):
    """Log payment failure. Don't suspend immediately — Stripe retries."""
    customer_id = invoice.get("customer", "")
    logger.warning("Payment failed for customer %s", customer_id)


async def _sync_plan_limits(stripe_customer_id: str, plan_tier: str):
    """Sync tenant_plans table after plan change."""
    if not DOLT_ENABLED:
        return
    from rate_limiter import PLAN_DEFAULTS
    customer = await fetchone(
        "SELECT tenant_id FROM billing_customers WHERE stripe_customer_id = %s",
        (stripe_customer_id,),
    )
    if not customer:
        return
    tenant_id = customer["tenant_id"]
    limits = PLAN_DEFAULTS.get(plan_tier, PLAN_DEFAULTS["starter"])
    now = datetime.now(timezone.utc)
    await execute(
        "REPLACE INTO tenant_plans "
        "(tenant_id, plan_tier, api_calls_per_minute, computations_per_day, "
        "ocr_pages_per_month, agent_messages_per_day, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (tenant_id, plan_tier, limits["api_calls_per_minute"],
         limits["computations_per_day"], limits["ocr_pages_per_month"],
         limits["agent_messages_per_day"], now),
    )


# --- Usage endpoints ---

@router.get("/usage")
async def get_usage(request: Request, _auth: str = Depends(require_auth)):
    """Get current billing period usage for the authenticated tenant."""
    tenant_id = get_tenant_id(request)
    from rate_limiter import rate_limiter
    usage = rate_limiter.get_tenant_usage(tenant_id)

    customer = await get_billing_customer(tenant_id) if DOLT_ENABLED else None
    plan = customer["plan_tier"] if customer else "starter"

    daily = []
    if DOLT_ENABLED:
        daily = await fetchall(
            "SELECT event_type, event_date, event_count FROM usage_daily "
            "WHERE tenant_id = %s ORDER BY event_date DESC LIMIT 30",
            (tenant_id,),
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
