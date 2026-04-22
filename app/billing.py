"""Stripe billing integration — subscriptions, webhooks, metered usage."""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Stripe config from env
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_ENABLED = bool(STRIPE_SECRET_KEY)

# Price IDs (configured per environment)
STRIPE_PRICES = {
    "starter": os.getenv("STRIPE_PRICE_STARTER", ""),
    "professional": os.getenv("STRIPE_PRICE_PROFESSIONAL", ""),
    "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE", ""),
}

# Metered add-on price IDs
STRIPE_METERED_PRICES = {
    "ocr_page": os.getenv("STRIPE_PRICE_OCR", ""),
    "tax_computation": os.getenv("STRIPE_PRICE_COMPUTATION", ""),
}

PLAN_TIERS = {
    "starter": {"name": "Starter", "price": 2900, "description": "$29/mo"},
    "professional": {"name": "Professional", "price": 9900, "description": "$99/mo"},
    "enterprise": {"name": "Enterprise", "price": 29900, "description": "$299/mo"},
}


def _get_stripe():
    """Lazy import stripe to avoid import errors when not installed."""
    if not STRIPE_ENABLED:
        raise RuntimeError("Stripe not configured (STRIPE_SECRET_KEY missing)")
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


async def create_checkout_session(tenant_name: str, email: str,
                                  plan_tier: str, success_url: str,
                                  cancel_url: str) -> dict:
    """Create a Stripe Checkout session for a new subscription."""
    stripe = _get_stripe()
    price_id = STRIPE_PRICES.get(plan_tier)
    if not price_id:
        raise ValueError(f"No Stripe price configured for plan: {plan_tier}")

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tenant_name": tenant_name, "plan_tier": plan_tier},
    )
    return {"checkout_url": session.url, "session_id": session.id}


async def create_billing_portal_session(stripe_customer_id: str,
                                        return_url: str) -> dict:
    """Create a Stripe Customer Portal session for subscription management."""
    stripe = _get_stripe()
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )
    return {"portal_url": session.url}


async def report_metered_usage(stripe_subscription_id: str,
                               event_type: str, quantity: int) -> dict:
    """Report metered usage to Stripe for add-on billing."""
    stripe = _get_stripe()
    price_id = STRIPE_METERED_PRICES.get(event_type)
    if not price_id:
        return {"reported": False, "reason": f"No metered price for {event_type}"}

    # Find subscription item for this metered price
    sub = stripe.Subscription.retrieve(stripe_subscription_id)
    item_id = None
    for item in sub["items"]["data"]:
        if item["price"]["id"] == price_id:
            item_id = item["id"]
            break

    if not item_id:
        return {"reported": False, "reason": "Metered item not in subscription"}

    record = stripe.SubscriptionItem.create_usage_record(
        item_id,
        quantity=quantity,
        action="increment",
    )
    return {"reported": True, "usage_record_id": record.id}


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe webhook signature. Returns the event dict or raises."""
    stripe = _get_stripe()
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
    event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    return event


# --- Dolt billing_customers operations ---

async def save_billing_customer(tenant_id: str, stripe_customer_id: str,
                                stripe_subscription_id: str, plan_tier: str):
    """Save or update billing customer in Dolt."""
    from db.connection import get_conn, DOLT_ENABLED
    if not DOLT_ENABLED:
        return
    import aiomysql
    now = datetime.now(timezone.utc)
    async with get_conn() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "REPLACE INTO billing_customers "
                "(tenant_id, stripe_customer_id, stripe_subscription_id, plan_tier, "
                "subscription_status, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, 'active', %s, %s)",
                (tenant_id, stripe_customer_id, stripe_subscription_id, plan_tier, now, now),
            )


async def get_billing_customer(tenant_id: str) -> dict | None:
    """Get billing customer by tenant_id."""
    from db.connection import fetchone
    return await fetchone(
        "SELECT * FROM billing_customers WHERE tenant_id = %s", (tenant_id,)
    )


async def update_subscription_status(stripe_customer_id: str, status: str,
                                     plan_tier: str | None = None,
                                     period_end: datetime | None = None):
    """Update subscription status after webhook events."""
    from db.connection import get_conn, DOLT_ENABLED
    if not DOLT_ENABLED:
        return
    import aiomysql
    now = datetime.now(timezone.utc)
    async with get_conn() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = ("UPDATE billing_customers SET subscription_status = %s, "
                   "updated_at = %s")
            args = [status, now]
            if plan_tier:
                sql += ", plan_tier = %s"
                args.append(plan_tier)
            if period_end:
                sql += ", current_period_end = %s"
                args.append(period_end)
            sql += " WHERE stripe_customer_id = %s"
            args.append(stripe_customer_id)
            await cur.execute(sql, tuple(args))
