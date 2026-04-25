"""TaxLens Agentic Tax Intelligence Platform — multi-tenant SaaS with PostgreSQL + PostgREST."""

import os
import uuid
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from ocr import analyze_document
from bridge import ocr_to_w2_payload, write_populated_data
from tax_routes import router as tax_router
from plaid_routes import router as plaid_router
from admin_routes import router as admin_router
from billing_routes import router as billing_router
from monitoring import router as monitoring_router
from oauth import router as oauth_router
from auth import require_auth, AUTH_ENABLED
from contextlib import asynccontextmanager
from mcp_server import mcp
from db.postgrest_client import postgrest, DB_ENABLED
from middleware.tenant_context import TenantContextMiddleware
from middleware.feature_gate import FeatureGateMiddleware
from middleware.request_id import RequestIDMiddleware
from metering import metering
from rate_limiter import rate_limiter, ip_rate_limiter, IP_RATE_LIMITS
from prometheus_fastapi_instrumentator import Instrumentator

from pythonjsonlogger.json import JsonFormatter

# --- Structured JSON Logging ---
_json_formatter = JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
)
_handler = logging.StreamHandler()
_handler.setFormatter(_json_formatter)
logging.root.handlers = [_handler]
logging.root.setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Suppress noisy INFO loggers — only WARN+ reaches stdout
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Create MCP Starlette app (initializes session_manager lazily)
_mcp_starlette = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app):
    """Initialize PostgREST client, start MCP session manager, metering."""
    if DB_ENABLED:
        logger.info("PostgREST database enabled: %s",
                     os.getenv("POSTGREST_URL", "(default)"))

    # Start metering logger
    await metering.start()
    logger.info("TaxLens API starting (v3.61.0)")

    async with mcp.session_manager.run():
        yield

    # Graceful shutdown — flush pending metering events
    logger.info("TaxLens API shutting down — flushing metering buffer")
    await metering.stop()
    try:
        from redis_client import close as redis_close
        await redis_close()
    except Exception:
        pass
    await postgrest.close()
    logger.info("TaxLens API shutdown complete")


app = FastAPI(
    title="TaxLens Agentic Tax Intelligence Platform",
    version="3.61.0",
    description=(
        "Multi-tenant tax intelligence API. Computes federal 1040 + state returns, "
        "generates IRS-compliant PDFs, and supports MCP (Model Context Protocol) "
        "for AI agent integration. Covers 53+ tax forms, 10 states, OCR document "
        "processing, and scenario optimization."
    ),
    docs_url="/docs",
    root_path="/api",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Tax Drafts", "description": "Create, retrieve, and manage tax computations"},
        {"name": "Documents", "description": "Upload and OCR tax documents"},
        {"name": "Admin", "description": "Tenant provisioning, API key management, OAuth clients"},
        {"name": "Billing", "description": "Stripe checkout, subscription management, usage"},
        {"name": "Monitoring", "description": "Usage tracking and admin monitoring"},
        {"name": "Documentation", "description": "API guides, MCP integration, PostgREST spec"},
        {"name": "oauth", "description": "OAuth 2.0 token endpoint (RFC 6749 + PKCE)"},
        {"name": "Content", "description": "Landing page content (about, security, for-businesses)"},
    ],
)

# --- Prometheus Metrics ---
instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/docs", "/openapi.json", "/metrics"],
)
instrumentator.instrument(app)
instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)

# --- Metering + Rate Limiting Middleware ---
# NOTE: Starlette middleware execution order is LIFO — last added runs first.
# We need: CORS (outermost) → TenantContext (sets tenant_id) → MeteringRateLimit (reads tenant_id)
# So add in reverse order: MeteringRateLimit first, TenantContext second, CORS last.
#
# IMPORTANT: Both middlewares are pure ASGI (not BaseHTTPMiddleware) to avoid
# deadlocks when async httpx calls (PostgREST) are used inside the middleware chain.
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from metering import EVENT_API_CALL


class MeteringRateLimitMiddleware:
    """Pure ASGI middleware — log API calls and enforce rate limits."""

    EXEMPT_PATHS = {"/health", "/billing/webhook", "/billing/plans",
                    "/billing/onboarding/free", "/docs", "/openapi.json",
                    "/mcp", "/mcp/", "/metrics", "/oauth/token"}

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = StarletteRequest(scope)
        path = request.url.path
        tenant_id = getattr(request.state, "tenant_id", None)

        if path in self.EXEMPT_PATHS or not tenant_id:
            # Apply IP-based rate limiting on public endpoints
            ip_limit = IP_RATE_LIMITS.get(path)
            if ip_limit:
                client_ip = request.client.host if request.client else "0.0.0.0"
                ip_allowed, ip_headers = ip_rate_limiter.check(client_ip, ip_limit)
                if not ip_allowed:
                    resp = StarletteJSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit exceeded. Please retry later."},
                        headers=ip_headers,
                    )
                    await resp(scope, receive, send)
                    return
            await self.app(scope, receive, send)
            return

        allowed, headers = await rate_limiter.check_api_rate(tenant_id)
        if not allowed:
            resp = StarletteJSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry later."},
                headers=headers,
            )
            await resp(scope, receive, send)
            return

        # Inject rate limit headers into the response
        headers_to_add = [(k.lower().encode(), v.encode()) for k, v in headers.items()]

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = list(message.get("headers", []))
                existing.extend(headers_to_add)
                message["headers"] = existing
            await send(message)

        await self.app(scope, receive, send_with_headers)

        # Fire-and-forget metering (non-blocking buffer)
        await metering.log(tenant_id, EVENT_API_CALL, endpoint=path)


