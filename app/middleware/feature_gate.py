"""Per-tenant feature gate middleware.

Loads tenant_features from PostgREST (LRU-cached) and blocks access to
endpoints that require features the tenant doesn't have.

Uses pure ASGI (not BaseHTTPMiddleware) to avoid deadlocks with async httpx.

Upload/analyze are allowed for ALL tiers (NIST/IRS document retention).
Form-type and schedule gating is enforced at the route level, not here.
"""

import json
import logging
import time
from collections import OrderedDict

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from db.postgrest_client import postgrest, DB_ENABLED

logger = logging.getLogger(__name__)

# Path prefix → required boolean feature flag
FEATURE_GATES = {
    "/mcp": "can_use_mcp",
    "/plaid": "can_use_plaid",
}

# Paths that skip feature gating entirely
_SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/billing/webhook",
               "/billing/plans", "/whoami"}
_SKIP_PREFIXES = ("/admin", "/onboarding", "/billing")

# --- Feature Cache (5-min TTL, 256 entries) ---
_FEAT_CACHE_MAX = 256
_FEAT_CACHE_TTL = 300  # 5 minutes
_feat_cache: OrderedDict[str, tuple[dict, float]] = OrderedDict()


def _cache_get(tenant_id: str) -> dict | None:
    entry = _feat_cache.get(tenant_id)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > _FEAT_CACHE_TTL:
        _feat_cache.pop(tenant_id, None)
        return None
    _feat_cache.move_to_end(tenant_id)
    return result


def _cache_put(tenant_id: str, result: dict) -> None:
    _feat_cache[tenant_id] = (result, time.monotonic())
    if len(_feat_cache) > _FEAT_CACHE_MAX:
        _feat_cache.popitem(last=False)


def invalidate_cache(tenant_id: str | None = None):
    """Clear feature cache for a tenant (or all tenants)."""
    if tenant_id:
        _feat_cache.pop(tenant_id, None)
    else:
        _feat_cache.clear()


async def get_tenant_features(tenant_id: str) -> dict:
    """Load tenant features from cache or PostgREST."""
    cached = _cache_get(tenant_id)
    if cached is not None:
        return cached

    if not DB_ENABLED:
        return {}

    try:
        admin_token = postgrest.mint_jwt("__admin__", role="app_admin")
        rows = await postgrest.get(
            "tenant_features",
            {"tenant_id": f"eq.{tenant_id}"},
            token=admin_token,
        )
        if rows:
            features = rows[0]
            _cache_put(tenant_id, features)
            return features
    except Exception as e:
        logger.warning("Failed to load tenant features for %s: %s", tenant_id, e)

    return {}


class FeatureGateMiddleware:
    """Pure ASGI middleware — block requests to gated endpoints."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path
        tenant_id = getattr(request.state, "tenant_id", None)

        # Skip paths that don't need feature gating
        if path in _SKIP_PATHS or not tenant_id or tenant_id == "__admin__":
            await self.app(scope, receive, send)
            return

        for prefix in _SKIP_PREFIXES:
            if path.startswith(prefix):
                await self.app(scope, receive, send)
                return

        # Check path-based feature gates
        for gate_path, feature_name in FEATURE_GATES.items():
            if path.startswith(gate_path):
                features = await get_tenant_features(tenant_id)
                if not features.get(feature_name, False):
                    resp = JSONResponse(
                        status_code=403,
                        content={
                            "error": "Upgrade to access this feature",
                            "feature": feature_name,
                            "upgrade_url": "/billing/plans",
                        },
                    )
                    await resp(scope, receive, send)
                    return
                break

        # Load features onto request.state for route-level checks
        if not hasattr(request.state, "features"):
            features = await get_tenant_features(tenant_id)
            request.state.features = features

        await self.app(scope, receive, send)
