"""Stripe live mode configuration — products, prices, metered billing."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Live Stripe Products & Prices
# ---------------------------------------------------------------------------
@dataclass
class StripeProduct:
    name: str
    description: str
    price_monthly: int  # cents
    tier: str
    features: list = field(default_factory=list)


LIVE_PRODUCTS = {
    "starter": StripeProduct(
        name="TaxLens Starter",
        description="Individual tax preparation with federal + 1 state",
        price_monthly=2900,  # $29
        tier="starter",
        features=[
            "Federal 1040 computation",
            "1 state return",
            "W-2 + 1099-INT OCR",
            "PDF generation (5 forms)",
            "5 computations/month",
        ],
    ),
    "professional": StripeProduct(
        name="TaxLens Professional",
        description="Full tax intelligence for CPAs and tax preparers",
        price_monthly=9900,  # $99
        tier="professional",
        features=[
            "All federal forms + schedules",
            "20 state returns",
            "All OCR models (W-2, 1099-R, 1099-MISC, 1099-G, etc.)",
            "Tax projections + optimizer",
            "Amended returns (1040-X)",
            "50 computations/month",
            "API access",
        ],
    ),
    "enterprise": StripeProduct(
        name="TaxLens Enterprise",
        description="Unlimited access with MCP integration for firms",
        price_monthly=29900,  # $299
        tier="enterprise",
        features=[
            "Everything in Professional",
            "Unlimited computations",
            "MCP server integration",
            "Batch document processing",
            "Webhook notifications",
            "Priority support",
            "Custom branding",
        ],
    ),
}


# ---------------------------------------------------------------------------
# Metered Usage
# ---------------------------------------------------------------------------
@dataclass
class UsageRecord:
    tenant_id: str = ""
    metric: str = ""  # "computations", "ocr_pages", "api_calls"
    quantity: int = 0
    timestamp: str = ""


# In-memory usage store (production: Stripe usage records API)
_usage_records: list[UsageRecord] = []


def record_metered_usage(tenant_id: str, metric: str, quantity: int = 1):
    """Record metered usage for billing (production: stripe.SubscriptionItem.create_usage_record)."""
    from datetime import datetime, timezone
    _usage_records.append(UsageRecord(
        tenant_id=tenant_id,
        metric=metric,
        quantity=quantity,
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))


def get_tenant_usage_summary(tenant_id: str) -> dict:
    """Get usage summary for a tenant."""
    summary: dict[str, int] = {}
    for r in _usage_records:
        if r.tenant_id == tenant_id:
            summary[r.metric] = summary.get(r.metric, 0) + r.quantity
    return summary


def reset_usage():
    """Reset usage records (for testing)."""
    _usage_records.clear()


# ---------------------------------------------------------------------------
# Revenue Dashboard
# ---------------------------------------------------------------------------
@dataclass
class RevenueMetrics:
    total_subscribers: int = 0
    mrr: float = 0.0  # Monthly Recurring Revenue
    arr: float = 0.0  # Annual Recurring Revenue
    subscribers_by_tier: dict = field(default_factory=dict)
    churn_rate: float = 0.0  # Monthly churn rate
    metered_revenue: float = 0.0  # Overage charges


def compute_revenue_metrics(
    subscribers: list[dict],
    churned_count: int = 0,
) -> RevenueMetrics:
    """Compute revenue dashboard metrics from subscriber list.

    Each subscriber dict: {"tenant_id": str, "tier": str, "status": str}
    """
    metrics = RevenueMetrics()
    tier_counts: dict[str, int] = {}

    for sub in subscribers:
        if sub.get("status") != "active":
            continue
        metrics.total_subscribers += 1
        tier = sub.get("tier", "starter")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        product = LIVE_PRODUCTS.get(tier)
        if product:
            metrics.mrr += product.price_monthly / 100.0

    metrics.subscribers_by_tier = tier_counts
    metrics.arr = metrics.mrr * 12

    if metrics.total_subscribers + churned_count > 0:
        metrics.churn_rate = churned_count / (metrics.total_subscribers + churned_count)

    return metrics


# ---------------------------------------------------------------------------
# Billing Lifecycle
# ---------------------------------------------------------------------------
BILLING_STATES = [
    "free",         # No subscription
    "trialing",     # Free trial period
    "active",       # Paid subscription active
    "past_due",     # Payment failed, grace period
    "canceled",     # Subscription canceled
    "downgraded",   # Moved to lower tier
]


def validate_billing_transition(current: str, target: str) -> bool:
    """Validate billing state transition."""
    valid_transitions = {
        "free": {"trialing", "active"},
        "trialing": {"active", "canceled"},
        "active": {"active", "past_due", "canceled", "downgraded"},
        "past_due": {"active", "canceled"},
        "canceled": {"active", "trialing"},
        "downgraded": {"active", "canceled"},
    }
    return target in valid_transitions.get(current, set())