# Add innermost first, outermost last (LIFO execution)
# Order: CORS (outermost) → RequestID → TenantContext → FeatureGate → MeteringRateLimit (innermost)
app.add_middleware(MeteringRateLimitMiddleware)
app.add_middleware(FeatureGateMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(RequestIDMiddleware)

_PORTAL_URL = os.getenv("TAXLENS_PORTAL_URL", "https://taxlens-portal.istayintek.com")
_API_URL = os.getenv("TAXLENS_API_URL", "https://dropit.istayintek.com/api")
_LANDING_URL = os.getenv("TAXLENS_LANDING_URL", "https://taxlens.istayintek.com")

_cors_origins = [_LANDING_URL, _PORTAL_URL]
_api_base = _API_URL.rsplit("/api", 1)[0]  # e.g. "https://dropit.istayintek.com"
if _api_base not in _cors_origins:
    _cors_origins.append(_api_base)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Config from env ---
STORAGE_ROOT = Path(os.getenv("TAXLENS_STORAGE_ROOT", "/data/documents"))
MAX_FILE_SIZE = int(os.getenv("TAXLENS_MAX_FILE_MB", "30")) * 1024 * 1024  # 30MB default

# Mount tax draft routes
app.include_router(tax_router)

# Mount Plaid integration routes
app.include_router(plaid_router)

# Mount admin/provisioning routes
app.include_router(admin_router)

# Mount billing routes (Stripe checkout, webhooks, usage)
app.include_router(billing_router)

# Mount monitoring routes (usage/me, admin monitoring)
app.include_router(monitoring_router)

# Mount OAuth token endpoint
app.include_router(oauth_router)

# Mount MCP server (StreamableHTTP at /mcp)
# Accessible at https://dropit.istayintek.com/api/mcp
# Session manager lifecycle managed by FastAPI lifespan above
from starlette.routing import Mount, Route
from mcp.server.fastmcp.server import StreamableHTTPASGIApp

_mcp_asgi = StreamableHTTPASGIApp(mcp.session_manager)
app.router.routes.append(Route("/mcp", endpoint=_mcp_asgi))
app.router.routes.append(Route("/mcp/", endpoint=_mcp_asgi))


# --- Models ---
class DocumentMetadata(BaseModel):
    proc_id: str
    username: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_at: str
    storage_path: str


class OcrResult(BaseModel):
    proc_id: str
    model_id: str
    form_type: str | None = None
    fields: dict
    confidence: float
    pages: int
    raw_path: str | None = None


# --- Helpers ---
def user_dir(username: str) -> Path:
    """Safe user directory — no path traversal."""
    safe = username.replace("/", "_").replace("..", "_").replace("\\", "_")
    return STORAGE_ROOT / safe


def doc_dir(username: str, proc_id: str) -> Path:
    return user_dir(username) / proc_id


# Azure doc_type strings → simplified form type
_DOC_TYPE_MAP = {
    "tax.us.w2": "W-2",
    "tax.us.1099Int": "1099-INT",
    "tax.us.1099Div": "1099-DIV",
    "tax.us.1099Nec": "1099-NEC",
    "tax.us.1099Misc": "1099-MISC",
    "tax.us.1098": "1098",
    "tax.us.1099B": "1099-B",
    "tax.us.1040": "1040",
}


def _detect_form_type(doc_type: str | None, model_id: str) -> str | None:
    """Detect tax form type from Azure doc_type or model_id."""
    if doc_type:
        for key, form in _DOC_TYPE_MAP.items():
            if key.lower() in doc_type.lower():
                return form
        return doc_type
    model_lower = model_id.lower()
    if "w2" in model_lower:
        return "W-2"
    if "1099int" in model_lower:
        return "1099-INT"
    if "1099div" in model_lower:
        return "1099-DIV"
    if "1099nec" in model_lower:
        return "1099-NEC"
    if "1098" in model_lower:
        return "1098"
    return None


# --- Endpoints ---

import time as _time
_STARTUP_TIME = _time.time()


@app.get("/health")
async def health(deep: bool = False):
    from plaid_routes import PLAID_ENABLED
    from billing import STRIPE_ENABLED, STRIPE_MODE
    from email_service import EMAIL_ENABLED

    db_ok = False
    db_latency_ms = None
    if DB_ENABLED:
        try:
            import httpx
            from db.postgrest_client import POSTGREST_URL
            t0 = _time.monotonic()
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{POSTGREST_URL}/")
                db_ok = r.status_code == 200
            db_latency_ms = round((_time.monotonic() - t0) * 1000, 1)
        except Exception:
            db_ok = False
    else:
        db_ok = True  # No DB to check

    storage_writable = STORAGE_ROOT.exists()
    status = "ok" if (db_ok and storage_writable) else "degraded"

    result = {
        "status": status,
        "version": "3.61.0",
        "uptime_seconds": round(_time.time() - _STARTUP_TIME),
        "storage_root": str(STORAGE_ROOT),
        "writable": storage_writable,
        "auth_enabled": AUTH_ENABLED,
        "db_enabled": DB_ENABLED,
        "db_ok": db_ok,
        "db_provider": "postgrest" if DB_ENABLED else "none",
        "stripe_enabled": STRIPE_ENABLED,
        "stripe_mode": STRIPE_MODE,
        "mcp_endpoint": "/api/mcp",
        "plaid_enabled": PLAID_ENABLED,
        "email_enabled": EMAIL_ENABLED,
    }

    # Redis health
    try:
        from redis_client import health_check as redis_health_check
        redis_status = await redis_health_check()
        result.update(redis_status)
    except Exception:
        result["redis_enabled"] = False

    if deep and db_latency_ms is not None:
        result["db_latency_ms"] = db_latency_ms

    if deep:
        # Check storage write capability
        try:
            test_file = STORAGE_ROOT / ".health_check"
            test_file.write_text("ok")
            test_file.unlink()
            result["storage_write_ok"] = True
        except Exception:
            result["storage_write_ok"] = False
            status = "degraded"
            result["status"] = status

    # Scaling status
    try:
        from scaling import get_scaling_status
        ss = get_scaling_status()
        result["scaling"] = {
            "metering_backend": ss.metering_backend,
            "buffer_size": ss.buffer_size,
            "tenants_tracked": ss.tenants_tracked,
        }
    except Exception:
        pass

    return result


@app.get("/ready")
async def readiness():
    """Readiness probe — returns 200 only when all dependencies are available."""
    db_ok = True
    if DB_ENABLED:
        try:
            import httpx
            from db.postgrest_client import POSTGREST_URL
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{POSTGREST_URL}/")
                db_ok = r.status_code == 200
        except Exception:
            db_ok = False

    storage_ok = STORAGE_ROOT.exists()

    if db_ok and storage_ok:
        return {"ready": True}
    else:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"ready": False, "db_ok": db_ok, "storage_ok": storage_ok},
        )


@app.get(
    "/postgrest-openapi",
    summary="PostgREST OpenAPI spec",
    description="Proxy the PostgREST auto-generated OpenAPI 3.0 spec. "
                "Shows all database tables/views available via the REST API.",
    tags=["Documentation"],
)
async def postgrest_openapi():
    """Proxy PostgREST OpenAPI spec with caching."""
    if not DB_ENABLED:
        raise HTTPException(503, "Database not enabled")

    # Try Redis cache first
    try:
        from redis_client import get_redis
        r = await get_redis()
        if r:
            cached = await r.get("postgrest_openapi")
            if cached:
                return JSONResponse(json.loads(cached),
                                    media_type="application/json")
    except Exception:
        pass

    # Fetch from PostgREST
    import httpx as _httpx
    from db.postgrest_client import POSTGREST_URL
    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{POSTGREST_URL}/")
            resp.raise_for_status()
            spec = resp.json()
    except Exception as e:
        raise HTTPException(502, f"PostgREST unreachable: {e}")

    # Cache in Redis (5 min TTL)
    try:
        from redis_client import get_redis
        r = await get_redis()
        if r:
            await r.set("postgrest_openapi", json.dumps(spec), ex=300)
    except Exception:
        pass

    return JSONResponse(spec, media_type="application/json")


