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
    logger.info("TaxLens API starting (v3.32.0)")

    async with mcp.session_manager.run():
        yield

    # Graceful shutdown — flush pending metering events
    logger.info("TaxLens API shutting down — flushing metering buffer")
    await metering.stop()
    await postgrest.close()
    logger.info("TaxLens API shutdown complete")


app = FastAPI(
    title="TaxLens Agentic Tax Intelligence Platform",
    version="3.32.0",
    docs_url="/docs",
    root_path="/api",
    lifespan=lifespan,
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
                    "/mcp", "/mcp/", "/metrics"}

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
        "version": "3.32.0",
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
