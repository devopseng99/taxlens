"""Monitoring routes — usage dashboards, per-tenant metrics."""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, HTTPException, Depends, Query

from auth import require_auth, require_admin, get_tenant_id
from db.postgrest_client import postgrest, DB_ENABLED
from rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monitoring"])


# --- Tenant-facing usage ---

@router.get("/usage/me")
async def my_usage(request: Request, _auth: str = Depends(require_auth)):
    """Get usage summary for the authenticated tenant."""
    tenant_id = get_tenant_id(request)
    current = rate_limiter.get_tenant_usage(tenant_id)

    plan = None
    daily = []
    if DB_ENABLED:
        token = getattr(request.state, "db_token", None) or postgrest.mint_jwt(tenant_id)
        plans = await postgrest.get("tenant_plans", {"tenant_id": f"eq.{tenant_id}"}, token=token)
        plan = plans[0] if plans else None

        daily = await postgrest.get(
            "usage_daily",
            {"tenant_id": f"eq.{tenant_id}", "order": "event_date.desc", "limit": "14"},
            token=token,
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
async def admin_overview(request: Request, _admin: str = Depends(require_admin)):
    """Platform-wide usage overview for admins."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled")

    token = getattr(request.state, "db_token", None) or postgrest.mint_jwt("__admin__", role="app_admin")

    # Get all tenants and aggregate by status
    tenants = await postgrest.get("tenants", token=token, select="status")
    status_counts = {}
    for t in tenants:
        s = t["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_usage = await postgrest.get(
        "usage_daily", {"event_date": f"eq.{today}"}, token=token,
    )
    usage_totals = {}
    for r in today_usage:
        et = r["event_type"]
        usage_totals[et] = usage_totals.get(et, 0) + r["event_count"]

    billing = await postgrest.get("billing_customers", token=token,
                                   select="subscription_status,plan_tier")
    billing_summary = []
    seen = {}
    for b in billing:
        key = (b["subscription_status"], b["plan_tier"])
        seen[key] = seen.get(key, 0) + 1
    for (status, tier), cnt in seen.items():
        billing_summary.append({"subscription_status": status, "plan_tier": tier, "cnt": cnt})

    return {
        "tenants": status_counts,
        "today_usage": usage_totals,
        "billing": billing_summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/admin/monitoring/tenants/{tenant_id}/usage")
async def admin_tenant_usage(tenant_id: str, request: Request,
                             days: int = Query(default=7, le=90),
                             _admin: str = Depends(require_admin)):
    """Per-tenant usage breakdown for admins."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled")

    token = getattr(request.state, "db_token", None) or postgrest.mint_jwt("__admin__", role="app_admin")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    daily = await postgrest.get(
        "usage_daily",
        {"tenant_id": f"eq.{tenant_id}", "event_date": f"gte.{since}",
         "order": "event_date.desc"},
        token=token,
    )

    current = rate_limiter.get_tenant_usage(tenant_id)

    plans = await postgrest.get("tenant_plans", {"tenant_id": f"eq.{tenant_id}"}, token=token)
    plan = plans[0] if plans else None

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
async def admin_anomalies(request: Request, _admin: str = Depends(require_admin)):
    """Detect usage anomalies (>3x average) across tenants."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled")

    token = getattr(request.state, "db_token", None) or postgrest.mint_jwt("__admin__", role="app_admin")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    today_data = await postgrest.get(
        "usage_daily", {"event_date": f"eq.{today}"}, token=token,
    )

    week_data = await postgrest.get(
        "usage_daily",
        {"event_date": f"gte.{week_ago}", "event_date": f"lt.{today}"},
        token=token,
    )

    # Build 7-day averages
    avg_map = {}
    count_map = {}
    for r in week_data:
        key = (r["tenant_id"], r["event_type"])
        avg_map[key] = avg_map.get(key, 0) + r["event_count"]
        count_map[key] = count_map.get(key, 0) + 1
    for key in avg_map:
        avg_map[key] = avg_map[key] / max(count_map[key], 1)

    # Build today totals
    today_map = {}
    for r in today_data:
        key = (r["tenant_id"], r["event_type"])
        today_map[key] = today_map.get(key, 0) + r["event_count"]

    anomalies = []
    for key, today_total in today_map.items():
        avg = avg_map.get(key, 0)
        if avg > 0 and today_total > avg * 3:
            anomalies.append({
                "tenant_id": key[0], "event_type": key[1],
                "today": today_total, "avg_7d": round(avg, 1),
                "ratio": round(today_total / avg, 1),
            })

    return {"anomalies": anomalies, "threshold": "3x 7-day average"}