@app.get(
    "/docs/api-guide",
    summary="API quick-start guide",
    description="Returns a structured API guide with authentication, endpoints, and examples.",
    tags=["Documentation"],
)
async def api_guide():
    """Structured API guide for developers and MCP integrators."""
    base_url = os.getenv("TAXLENS_API_URL", "https://dropit.istayintek.com/api")
    return {
        "title": "TaxLens API Quick-Start Guide",
        "version": "3.61.0",
        "base_url": base_url,
        "authentication": {
            "methods": [
                {
                    "type": "API Key",
                    "header": "X-API-Key",
                    "description": "Include your API key in the X-API-Key header. "
                                   "Provisioned via admin endpoints.",
                },
                {
                    "type": "OAuth 2.0 Bearer Token",
                    "header": "Authorization: Bearer <token>",
                    "token_endpoint": f"{base_url}/oauth/token",
                    "grant_types": ["client_credentials", "authorization_code", "refresh_token"],
                    "description": "Use POST /oauth/token with client_credentials grant for MCP agents. "
                                   "PKCE S256 required for authorization_code.",
                },
            ],
            "scopes": ["compute", "drafts", "documents", "mcp", "plaid"],
        },
        "endpoints": {
            "tax_drafts": {
                "create": {"method": "POST", "path": "/tax-draft",
                           "description": "Compute a full tax return from OCR + inputs"},
                "get": {"method": "GET", "path": "/tax-draft/{draft_id}",
                        "description": "Retrieve draft results"},
                "list": {"method": "GET", "path": "/tax-drafts/{username}",
                         "description": "List all drafts for a user"},
                "download_pdf": {"method": "GET", "path": "/tax-draft/{draft_id}/pdf/{form}",
                                 "description": "Download a specific form PDF"},
                "list_pdfs": {"method": "GET", "path": "/tax-draft/{draft_id}/pdfs",
                              "description": "List available PDFs for a draft"},
            },
            "documents": {
                "upload": {"method": "POST", "path": "/upload",
                           "description": "Upload a tax document (PDF/image)"},
                "analyze": {"method": "POST", "path": "/analyze/{proc_id}",
                            "description": "Run Azure OCR on an uploaded document"},
            },
            "mcp": {
                "endpoint": f"{base_url}/mcp",
                "description": "Model Context Protocol (StreamableHTTP). "
                               "9 tools: compute_tax_scenario, get_tax_summary, list_deductions, "
                               "optimize_deductions, compare_scenarios, estimate_quarterly_payments, "
                               "list_states, get_filing_requirements, check_audit_risk",
            },
            "billing": {
                "plans": {"method": "GET", "path": "/billing/plans"},
                "onboarding": {"method": "POST", "path": "/billing/onboarding/free"},
                "checkout": {"method": "POST", "path": "/billing/checkout"},
            },
            "oauth": {
                "token": {"method": "POST", "path": "/oauth/token",
                          "content_type": "application/x-www-form-urlencoded",
                          "description": "Exchange credentials for access + refresh tokens"},
            },
        },
        "rate_limits": {
            "free": "10 API calls/min, 5 computations/day",
            "starter": "30 API calls/min, 50 computations/day",
            "professional": "120 API calls/min, 500 computations/day",
            "enterprise": "600 API calls/min, unlimited computations",
            "headers": ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
        },
        "interactive_docs": f"{base_url}/docs",
        "openapi_spec": f"{base_url}/openapi.json",
        "postgrest_spec": f"{base_url}/postgrest-openapi",
    }


@app.get(
    "/docs/mcp-guide",
    summary="MCP integration guide",
    description="Guide for integrating TaxLens as an MCP server with Claude Desktop or other MCP clients.",
    tags=["Documentation"],
)
async def mcp_guide():
    """MCP integration guide for Claude Desktop and MCP clients."""
    base_url = os.getenv("TAXLENS_API_URL", "https://dropit.istayintek.com/api")
    return {
        "title": "TaxLens MCP Integration Guide",
        "protocol": "StreamableHTTP",
        "endpoint": f"{base_url}/mcp",
        "authentication": {
            "method": "OAuth 2.0",
            "grant_type": "client_credentials",
            "token_endpoint": f"{base_url}/oauth/token",
        },
        "claude_desktop_config": {
            "mcpServers": {
                "taxlens": {
                    "url": f"{base_url}/mcp",
                    "oauth": {
                        "client_id": "<your_client_id>",
                        "client_secret": "<your_client_secret>",
                        "token_endpoint": f"{base_url}/oauth/token",
                    },
                }
            }
        },
        "available_tools": [
            {"name": "compute_tax_scenario", "description": "Compute federal + state tax for given inputs"},
            {"name": "get_tax_summary", "description": "Get formatted summary of a tax computation"},
            {"name": "list_deductions", "description": "List all available deductions with eligibility"},
            {"name": "optimize_deductions", "description": "Compare standard vs itemized deductions"},
            {"name": "compare_scenarios", "description": "Compare two tax scenarios side-by-side"},
            {"name": "estimate_quarterly_payments", "description": "Compute estimated quarterly payments"},
            {"name": "list_states", "description": "List supported state tax engines"},
            {"name": "get_filing_requirements", "description": "Determine if filing is required"},
            {"name": "check_audit_risk", "description": "Assess audit risk factors for a return"},
        ],
        "example_prompts": [
            "What would my taxes be with $120K salary, married filing jointly, 2 kids?",
            "Compare standard deduction vs itemized with $25K mortgage interest",
            "How much should I pay in estimated taxes per quarter?",
        ],
    }


@app.get(
    "/content/about",
    summary="About page content",
    tags=["Content"],
)
async def about_content():
    """Structured content for the /about landing page."""
    return {
        "title": "About TaxLens",
        "tagline": "Agentic Tax Intelligence for Everyone",
        "mission": (
            "TaxLens makes tax computation transparent, accessible, and programmable. "
            "Built for CPAs, tax professionals, and developers who need accurate IRS-compliant "
            "calculations without black-box software."
        ),
        "platform": {
            "forms_supported": "53+ IRS forms and schedules",
            "states": "10 state tax engines (IL, CA, NY, TX, FL, PA, OH, GA, NC, NJ)",
            "ocr_types": "8 document types (W-2, 1099-INT/DIV/NEC/MISC/B, 1098)",
            "pdf_generators": "29+ IRS-compliant PDF generators",
            "api_endpoints": "60+ REST API endpoints",
            "mcp_tools": "9 AI agent tools via Model Context Protocol",
        },
        "technology": {
            "api": "FastAPI (Python 3.11) with PostgREST + PostgreSQL",
            "security": "Multi-tenant isolation via RLS, SHA-256 hashed API keys, OAuth 2.0 + PKCE",
            "deployment": "Kubernetes (RKE2) with Helm charts, Cloudflare tunnel",
            "monitoring": "Prometheus metrics, structured JSON logging",
        },
        "compliance": {
            "tax_years": ["2024", "2025"],
            "irs_forms": "Uses official IRS fillable PDF templates",
            "accuracy": "896+ unit tests covering edge cases, AMT, NIIT, phaseouts",
        },
    }


