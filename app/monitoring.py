"""Monitoring routes — usage dashboards, per-tenant metrics, Prometheus."""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, HTTPException, Depends, Query

from auth import require_auth, require_admin, get_tenant_id
from db.connection import DOLT_ENABLED, fetchall, fetchone
from rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monitoring"])


# --- Tenant-facing usage ---

@router.get("/usage/me")
async def my_usage(request: Request, _auth: str = Depends(require_auth)):
    """Get usage summary for the authenticated tenant."""
    tenant_id = get_tenant_id(request)
    current = rate_limiter.get_tenant_usage(tenant_id)

    # Plan info
    plan = None
    if DOLT_ENABLED:
        plan = await fetchone(
            "SELECT plan_tier, api_calls_per_minute, computations_per_day, "
            "ocr_pages_per_month, agent_messages_per_day "
            "FROM tenant_plans WHERE tenant_id = %s", (tenant_id,)
        )

    # Recent daily history
    daily = []
    if DOLT_ENABLED:
        daily = await fetchall(
            "SELECT event_type, event_date, event_count FROM usage_daily "
            "WHERE tenant_id = %s ORDER BY event_date DESC LIMIT 14",
            (tenant_id,),
        )

    return {
        "tenant_id": tenant_id,
        "plan": dict(plan) if plan else {"plan_tier": "starter"},
        "current_usage": current,
        "daily_history": [
            {"type": r["event_type"], "date": str(r["event_date"]),
             "count": r["event_count"]} for r in daily
        ],
    }


# --- Admin monitoring ---

@router.get("/admin/monitoring/overview")
async def admin_overview(_admin: str = Depends(require_admin)):
    """Platform-wide usage overview for admins."""
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled")

    # Total tenants by status
    tenants = await fetchall(
        "SELECT status, COUNT(*) as cnt FROM tenants GROUP BY status"
    )

    # Total usage today
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_usage = await fetchall(
        "SELECT event_type, SUM(event_count) as total FROM usage_daily "
        "WHERE event_date = %s GROUP BY event_type", (today,)
    )

    # Billing summary
    billing = await fetchall(
        "SELECT subscription_status, COUNT(*) as cnt, plan_tier "
        "FROM billing_customers GROUP BY subscription_status, plan_tier"
    )

    return {
        "tenants": {r["status"]: r["cnt"] for r in tenants},
        "today_usage": {r["event_type"]: r["total"] for r in today_usage},
        "billing": [dict(r) for r in billing],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/admin/monitoring/tenants/{tenant_id}/usage")
async def admin_tenant_usage(tenant_id: str,
                             days: int = Query(default=7, le=90),
                             _admin: str = Depends(require_admin)):
    """Per-tenant usage breakdown for admins."""
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled")

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    daily = await fetchall(
        "SELECT event_type, event_date, event_count FROM usage_daily "
        "WHERE tenant_id = %s AND event_date >= %s ORDER BY event_date DESC",
        (tenant_id, since),
    )

    # Current real-time counters
    current = rate_limiter.get_tenant_usage(tenant_id)

    # Plan limits
    plan = await fetchone(
        "SELECT * FROM tenant_plans WHERE tenant_id = %s", (tenant_id,)
    )

    return {
        "tenant_id": tenant_id,
        "plan": dict(plan) if plan else None,
        "current_usage": current,
        "daily": [
            {"type": r["event_type"], "date": str(r["event_date"]),
             "count": r["event_count"]} for r in daily
        ],
    }


@router.get("/admin/monitoring/anomalies")
async def admin_anomalies(_admin: str = Depends(require_admin)):
    """Detect usage anomalies (>3x average) across tenants."""
    if not DOLT_ENABLED:
        raise HTTPException(503, "Dolt not enabled")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    # Get today's usage per tenant
    today_data = await fetchall(
        "SELECT tenant_id, event_type, SUM(event_count) as today_total "
        "FROM usage_daily WHERE event_date = %s GROUP BY tenant_id, event_type",
        (today,),
    )

    # Get 7-day averages per tenant
    avg_data = await fetchall(
        "SELECT tenant_id, event_type, AVG(event_count) as avg_count "
        "FROM usage_daily WHERE event_date >= %s AND event_date < %s "
        "GROUP BY tenant_id, event_type",
        (week_ago, today),
    )

    avg_map = {}
    for r in avg_data:
        key = (r["tenant_id"], r["event_type"])
        avg_map[key] = float(r["avg_count"]) if r["avg_count"] else 0

    anomalies = []
    for r in today_data:
        key = (r["tenant_id"], r["event_type"])
        avg = avg_map.get(key, 0)
        today_total = r["today_total"] or 0
        if avg > 0 and today_total > avg * 3:
            anomalies.append({
                "tenant_id": r["tenant_id"],
                "event_type": r["event_type"],
                "today": today_total,
                "avg_7d": round(avg, 1),
                "ratio": round(today_total / avg, 1),
            })

    return {"anomalies": anomalies, "threshold": "3x 7-day average"}