@app.get(
    "/content/security",
    summary="Security page content",
    tags=["Content"],
)
async def security_content():
    """Structured content for the /security landing page."""
    return {
        "title": "Security & Data Handling",
        "overview": (
            "TaxLens is designed with security-first principles. All tax data is "
            "tenant-isolated, encrypted in transit, and never shared across accounts."
        ),
        "data_handling": {
            "encryption_in_transit": "TLS 1.3 via Cloudflare tunnel (zero-trust)",
            "storage": "Local PVC on Kubernetes — no cloud storage, no third-party access",
            "multi_tenant_isolation": "PostgreSQL Row-Level Security (RLS) per tenant_id",
            "api_key_storage": "SHA-256 hashed — raw keys never stored",
            "oauth_tokens": "SHA-256 hashed with TTL-based expiry and rotation",
        },
        "authentication": {
            "methods": ["API Key (X-API-Key)", "OAuth 2.0 Bearer Token", "PKCE S256"],
            "admin_access": "Separate admin key, not API key",
            "rate_limiting": "Per-tenant token bucket + per-IP sliding window",
        },
        "infrastructure": {
            "kubernetes": "RKE2 on dedicated hardware",
            "no_cloud_vendors": "No AWS/GCP/Azure for core data storage",
            "ocr_processing": "Azure Document Intelligence (stateless, no data retention)",
            "audit_logging": "All CRUD operations logged via PostgreSQL triggers",
        },
        "responsible_disclosure": {
            "contact": "security@istayintek.com",
            "scope": "API endpoints, authentication, data isolation",
        },
    }


@app.get(
    "/content/for-businesses",
    summary="Business use cases",
    tags=["Content"],
)
async def for_businesses_content():
    """Structured content for the /for-businesses landing page."""
    return {
        "title": "TaxLens for Businesses",
        "subtitle": "Built for CPA firms, tax professionals, and fintech developers",
        "use_cases": [
            {
                "title": "CPA / EA Firms",
                "description": "Multi-client tax computation via API. Upload W-2s and 1099s, "
                               "get complete returns with PDFs. No per-return software licenses.",
                "features": ["Multi-tenant client isolation", "Batch document upload",
                             "PDF package with cover letter", "Audit risk assessment"],
            },
            {
                "title": "Fintech Integration",
                "description": "Embed tax computation in your app via REST API or MCP. "
                               "9 AI agent tools for conversational tax planning.",
                "features": ["OAuth 2.0 + PKCE authentication", "MCP for AI agents",
                             "Webhook notifications", "Stripe billing integration"],
            },
            {
                "title": "Tax Planning",
                "description": "Scenario comparison, quarterly estimates, withholding analysis. "
                               "Help clients optimize their tax position year-round.",
                "features": ["Side-by-side scenario comparison", "Quarterly payment calculator",
                             "Standard vs itemized optimization", "Multi-state support"],
            },
        ],
        "pricing": {
            "starter": {"price": "$29/mo", "computations": "50/day", "features": "Core forms + OCR"},
            "professional": {"price": "$99/mo", "computations": "500/day", "features": "All forms + MCP + Plaid"},
            "enterprise": {"price": "$299/mo", "computations": "Unlimited", "features": "Everything + priority support"},
        },
    }


@app.get("/whoami")
async def whoami(request: Request, _auth: str = Depends(require_auth)):
    """Return the authenticated tenant/user context."""
    return {
        "tenant_id": getattr(request.state, "tenant_id", None),
        "tenant_slug": getattr(request.state, "tenant_slug", None),
        "user_id": getattr(request.state, "user_id", None),
        "username": getattr(request.state, "username", None),
        "role": getattr(request.state, "role", None),
        "db_enabled": DB_ENABLED,
    }


# ---------------------------------------------------------------------------
# Tax Calendar
# ---------------------------------------------------------------------------
_TAX_CALENDAR_2025 = [
    {"date": "2026-01-15", "event": "Q4 2025 estimated tax payment due", "form": "1040-ES"},
    {"date": "2026-01-31", "event": "W-2 and 1099 forms due to taxpayers", "form": "W-2/1099"},
    {"date": "2026-02-18", "event": "1099-B due to taxpayers (brokerages)", "form": "1099-B"},
    {"date": "2026-03-15", "event": "S-Corp / Partnership returns due (Form 1065/1120-S)", "form": "1065/1120-S"},
    {"date": "2026-04-15", "event": "Individual tax return due (Form 1040)", "form": "1040"},
    {"date": "2026-04-15", "event": "Q1 2026 estimated tax payment due", "form": "1040-ES"},
    {"date": "2026-06-15", "event": "Q2 2026 estimated tax payment due", "form": "1040-ES"},
    {"date": "2026-06-15", "event": "Automatic extension for US citizens abroad", "form": "1040"},
    {"date": "2026-09-15", "event": "Q3 2026 estimated tax payment due", "form": "1040-ES"},
    {"date": "2026-09-15", "event": "Extended partnership/S-Corp returns due", "form": "1065/1120-S"},
    {"date": "2026-10-15", "event": "Extended individual return due (Form 4868)", "form": "1040"},
]

_STATE_DEADLINES = {
    "CA": [{"date": "2026-04-15", "event": "CA Form 540 due"}, {"date": "2026-10-15", "event": "CA extended return due"}],
    "NY": [{"date": "2026-04-15", "event": "NY IT-201/IT-203 due"}],
    "IL": [{"date": "2026-04-15", "event": "IL-1040 due"}],
    "NJ": [{"date": "2026-04-15", "event": "NJ-1040 due"}],
    "PA": [{"date": "2026-04-15", "event": "PA-40 due"}],
    "GA": [{"date": "2026-04-15", "event": "GA Form 500 due"}],
    "NC": [{"date": "2026-04-15", "event": "NC D-400 due"}],
    "OH": [{"date": "2026-04-15", "event": "OH IT-1040 due"}],
    "TX": [],
    "FL": [],
}


@app.get("/tax-calendar", tags=["Planning"])
async def tax_calendar(
    state: str = Query(default="", description="State code for state-specific deadlines"),
):
    """Return IRS tax calendar deadlines for 2025 tax year with optional state deadlines."""
    result = {"federal": _TAX_CALENDAR_2025}
    if state:
        state_upper = state.upper()
        state_events = _STATE_DEADLINES.get(state_upper, [])
        result["state"] = state_events
        result["state_code"] = state_upper
    return result


# ---------------------------------------------------------------------------
# Scenario Comparison (API wrapper for MCP tool)
# ---------------------------------------------------------------------------
@app.post("/compare-scenarios", tags=["Planning"])
async def compare_scenarios_api(
    scenarios: list[dict],
    _auth: str = Depends(require_auth),
):
    """Compare 2-4 tax filing scenarios side-by-side.

    Each scenario dict should have: label, filing_status, wages, and
    optional fields matching compute_tax parameters.
    """
    if len(scenarios) < 2:
        raise HTTPException(400, "Need at least 2 scenarios to compare")
    if len(scenarios) > 4:
        raise HTTPException(400, "Maximum 4 scenarios")

    from tax_engine import (
        PersonInfo, W2Income, Deductions, AdditionalIncome, Payments, compute_tax,
    )
    from tax_projector import _marginal_rate, _effective_rate

    results = []
    for i, scenario in enumerate(scenarios):
        label = scenario.pop("label", f"Scenario {i + 1}")
        filer = PersonInfo(first_name="Scenario", last_name=str(i + 1))
        w2s = [W2Income(
            wages=scenario.get("wages", 0),
            federal_withheld=scenario.get("federal_withheld", 0),
        )]
        result = compute_tax(
            filing_status=scenario.get("filing_status", "single"),
            filer=filer,
            w2s=w2s,
            deductions=Deductions(
                mortgage_interest=scenario.get("mortgage_interest", 0),
                property_tax=scenario.get("property_tax", 0),
                state_income_tax_paid=scenario.get("state_income_tax_paid", 0),
                charitable_cash=scenario.get("charitable_cash", 0),
                student_loan_interest=scenario.get("student_loan_interest", 0),
            ),
            additional=AdditionalIncome(
                other_interest=scenario.get("interest_income", 0),
                ordinary_dividends=scenario.get("dividend_income", 0),
            ),
            payments=Payments(
                estimated_federal=scenario.get("estimated_payments", 0),
            ),
            num_dependents=scenario.get("num_dependents", 0),
            residence_state=scenario.get("residence_state", ""),
        )
        results.append({
            "label": label,
            "filing_status": scenario.get("filing_status", "single"),
            "total_income": round(result.line_9_total_income, 2),
            "agi": round(result.line_11_agi, 2),
            "taxable_income": round(result.line_15_taxable_income, 2),
            "total_tax": round(result.line_24_total_tax, 2),
            "effective_rate": round(_effective_rate(result.line_24_total_tax, result.line_9_total_income) * 100, 2),
            "marginal_rate": round(_marginal_rate(result.line_15_taxable_income, scenario.get("filing_status", "single")) * 100, 2),
            "refund": round(result.line_34_overpaid, 2),
            "owed": round(result.line_37_owed, 2),
        })

    # Compute deltas from first scenario
    base = results[0]
    for r in results[1:]:
        r["tax_delta"] = round(r["total_tax"] - base["total_tax"], 2)
        r["refund_delta"] = round(r["refund"] - base["refund"], 2)

    return {"scenarios": results, "base_scenario": base["label"]}


# ---------------------------------------------------------------------------
# TCJA Sunset Comparison (2025 Current Law vs 2026 Sunset)
# ---------------------------------------------------------------------------
@app.post("/tcja-comparison", tags=["Planning"])
async def tcja_comparison(
    filing_status: str = Query(default="single"),
    wages: float = Query(default=0),
    federal_withheld: float = Query(default=0),
    business_income: float = Query(default=0),
    business_expenses: float = Query(default=0),
    mortgage_interest: float = Query(default=0),
    property_tax: float = Query(default=0),
    state_income_tax_paid: float = Query(default=0),
    charitable_cash: float = Query(default=0),
    num_dependents: int = Query(default=0),
    _auth: str = Depends(require_auth),
):
    """Compare identical income under 2025 current law vs 2026 TCJA sunset.

    Shows the tax impact of TCJA expiration: bracket reversion, SALT cap removal,
    QBI expiration, CTC reduction, personal exemption restoration, and lower
    standard deduction.
    """
    from tax_engine import (
        PersonInfo, W2Income, BusinessIncome, Deductions,
        AdditionalIncome, Payments, compute_tax,
    )
    from tax_projector import _marginal_rate, _effective_rate

    common_kwargs = dict(
        filing_status=filing_status,
        filer=PersonInfo(first_name="TCJA", last_name="Compare"),
        w2s=[W2Income(wages=wages, federal_withheld=federal_withheld)] if wages > 0 else [],
        businesses=[BusinessIncome(gross_receipts=business_income, other_expenses=business_expenses)] if business_income > 0 else [],
        additional=AdditionalIncome(),
        deductions=Deductions(
            mortgage_interest=mortgage_interest,
            property_tax=property_tax,
            state_income_tax_paid=state_income_tax_paid,
            charitable_cash=charitable_cash,
        ),
        payments=Payments(),
        num_dependents=num_dependents,
    )

    r2025 = compute_tax(**common_kwargs, tax_year=2025)
    r2026 = compute_tax(**common_kwargs, tax_year=2026)

    def _scenario(r, year):
        return {
            "tax_year": year,
            "total_income": round(r.line_9_total_income, 2),
            "agi": round(r.line_11_agi, 2),
            "deduction_type": r.deduction_type,
            "deduction_amount": round(r.line_13_deduction, 2),
            "personal_exemption": round(r.personal_exemption, 2),
            "qbi_deduction": round(r.qbi_deduction, 2),
            "taxable_income": round(r.line_15_taxable_income, 2),
            "total_tax": round(r.line_24_total_tax, 2),
            "effective_rate": round(_effective_rate(r.line_24_total_tax, r.line_9_total_income) * 100, 2),
            "marginal_rate": round(_marginal_rate(r.line_15_taxable_income, filing_status, year) * 100, 2),
            "ctc": round(r.line_27_ctc, 2),
            "refund": round(r.line_34_overpaid, 2),
            "owed": round(r.line_37_owed, 2),
        }

    s2025 = _scenario(r2025, 2025)
    s2026 = _scenario(r2026, 2026)

    # Key deltas
    tax_delta = round(s2026["total_tax"] - s2025["total_tax"], 2)

    tcja_impacts = []
    if s2026["qbi_deduction"] < s2025["qbi_deduction"]:
        tcja_impacts.append(f"QBI deduction lost: -${s2025['qbi_deduction']:,.0f}")
    if s2026["deduction_amount"] < s2025["deduction_amount"]:
        tcja_impacts.append(f"Standard deduction reduced: ${s2025['deduction_amount']:,.0f} → ${s2026['deduction_amount']:,.0f}")
    if s2026["personal_exemption"] > 0:
        tcja_impacts.append(f"Personal exemption restored: +${s2026['personal_exemption']:,.0f}")
    if s2026["ctc"] < s2025["ctc"]:
        tcja_impacts.append(f"CTC reduced: ${s2025['ctc']:,.0f} → ${s2026['ctc']:,.0f}")
    if s2026["marginal_rate"] != s2025["marginal_rate"]:
        tcja_impacts.append(f"Marginal rate change: {s2025['marginal_rate']}% → {s2026['marginal_rate']}%")
    salt_2025 = r2025.sched_a_salt
    salt_2026 = r2026.sched_a_salt
    if salt_2026 > salt_2025:
        tcja_impacts.append(f"SALT cap removed: ${salt_2025:,.0f} → ${salt_2026:,.0f}")

    return {
        "current_law_2025": s2025,
        "sunset_2026": s2026,
        "tax_increase": tax_delta,
        "tax_increase_pct": round((tax_delta / s2025["total_tax"] * 100) if s2025["total_tax"] > 0 else 0, 1),
        "tcja_impacts": tcja_impacts,
        "disclaimer": "2026 values are projections based on TCJA sunset provisions. "
                       "Congress may extend, modify, or replace these provisions.",
    }


# ---------------------------------------------------------------------------
# Entity Type Optimization (Sole Prop vs S-Corp vs C-Corp)
# ---------------------------------------------------------------------------
@app.post("/entity-comparison", tags=["Planning"])
async def entity_comparison(
    business_income: float = Query(..., description="Net business profit (Schedule C equivalent)"),
    filing_status: str = Query(default="single"),
    other_income: float = Query(default=0, description="Non-business income (W-2, interest, etc.)"),
    reasonable_compensation: float | None = Query(default=None, description="S-corp W-2 salary (auto-calculated if omitted)"),
    is_sstb: bool = Query(default=False, description="Specified Service Trade or Business (§199A(d)(2))"),
    tax_year: int = Query(default=2025, description="Tax year"),
    _auth: str = Depends(require_auth),
):
    """Compare tax burden under sole proprietorship, S-corp, and C-corp.

    Shows SE tax savings, FICA split, QBI deduction, and double-taxation
    impact for each entity structure. Includes reasonable compensation range.
    """
    from entity_optimizer import compare_entities, comparison_to_dict
    comp = compare_entities(
        business_income=business_income,
        filing_status=filing_status,
        other_income=other_income,
        reasonable_compensation=reasonable_compensation,
        is_sstb=is_sstb,
        tax_year=tax_year,
    )
    return comparison_to_dict(comp)


# ---------------------------------------------------------------------------
# Mega Backdoor Roth Calculator
# ---------------------------------------------------------------------------
@app.post("/mega-backdoor-roth", tags=["Planning"])
async def mega_backdoor_roth(
    employee_deferrals: float = Query(..., description="Total pre-tax + Roth 401(k) deferrals"),
    employer_match: float = Query(default=0, description="Employer matching contributions (vested)"),
    age_50_plus: bool = Query(default=False, description="Age 50+ for catch-up eligibility"),
    marginal_rate: float = Query(default=0.24, description="Expected marginal tax rate at withdrawal"),
    projection_years: int = Query(default=10, description="Years to project growth"),
    annual_return: float = Query(default=0.07, description="Expected annual return rate"),
    tax_year: int = Query(default=2025, description="Tax year"),
    _auth: str = Depends(require_auth),
):
    """Calculate mega backdoor Roth space and projected tax savings.

    Computes after-tax 401(k) contribution space under §415(c) limits,
    then projects Roth vs taxable growth over the specified period.
    """
    from mega_backdoor_roth import compute_mega_backdoor, result_to_dict
    result = compute_mega_backdoor(
        employee_deferrals=employee_deferrals,
        employer_match=employer_match,
        age_50_plus=age_50_plus,
        marginal_rate=marginal_rate,
        projection_years=projection_years,
        annual_return=annual_return,
        tax_year=tax_year,
    )
    return result_to_dict(result)


# ---------------------------------------------------------------------------
# Tax Projection + Roth Conversion
# ---------------------------------------------------------------------------
@app.post("/tax-projection", tags=["Planning"])
async def tax_projection(
    wages: float = Query(..., description="Current W-2 wages"),
    federal_withheld: float = Query(default=0, description="Current federal withholding"),
    filing_status: str = Query(default="single"),
    income_growth_rate: float = Query(default=0.03, description="Annual income growth (0.03 = 3%)"),
    interest_income: float = Query(default=0),
    dividend_income: float = Query(default=0),
    mortgage_interest: float = Query(default=0),
    property_tax: float = Query(default=0),
    charitable: float = Query(default=0),
    num_dependents: int = Query(default=0),
    _auth: str = Depends(require_auth),
):
    """Project tax liability across 3 years (2024-2026) with income growth."""
    from tax_projector import ProjectionScenario, project_tax_liability, get_2026_projected_constants

    base = ProjectionScenario(
        wages=wages, federal_withheld=federal_withheld,
        filing_status=filing_status, income_growth_rate=income_growth_rate,
        interest_income=interest_income, dividend_income=dividend_income,
        mortgage_interest=mortgage_interest, property_tax=property_tax,
        charitable=charitable, num_dependents=num_dependents,
    )
    projections = project_tax_liability(base)
    constants_2026 = get_2026_projected_constants()

    return {
        "projections": [
            {
                "tax_year": p.tax_year,
                "total_income": p.total_income,
                "agi": p.agi,
                "taxable_income": p.taxable_income,
                "total_tax": p.total_tax,
                "effective_rate": p.effective_rate,
                "marginal_rate": p.marginal_rate,
                "refund_or_owed": p.refund_or_owed,
                "is_projected": p.is_projected,
            }
            for p in projections
        ],
        "projected_2026_constants": constants_2026,
    }


@app.post("/roth-optimizer", tags=["Planning"])
async def roth_optimizer(
    wages: float = Query(..., description="W-2 wages"),
    federal_withheld: float = Query(default=0),
    other_income: float = Query(default=0, description="Other ordinary income"),
    filing_status: str = Query(default="single"),
    target_bracket_rate: float = Query(default=0.22, description="Target bracket (0.22 = 22%)"),
    max_conversion: float = Query(default=500000),
    _auth: str = Depends(require_auth),
):
    """Find optimal Roth conversion amount to stay within target bracket."""
    from tax_projector import optimize_roth_conversion

    result = optimize_roth_conversion(
        wages=wages, federal_withheld=federal_withheld,
        other_income=other_income, filing_status=filing_status,
        target_bracket_rate=target_bracket_rate,
        max_conversion=max_conversion,
    )
    return {
        "optimal_conversion": result.optimal_conversion,
        "tax_on_conversion": result.tax_on_conversion,
        "marginal_rate_at_conversion": result.marginal_rate_at_conversion,
        "stays_in_bracket": result.stays_in_bracket,
        "target_bracket_top": result.target_bracket_top,
        "total_tax_without_conversion": result.total_tax_without_conversion,
        "total_tax_with_conversion": result.total_tax_with_conversion,
    }


# ---------------------------------------------------------------------------
# Tax Optimization
# ---------------------------------------------------------------------------
@app.post("/optimize", tags=["Planning"])
async def optimize_taxes(
    wages: float = Query(...),
    federal_withheld: float = Query(default=0),
    filing_status: str = Query(default="single"),
    mortgage_interest: float = Query(default=0),
    property_tax: float = Query(default=0),
    state_income_tax: float = Query(default=0),
    charitable_cash: float = Query(default=0),
    interest_income: float = Query(default=0),
    business_income: float = Query(default=0),
    has_hsa: bool = Query(default=False),
    hsa_contribution: float = Query(default=0),
    age: int = Query(default=35),
    num_dependents: int = Query(default=0),
    ira_contribution: float = Query(default=0),
    has_401k: bool = Query(default=False),
    contribution_401k: float = Query(default=0),
    capital_gains_long: float = Query(default=0),
    capital_losses: float = Query(default=0),
    _auth: str = Depends(require_auth),
):
    """Get personalized tax optimization recommendations with estimated savings."""
    from tax_optimizer import get_optimization_plan
    plan = get_optimization_plan(
        wages=wages, federal_withheld=federal_withheld,
        filing_status=filing_status, mortgage_interest=mortgage_interest,
        property_tax=property_tax, state_income_tax=state_income_tax,
        charitable_cash=charitable_cash, interest_income=interest_income,
        business_income=business_income, has_hsa=has_hsa,
        hsa_contribution=hsa_contribution, age=age,
        num_dependents=num_dependents, ira_contribution=ira_contribution,
        has_401k=has_401k, contribution_401k=contribution_401k,
        capital_gains_long=capital_gains_long, capital_losses=capital_losses,
    )
    return {
        "total_potential_savings": plan.total_potential_savings,
        "current_tax": plan.current_tax,
        "optimized_tax": plan.optimized_tax,
        "recommendation_count": len(plan.recommendations),
        "recommendations": [
            {
                "strategy": r.strategy,
                "category": r.category,
                "estimated_savings": r.estimated_savings,
                "difficulty": r.difficulty,
                "irs_risk": r.irs_risk,
                "description": r.description,
                "action_items": r.action_items,
            }
            for r in plan.recommendations
        ],
    }


@app.post("/withholding-check", tags=["Planning"])
async def withholding_check(
    annual_wages: float = Query(...),
    federal_withheld_ytd: float = Query(...),
    pay_periods_per_year: int = Query(default=26),
    pay_periods_elapsed: int = Query(default=0),
    filing_status: str = Query(default="single"),
    current_w4_extra: float = Query(default=0),
    num_dependents: int = Query(default=0),
    other_income: float = Query(default=0),
    deductions_above_standard: float = Query(default=0),
    estimated_payments: float = Query(default=0),
    target_refund: float = Query(default=0),
    _auth: str = Depends(require_auth),
):
    """Analyze withholding gap and recommend W-4 adjustments."""
    from withholding_analyzer import WithholdingInput, analyze_withholding
    inp = WithholdingInput(
        filing_status=filing_status,
        annual_wages=annual_wages,
        federal_withheld_ytd=federal_withheld_ytd,
        pay_periods_per_year=pay_periods_per_year,
        pay_periods_elapsed=pay_periods_elapsed,
        current_w4_extra=current_w4_extra,
        num_dependents=num_dependents,
        other_income=other_income,
        deductions_above_standard=deductions_above_standard,
        estimated_payments=estimated_payments,
        target_refund=target_refund,
    )
    result = analyze_withholding(inp)
    return {
        "projected_tax": round(result.projected_tax, 2),
        "projected_withholding": round(result.projected_withholding, 2),
        "projected_estimated": round(result.projected_estimated, 2),
        "projected_total_payments": round(result.projected_total_payments, 2),
        "gap": round(result.gap, 2),
        "gap_description": result.gap_description,
        "at_risk_of_penalty": result.at_risk_of_penalty,
        "safe_harbor_amount": round(result.safe_harbor_amount, 2),
        "recommended_extra_per_period": result.recommended_extra_per_period,
        "remaining_periods": result.remaining_periods,
        "adjustment_description": result.adjustment_description,
        "target_refund": result.target_refund,
        "target_withholding": round(result.target_withholding, 2),
        "effective_rate": round(result.effective_rate, 4),
        "marginal_rate": result.marginal_rate,
    }


# ---------------------------------------------------------------------------
# Webhook Management
# ---------------------------------------------------------------------------
@app.post("/webhooks", tags=["Webhooks"])
async def create_webhook(
    url: str = Query(...),
    events: str = Query(..., description="Comma-separated event types"),
    description: str = Query(default=""),
    _auth: str = Depends(require_auth),
    request: Request = None,
):
    """Register a webhook endpoint for event notifications."""
    from webhooks import create_endpoint, EVENT_TYPES
    tenant_id = getattr(request.state, "tenant_id", "default") if request else "default"
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    ep = create_endpoint(tenant_id=tenant_id, url=url, events=event_list, description=description)
    return {"id": ep.id, "url": ep.url, "events": ep.events, "secret": ep.secret, "active": ep.active}


@app.get("/webhooks", tags=["Webhooks"])
async def list_webhooks(
    _auth: str = Depends(require_auth),
    request: Request = None,
):
    """List all webhook endpoints for the current tenant."""
    from webhooks import list_endpoints
    tenant_id = getattr(request.state, "tenant_id", "default") if request else "default"
    endpoints = list_endpoints(tenant_id)
    return [{"id": ep.id, "url": ep.url, "events": ep.events, "active": ep.active, "description": ep.description} for ep in endpoints]


@app.delete("/webhooks/{endpoint_id}", tags=["Webhooks"])
async def delete_webhook(endpoint_id: str, _auth: str = Depends(require_auth)):
    """Delete a webhook endpoint."""
    from webhooks import delete_endpoint
    if not delete_endpoint(endpoint_id):
        raise HTTPException(404, "Webhook endpoint not found")
    return {"deleted": True}


@app.post("/webhooks/{endpoint_id}/test", tags=["Webhooks"])
async def test_webhook(endpoint_id: str, _auth: str = Depends(require_auth)):
    """Send a test event to a webhook endpoint."""
    from webhooks import test_endpoint
    delivery = test_endpoint(endpoint_id)
    return {"delivery_id": delivery.id, "success": delivery.success, "status_code": delivery.status_code}


@app.get("/webhooks/{endpoint_id}/deliveries", tags=["Webhooks"])
async def list_deliveries(endpoint_id: str, limit: int = Query(default=50), _auth: str = Depends(require_auth)):
    """Get delivery log for a webhook endpoint."""
    from webhooks import get_deliveries
    deliveries = get_deliveries(endpoint_id=endpoint_id, limit=limit)
    return [{"id": d.id, "event_type": d.event_type, "success": d.success, "status_code": d.status_code, "attempt": d.attempt, "created_at": d.created_at} for d in deliveries]


# ---------------------------------------------------------------------------
# Revenue Dashboard (Admin)
# ---------------------------------------------------------------------------
@app.get("/admin/dashboards", tags=["Admin"])
async def grafana_dashboards(_auth: str = Depends(require_auth)):
    """Grafana dashboard definitions and alert rules."""
    from grafana_dashboards import get_all_dashboards, get_alert_rules_yaml, CUSTOM_METRICS
    return {
        "dashboards": {k: v["dashboard"]["title"] for k, v in get_all_dashboards().items()},
        "alert_rules_count": len(get_alert_rules_yaml()),
        "custom_metrics_count": len(CUSTOM_METRICS),
    }


@app.get("/admin/revenue", tags=["Admin"])
async def revenue_dashboard(_auth: str = Depends(require_auth)):
    """Revenue dashboard — MRR, ARR, subscriber breakdown."""
    from stripe_live import compute_revenue_metrics, LIVE_PRODUCTS
    # In production, query billing_customers table; for now return demo data
    return {
        "products": {
            tier: {"name": p.name, "price_monthly": p.price_monthly / 100, "features": p.features}
            for tier, p in LIVE_PRODUCTS.items()
        },
        "metrics": {
            "total_subscribers": 0,
            "mrr": 0.0,
            "arr": 0.0,
            "subscribers_by_tier": {},
            "churn_rate": 0.0,
        },
    }


@app.post("/upload", response_model=DocumentMetadata)
async def upload_document(
    file: UploadFile = File(...),
    username: str = Form(...),
    doc_type: str = Form(default="auto"),
    _auth: str = Depends(require_auth),
):
    """Upload a tax document (PDF, image). Stored locally on PVC."""

    # Validate content type
    allowed = {"application/pdf", "image/jpeg", "image/png", "image/tiff", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Allowed: {', '.join(allowed)}")

    # Read and check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large: {len(content)} bytes. Max: {MAX_FILE_SIZE} bytes ({MAX_FILE_SIZE // (1024*1024)}MB)")

    # Generate processing ID and paths
    proc_id = uuid.uuid4().hex[:12]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ext = Path(file.filename).suffix if file.filename else ".bin"
    storage_name = f"{ts}_{proc_id}{ext}"

    dest_dir = doc_dir(username, proc_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / storage_name

    # Write file
    dest_path.write_bytes(content)

    # Compute SHA-256
    sha = hashlib.sha256(content).hexdigest()

    # Write metadata sidecar
    meta = DocumentMetadata(
        proc_id=proc_id,
        username=username,
        filename=file.filename or "unknown",
        content_type=file.content_type,
        size_bytes=len(content),
        sha256=sha,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        storage_path=str(dest_path.relative_to(STORAGE_ROOT)),
    )
    (dest_dir / "metadata.json").write_text(meta.model_dump_json(indent=2))

    return meta


@app.post("/analyze/{proc_id}", response_model=OcrResult)
async def analyze(
    proc_id: str,
    username: str = Query(...),
    model_id: str = Query(default="prebuilt-tax.us"),
    _auth: str = Depends(require_auth),
):
    """Run Azure Document Intelligence OCR on an uploaded document."""

    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404, f"Document {proc_id} not found for user {username}")

    files = [f for f in dest.iterdir() if f.name != "metadata.json" and f.name != "ocr_result.json"]
    if not files:
        raise HTTPException(404, f"No document file in {proc_id}")

    doc_file = files[0]

    try:
        result = await analyze_document(doc_file, model_id)
    except Exception as e:
        raise HTTPException(502, f"Azure OCR failed: {str(e)}")

    form_type = _detect_form_type(result.get("doc_type", ""), model_id)

    raw_data = result["raw"]
    raw_data["form_type"] = form_type
    ocr_path = dest / "ocr_result.json"
    ocr_path.write_text(json.dumps(raw_data, indent=2, default=str))

    ocr = OcrResult(
        proc_id=proc_id,
        model_id=model_id,
        form_type=form_type,
        fields=result["fields"],
        confidence=result["confidence"],
        pages=result["pages"],
        raw_path=str(ocr_path.relative_to(STORAGE_ROOT)),
    )
    return ocr


@app.get("/documents/{username}")
async def list_documents(username: str):
    """List all documents for a user."""
    udir = user_dir(username)
    if not udir.exists():
        return {"documents": []}

    docs = []
    for proc_dir in sorted(udir.iterdir()):
        meta_file = proc_dir / "metadata.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            meta["has_ocr"] = (proc_dir / "ocr_result.json").exists()
            docs.append(meta)
    return {"documents": docs}


@app.get("/documents/{username}/{proc_id}")
async def get_document(username: str, proc_id: str):
    """Get document metadata + OCR result if available."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404)

    meta_file = dest / "metadata.json"
    result = json.loads(meta_file.read_text()) if meta_file.exists() else {}

    ocr_file = dest / "ocr_result.json"
    if ocr_file.exists():
        result["ocr_result"] = json.loads(ocr_file.read_text())

    return result


@app.get("/documents/{username}/{proc_id}/file")
async def download_file(
    username: str,
    proc_id: str,
    download: bool = Query(default=False, description="Force download instead of inline view"),
):
    """View or download the original uploaded file."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404)

    files = [f for f in dest.iterdir() if f.name not in ("metadata.json", "ocr_result.json")]
    if not files:
        raise HTTPException(404)

    if download:
        return FileResponse(files[0], filename=files[0].name)
    return FileResponse(
        files[0],
        filename=files[0].name,
        content_disposition_type="inline",
    )


@app.post("/bridge/{proc_id}")
async def bridge_to_openfile(
    proc_id: str,
    username: str = Query(...),
    tax_return_id: str = Query(...),
    _auth: str = Depends(require_auth),
):
    """Bridge OCR results to OpenFile populated_data table."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404, f"Document {proc_id} not found for user {username}")

    ocr_file = dest / "ocr_result.json"
    if not ocr_file.exists():
        raise HTTPException(400, f"No OCR result for {proc_id}. Run /analyze first.")

    ocr_data = json.loads(ocr_file.read_text())
    ocr_fields = ocr_data.get("fields", {})

    try:
        result = write_populated_data(tax_return_id, ocr_fields)
    except Exception as e:
        raise HTTPException(502, f"Failed to write to OpenFile DB: {str(e)}")

    return result


@app.post("/bridge/{proc_id}/preview")
async def preview_bridge(
    proc_id: str,
    username: str = Query(...),
):
    """Preview the W2 payload that would be written to OpenFile (dry run)."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404)

    ocr_file = dest / "ocr_result.json"
    if not ocr_file.exists():
        raise HTTPException(400, "No OCR result. Run /analyze first.")

    ocr_data = json.loads(ocr_file.read_text())
    return {"w2_payload": ocr_to_w2_payload(ocr_data.get("fields", {}))}


@app.delete("/documents/{username}/{proc_id}")
async def delete_document(username: str, proc_id: str, _auth: str = Depends(require_auth)):
    """Delete a document and all associated files."""
    dest = doc_dir(username, proc_id)
    if not dest.exists():
        raise HTTPException(404)

    import shutil
    shutil.rmtree(dest)
    return {"deleted": proc_id}
